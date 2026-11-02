"""CU11: registro, consulta, ediciÃ³n y habilitaciÃ³n de empresas contratantes."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Administrador, Empresa, MembresiaEmpresa, PlanSaaS, SuscripcionEmpresa, utc_now
from app.autenticacion_usuarios.permissions import ensure_company_roles
from app.tenancy import require_superadministrator


router = APIRouter(prefix="/api/plataforma", tags=["CU11 Â· Empresas contratantes"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyCreate(Input):
    nombre: str = Field(min_length=3, max_length=120)
    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    administrador_id: int = Field(gt=0, strict=True)
    nit: str | None = Field(default=None, max_length=30)
    correo_contacto: str | None = Field(default=None, max_length=254)
    telefono_contacto: str | None = Field(default=None, max_length=40)

    @field_validator("correo_contacto")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Introduce un correo de contacto vÃ¡lido.")
        return normalized


class CompanyPatch(Input):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    nit: str | None = Field(default=None, max_length=30)
    correo_contacto: str | None = Field(default=None, max_length=254)
    telefono_contacto: str | None = Field(default=None, max_length=40)

    @field_validator("nombre")
    @classmethod
    def name_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("El nombre de la empresa no puede quedar vacío.")
        return value

    @field_validator("correo_contacto")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Introduce un correo de contacto vÃ¡lido.")
        return normalized

    @model_validator(mode="after")
    def changes_required(self):
        if not self.model_fields_set:
            raise ValueError("EnvÃ­a al menos un campo para actualizar.")
        return self


class CompanyStatePatch(Input):
    activo: bool = Field(strict=True)


class CompanyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    slug: str
    nit: str | None
    correo_contacto: str | None
    telefono_contacto: str | None
    activo: bool
    creado_en: str
    administradores_activos: int = 0


class AdministratorOption(BaseModel):
    id: int
    nombre: str
    correo: str


def _company_view(db: Session, company: Empresa) -> CompanyView:
    count = db.scalar(select(func.count()).select_from(MembresiaEmpresa).where(
        MembresiaEmpresa.empresa_id == company.id, MembresiaEmpresa.activo.is_(True)
    )) or 0
    return CompanyView(
        id=company.id, nombre=company.nombre, slug=company.slug, nit=company.nit,
        correo_contacto=company.correo_contacto, telefono_contacto=company.telefono_contacto,
        activo=company.activo, creado_en=company.creado_en.isoformat(), administradores_activos=count,
    )


@router.get("/administradores", response_model=list[AdministratorOption])
def list_initial_administrators(
    q: str | None = Query(default=None, max_length=120),
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    statement = select(Administrador).where(Administrador.activo.is_(True), Administrador.es_superadministrador.is_(False))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(Administrador.nombre.ilike(pattern) | Administrador.correo.ilike(pattern))
    rows = db.scalars(statement.order_by(Administrador.nombre, Administrador.id).limit(100)).all()
    return [AdministratorOption(id=row.id, nombre=row.nombre, correo=row.correo) for row in rows]


@router.get("/empresas", response_model=list[CompanyView])
def list_companies(
    q: str | None = Query(default=None, max_length=120),
    estado: Literal["activas", "inactivas", "todas"] = "todas",
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    statement = select(Empresa)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(Empresa.nombre.ilike(pattern) | Empresa.slug.ilike(pattern))
    if estado == "activas":
        statement = statement.where(Empresa.activo.is_(True))
    elif estado == "inactivas":
        statement = statement.where(Empresa.activo.is_(False))
    rows = db.scalars(statement.order_by(Empresa.id.desc()).limit(500)).all()
    return [_company_view(db, row) for row in rows]


@router.post("/empresas", response_model=CompanyView, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    owner = db.get(Administrador, payload.administrador_id)
    if owner is None or not owner.activo or owner.es_superadministrador:
        raise HTTPException(422, "El administrador inicial debe ser una cuenta empresarial activa.")
    basic_plan = db.scalar(select(PlanSaaS).where(PlanSaaS.codigo == "BASICO", PlanSaaS.activo.is_(True)))
    if basic_plan is None:
        raise HTTPException(409, "Activa un plan BÃ¡sico antes de registrar empresas.")

    company = Empresa(
        nombre=payload.nombre, slug=payload.slug, nit=payload.nit or None,
        correo_contacto=payload.correo_contacto or None, telefono_contacto=payload.telefono_contacto or None,
        activo=True,
    )
    db.add(company)
    try:
        db.flush()
        roles = ensure_company_roles(db, company.id)
        db.add(MembresiaEmpresa(
            administrador_id=owner.id, empresa_id=company.id, nombre=owner.nombre,
            rol="ADMINISTRADOR", rol_empresa_id=roles["ADMINISTRADOR"].id, activo=True,
        ))
        db.add(SuscripcionEmpresa(
            empresa_id=company.id, plan_id=basic_plan.id, estado="ACTIVA",
            inicia_en=utc_now(), renueva_en=None, actualizado_en=utc_now(),
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una empresa con ese slug o el administrador ya tiene esa pertenencia.") from None
    db.refresh(company)
    return _company_view(db, company)


@router.patch("/empresas/{empresa_id}", response_model=CompanyView)
def update_company(
    empresa_id: int,
    payload: CompanyPatch,
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    company = db.get(Empresa, empresa_id)
    if company is None:
        raise HTTPException(404, "Empresa no encontrada.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar la empresa.") from None
    db.refresh(company)
    return _company_view(db, company)


@router.patch("/empresas/{empresa_id}/estado", response_model=CompanyView)
def change_company_state(
    empresa_id: int,
    payload: CompanyStatePatch,
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    company = db.get(Empresa, empresa_id)
    if company is None:
        raise HTTPException(404, "Empresa no encontrada.")
    company.activo = payload.activo
    db.commit()
    db.refresh(company)
    return _company_view(db, company)
