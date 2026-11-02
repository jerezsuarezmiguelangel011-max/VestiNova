"""Gestión mínima de empresas, sucursales y pertenencias autorizadas."""
from typing import Annotated, Literal
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa, Sucursal
from app.security import require_administrator
from app.permissions import effective_role, ensure_company_roles
from app.staff import check_assignable_role, check_target_authority, get_member, protect_last_administrator, replace_branches, validate_branches
from app.tenancy import TenantContext, authorized_branches_statement, require_permission, require_superadministrator, require_tenant


router = APIRouter(tags=["Empresas y sucursales"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmpresaCreate(Input):
    nombre: str = Field(min_length=3, max_length=120)
    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    administrador_id: int = Field(gt=0, strict=True)


class EmpresaPatch(Input):
    nombre: str = Field(min_length=3, max_length=120)


class EmpresaEstadoPatch(Input):
    activo: bool = Field(strict=True)


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


class SucursalCreate(Input):
    codigo: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=3, max_length=120)

    @field_validator("codigo")
    @classmethod
    def normalize_code(cls, value: str):
        value = value.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", value):
            raise ValueError("El código admite letras ASCII, números, guion y guion bajo.")
        return value


class SucursalPatch(Input):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def required_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Envía al menos un cambio no nulo.")
        return self


class SucursalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    codigo: str
    nombre: str
    activo: bool


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


@router.post("/api/plataforma/empresas", response_model=EmpresaResponse, status_code=201)
def create_company(payload: EmpresaCreate, _: Administrador = Depends(require_superadministrator), db: Session = Depends(get_db)):
    owner = db.get(Administrador, payload.administrador_id)
    if owner is None or not owner.activo:
        raise HTTPException(422, "El administrador inicial debe ser una cuenta activa existente.")
    company = Empresa(nombre=payload.nombre, slug=payload.slug, activo=True)
    db.add(company)
    try:
        db.flush()
        roles = ensure_company_roles(db, company.id)
        db.add(MembresiaEmpresa(administrador_id=owner.id, empresa_id=company.id, nombre=owner.nombre,
                               rol="ADMINISTRADOR", rol_empresa_id=roles["ADMINISTRADOR"].id, activo=True))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una empresa con ese slug.") from None
    return company


@router.patch("/api/plataforma/empresas/{empresa_id}/estado", response_model=EmpresaResponse)
def change_company_state(empresa_id: int, payload: EmpresaEstadoPatch, _: Administrador = Depends(require_superadministrator), db: Session = Depends(get_db)):
    company = db.get(Empresa, empresa_id)
    if company is None:
        raise HTTPException(404, "Empresa no encontrada.")
    company.activo = payload.activo
    db.commit()
    return company


@router.get("/api/admin/empresa", response_model=EmpresaResponse)
def current_company(context: TenantContext = Depends(require_tenant)):
    return context.empresa


@router.patch("/api/admin/empresa", response_model=EmpresaResponse)
def update_current_company(payload: EmpresaPatch, context: TenantContext = Depends(require_permission("empresa.editar", mutation=True)), db: Session = Depends(get_db)):
    context.empresa.nombre = payload.nombre
    db.commit()
    return context.empresa


@router.get("/api/admin/sucursales", response_model=list[SucursalResponse])
def my_branches(context: TenantContext = Depends(require_permission("sucursales.consultar")), db: Session = Depends(get_db)):
    return db.scalars(authorized_branches_statement(context).order_by(Sucursal.id)).all()


@router.post("/api/admin/sucursales", response_model=SucursalResponse, status_code=201)
def create_branch(payload: SucursalCreate, context: TenantContext = Depends(require_permission("sucursales.gestionar", mutation=True)), db: Session = Depends(get_db)):
    branch = Sucursal(empresa_id=context.empresa_id, codigo=payload.codigo, nombre=payload.nombre, activo=True)
    db.add(branch)
    commit_organization(db, "Ya existe una sucursal con ese código en la empresa.")
    return branch


@router.patch("/api/admin/sucursales/{sucursal_id}", response_model=SucursalResponse)
def update_branch(sucursal_id: int, payload: SucursalPatch, context: TenantContext = Depends(require_permission("sucursales.gestionar", mutation=True)), db: Session = Depends(get_db)):
    # Incluye inactivas para permitir una reactivación explícita; nunca otras empresas.
    branch = db.scalar(select(Sucursal).where(Sucursal.id == sucursal_id, Sucursal.empresa_id == context.empresa_id))
    if branch is None:
        raise HTTPException(404, "Sucursal no encontrada.")
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(branch, name, value)
    db.commit()
    return branch


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
    commit_organization(db, "No se pudo actualizar la pertenencia y sus sucursales.")
    return membership_response(db, membership)
