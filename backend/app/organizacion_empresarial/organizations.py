"""Gestión de empresas y pertenencias empresariales del personal."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa
from app.security import require_administrator
from app.autenticacion_usuarios.permissions import effective_role, ensure_company_roles
from app.organizacion_empresarial.audit import record_audit_event
from app.autenticacion_usuarios.staff import check_assignable_role, check_target_authority, get_member, protect_last_administrator, replace_branches, validate_branches
from app.tenancy import TenantContext, require_permission, require_tenant


router = APIRouter(tags=["Empresas y pertenencias"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmpresaPatch(Input):
    nombre: str = Field(min_length=3, max_length=120)


class EmpresaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    slug: str
    activo: bool


class EmpresaAccesoResponse(EmpresaResponse):
    rol: Literal["ADMINISTRADOR", "OPERADOR", "ENCARGADO_SUCURSAL", "CAJERO"]
    rol_id: int | None = None
    rol_nombre: str = ""
    rol_sistema: str | None = None
    permisos: list[str] = Field(default_factory=list)


class PertenenciaCreate(Input):
    administrador_id: int = Field(gt=0, strict=True)
    rol: Literal["ADMINISTRADOR", "OPERADOR", "ENCARGADO_SUCURSAL", "CAJERO"]
    activo: bool = Field(default=True, strict=True)
    sucursal_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=100)

    @field_validator("sucursal_ids")
    @classmethod
    def valid_branches(cls, value):
        if any(isinstance(item, bool) or item <= 0 for item in value) or len(set(value)) != len(value):
            raise ValueError("Las sucursales deben ser identificadores positivos sin duplicados.")
        return value

    @model_validator(mode="after")
    def branch_grants_only_for_operator(self):
        if self.rol == "ADMINISTRADOR" and self.sucursal_ids:
            raise ValueError("El administrador accede a todas las sucursales activas; no envíes sucursal_ids.")
        return self


class PertenenciaResponse(BaseModel):
    administrador_id: int
    empresa_id: int
    rol: Literal["ADMINISTRADOR", "OPERADOR", "ENCARGADO_SUCURSAL", "CAJERO"]
    activo: bool
    sucursal_ids: list[int]


def commit_organization(db: Session, message: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, message) from None


@router.get("/api/empresas", response_model=list[EmpresaAccesoResponse])
def my_companies(usuario: Administrador = Depends(require_administrator), db: Session = Depends(get_db)):
    rows = db.execute(select(Empresa, MembresiaEmpresa).join(MembresiaEmpresa, Empresa.id == MembresiaEmpresa.empresa_id).where(
        MembresiaEmpresa.administrador_id == usuario.id, MembresiaEmpresa.activo.is_(True), Empresa.activo.is_(True)
    ).order_by(Empresa.id)).all()
    result = []
    for company, member in rows:
        access = effective_role(db, member)
        if access is not None:
            result.append(company_access(company, member, access))
    return result


def company_access(company, member, access):
    return {**EmpresaResponse.model_validate(company).model_dump(), "rol": member.rol, "rol_id": access.id,
            "rol_nombre": access.nombre, "rol_sistema": access.codigo_sistema, "permisos": sorted(access.permisos)}


@router.get("/api/admin/empresa", response_model=EmpresaResponse)
def current_company(context: TenantContext = Depends(require_tenant)):
    return context.empresa


@router.patch("/api/admin/empresa", response_model=EmpresaResponse)
def update_current_company(payload: EmpresaPatch, context: TenantContext = Depends(require_permission("empresa.editar", mutation=True)), db: Session = Depends(get_db)):
    context.empresa.nombre = payload.nombre
    db.commit()
    return context.empresa


def membership_response(db: Session, membership: MembresiaEmpresa):
    branch_ids = db.scalars(select(AccesoSucursal.sucursal_id).where(
        AccesoSucursal.empresa_id == membership.empresa_id, AccesoSucursal.administrador_id == membership.administrador_id
    ).order_by(AccesoSucursal.sucursal_id)).all()
    return PertenenciaResponse(administrador_id=membership.administrador_id, empresa_id=membership.empresa_id, rol=membership.rol, activo=membership.activo, sucursal_ids=list(branch_ids))


@router.get("/api/admin/pertenencias", response_model=list[PertenenciaResponse])
def list_memberships(context: TenantContext = Depends(require_permission("usuarios.consultar")), db: Session = Depends(get_db)):
    memberships = db.scalars(select(MembresiaEmpresa).where(MembresiaEmpresa.empresa_id == context.empresa_id).order_by(MembresiaEmpresa.administrador_id)).all()
    return [membership_response(db, membership) for membership in memberships]


@router.post("/api/admin/pertenencias", response_model=PertenenciaResponse)
def assign_membership(payload: PertenenciaCreate, context: TenantContext = Depends(require_permission("usuarios.editar", mutation=True)), db: Session = Depends(get_db)):
    # Compatibilidad de URI y cuerpo: solo actualiza miembros existentes. Nunca
    # vincula identidades globales ajenas por un ID adivinado desde una empresa.
    membership, _ = get_member(db, context.empresa_id, payload.administrador_id)
    check_target_authority(db, context, membership)
    role = ensure_company_roles(db, context.empresa_id)[payload.rol]
    check_assignable_role(db, context, role)
    validate_branches(db, context, payload.sucursal_ids, role.codigo_sistema)
    protect_last_administrator(db, membership, active=payload.activo, system_role=role.codigo_sistema)
    membership.rol = payload.rol
    membership.rol_empresa_id = role.id
    membership.activo = payload.activo
    db.flush()
    replace_branches(db, membership, payload.sucursal_ids)
    record_audit_event(db, context, accion="usuario.acceso_actualizado", entidad="usuario",
                       entidad_id=membership.administrador_id,
                       detalles={"rol": role.nombre, "activo": membership.activo,
                                 "sucursales": sorted(payload.sucursal_ids)})
    commit_organization(db, "No se pudo actualizar la pertenencia y sus sucursales.")
    return membership_response(db, membership)
