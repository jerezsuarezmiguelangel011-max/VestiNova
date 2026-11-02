"""CU03: consulta y gestión de sucursales de una empresa."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.db import get_db
from app.models import Sucursal
from app.organizacion_empresarial.plans import ensure_resource_capacity
from app.tenancy import TenantContext, authorized_branches_statement, require_permission


router = APIRouter(tags=["CU03 · Sucursales"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SucursalCreate(Input):
    codigo: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=3, max_length=120)
    ciudad: str = Field(default="", max_length=100)
    ubicacion: str = Field(default="", max_length=240)
    contacto: str = Field(default="", max_length=120)

    @field_validator("codigo")
    @classmethod
    def normalize_code(cls, value: str):
        value = value.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", value):
            raise ValueError("El código admite letras ASCII, números, guion y guion bajo.")
        return value


class SucursalPatch(Input):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    ciudad: str | None = Field(default=None, max_length=100)
    ubicacion: str | None = Field(default=None, max_length=240)
    contacto: str | None = Field(default=None, max_length=120)
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
    ciudad: str
    ubicacion: str
    contacto: str
    activo: bool


def commit_branch(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, message) from None


@router.get("/api/admin/sucursales", response_model=list[SucursalResponse])
def my_branches(context: TenantContext = Depends(require_permission("sucursales.consultar")), db: Session = Depends(get_db)):
    return db.scalars(authorized_branches_statement(context).order_by(Sucursal.id)).all()


@router.get("/api/admin/sucursales/gestion", response_model=list[SucursalResponse])
def managed_branches(context: TenantContext = Depends(require_permission("sucursales.gestionar")), db: Session = Depends(get_db)):
    return db.scalars(select(Sucursal).where(Sucursal.empresa_id == context.empresa_id).order_by(Sucursal.id)).all()


@router.post("/api/admin/sucursales", response_model=SucursalResponse, status_code=201)
def create_branch(payload: SucursalCreate, context: TenantContext = Depends(require_permission("sucursales.gestionar", mutation=True)), db: Session = Depends(get_db)):
    ensure_resource_capacity(db, context.empresa_id, "sucursales")
    branch = Sucursal(empresa_id=context.empresa_id, **payload.model_dump(), activo=True)
    db.add(branch)
    try:
        db.flush()
        record_audit_event(db, context, accion="sucursal.creada", entidad="sucursal", entidad_id=branch.id,
                           detalles={"codigo": branch.codigo, "nombre": branch.nombre})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sucursal con ese código en la empresa.") from None
    return branch


@router.patch("/api/admin/sucursales/{sucursal_id}", response_model=SucursalResponse)
def update_branch(sucursal_id: int, payload: SucursalPatch,
                  context: TenantContext = Depends(require_permission("sucursales.gestionar", mutation=True)),
                  db: Session = Depends(get_db)):
    # Incluye inactivas para permitir una reactivación explícita; nunca otras empresas.
    branch = db.scalar(select(Sucursal).where(Sucursal.id == sucursal_id, Sucursal.empresa_id == context.empresa_id))
    if branch is None:
        raise HTTPException(404, "Sucursal no encontrada.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("activo") is True and not branch.activo:
        ensure_resource_capacity(db, context.empresa_id, "sucursales")
    for name, value in changes.items():
        setattr(branch, name, value)
    record_audit_event(db, context, accion="sucursal.actualizada", entidad="sucursal", entidad_id=branch.id,
                       detalles={"campos": sorted(changes), "codigo": branch.codigo})
    commit_branch(db, "No se pudo actualizar la sucursal.")
    return branch
