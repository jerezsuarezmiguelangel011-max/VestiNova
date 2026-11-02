"""AdministraciÃ³n SaaS de planes y suscripciones para CU12."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Empresa, PlanSaaS, SuscripcionEmpresa, utc_now
from app.organizacion_empresarial.plans import PlanResponse, subscription_state
from app.tenancy import require_superadministrator


router = APIRouter(prefix="/api/plataforma", tags=["CU12 Â· Planes y suscripciones"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlanCreate(Input):
    codigo: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    nombre: str = Field(min_length=2, max_length=100)
    descripcion: str = Field(default="", max_length=500)
    precio_mensual: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    max_sucursales: int = Field(ge=1, le=10000, strict=True)
    max_productos: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    max_usuarios: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    prestaciones: list[str] = Field(default_factory=list, max_length=40)
    activo: bool = Field(default=True, strict=True)

    @field_validator("prestaciones")
    @classmethod
    def valid_features(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 80 for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("Las prestaciones deben ser textos breves, no vacÃ­os y sin duplicados.")
        return normalized


class PlanPatch(Input):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    precio_mensual: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    max_sucursales: int | None = Field(default=None, ge=1, le=10000, strict=True)
    max_productos: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    max_usuarios: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    prestaciones: list[str] | None = Field(default=None, max_length=40)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def changes_required(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set - {"precio_mensual", "max_productos", "max_usuarios"}):
            raise ValueError("EnvÃ­a al menos un cambio vÃ¡lido.")
        return self


class SubscriptionSet(Input):
    plan_id: int = Field(gt=0, strict=True)
    estado: Literal["ACTIVA", "SUSPENDIDA", "VENCIDA", "CANCELADA"] = "ACTIVA"
    inicia_en: datetime
    renueva_en: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.inicia_en.utcoffset() is None or (self.renueva_en is not None and self.renueva_en.utcoffset() is None):
            raise ValueError("Las fechas deben incluir zona horaria.")
        if self.renueva_en is not None and self.renueva_en < self.inicia_en:
            raise ValueError("La fecha de renovaciÃ³n no puede preceder al inicio.")
        return self


class SubscriptionView(BaseModel):
    empresa_id: int
    empresa_nombre: str
    empresa_slug: str
    empresa_activa: bool
    estado: str
    inicia_en: datetime
    renueva_en: datetime | None
    plan: PlanResponse


@router.get("/planes", response_model=list[PlanResponse])
def list_plans(_: object = Depends(require_superadministrator), db: Session = Depends(get_db)):
    return db.scalars(select(PlanSaaS).order_by(PlanSaaS.max_sucursales, PlanSaaS.nombre)).all()


@router.post("/planes", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, _: object = Depends(require_superadministrator), db: Session = Depends(get_db)):
    plan = PlanSaaS(**payload.model_dump())
    db.add(plan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un plan con ese cÃ³digo.") from None
    db.refresh(plan)
    return plan


@router.patch("/planes/{plan_id}", response_model=PlanResponse)
def update_plan(plan_id: int, payload: PlanPatch, _: object = Depends(require_superadministrator), db: Session = Depends(get_db)):
    plan = db.get(PlanSaaS, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan no encontrado.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("activo") is False:
        active_subscription = db.scalar(select(SuscripcionEmpresa.empresa_id).where(
            SuscripcionEmpresa.plan_id == plan.id,
            SuscripcionEmpresa.estado == "ACTIVA",
        ).limit(1))
        if active_subscription is not None:
            raise HTTPException(409, "No se puede desactivar un plan con suscripciones activas.")
    for field, value in changes.items():
        setattr(plan, field, value)
    plan.actualizado_en = utc_now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar el plan.") from None
    db.refresh(plan)
    return plan


@router.get("/suscripciones", response_model=list[SubscriptionView])
def list_subscriptions(
    q: str | None = Query(default=None, max_length=120),
    estado: Literal["ACTIVA", "SUSPENDIDA", "VENCIDA", "CANCELADA", "PROGRAMADA"] | None = None,
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    statement = select(SuscripcionEmpresa, Empresa, PlanSaaS).join(
        Empresa, Empresa.id == SuscripcionEmpresa.empresa_id
    ).join(PlanSaaS, PlanSaaS.id == SuscripcionEmpresa.plan_id)
    if q and q.strip():
        statement = statement.where(Empresa.nombre.ilike(f"%{q.strip()}%"))
    rows = db.execute(statement.order_by(Empresa.nombre, Empresa.id)).all()
    result = []
    for subscription, company, plan in rows:
        effective_state = subscription_state(subscription)
        if estado is not None and effective_state != estado:
            continue
        result.append(SubscriptionView(
            empresa_id=company.id,
            empresa_nombre=company.nombre,
            empresa_slug=company.slug,
            empresa_activa=company.activo,
            estado=effective_state,
            inicia_en=subscription.inicia_en,
            renueva_en=subscription.renueva_en,
            plan=PlanResponse.model_validate(plan),
        ))
    return result


@router.put("/empresas/{empresa_id}/suscripcion", response_model=SubscriptionView)
def set_company_subscription(
    empresa_id: int,
    payload: SubscriptionSet,
    _: object = Depends(require_superadministrator),
    db: Session = Depends(get_db),
):
    company = db.get(Empresa, empresa_id)
    plan = db.get(PlanSaaS, payload.plan_id)
    if company is None:
        raise HTTPException(404, "Empresa no encontrada.")
    if plan is None or not plan.activo:
        raise HTTPException(422, "Selecciona un plan activo.")
    subscription = db.get(SuscripcionEmpresa, company.id)
    if subscription is None:
        subscription = SuscripcionEmpresa(empresa_id=company.id, plan_id=plan.id)
        db.add(subscription)
    subscription.plan_id = plan.id
    subscription.estado = payload.estado
    subscription.inicia_en = payload.inicia_en.astimezone(timezone.utc)
    subscription.renueva_en = payload.renueva_en.astimezone(timezone.utc) if payload.renueva_en else None
    subscription.actualizado_en = utc_now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar la suscripciÃ³n.") from None
    return SubscriptionView(
        empresa_id=company.id,
        empresa_nombre=company.nombre,
        empresa_slug=company.slug,
        empresa_activa=company.activo,
        estado=subscription_state(subscription),
        inicia_en=subscription.inicia_en,
        renueva_en=subscription.renueva_en,
        plan=PlanResponse.model_validate(plan),
    )
