"""CU12: lectura de suscripciÃ³n y lÃ­mites efectivos por empresa."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MembresiaEmpresa, PlanSaaS, Producto, Sucursal, SuscripcionEmpresa
from app.tenancy import TenantContext, require_permission


router = APIRouter(prefix="/api/admin/plan", tags=["CU12 Â· Planes y suscripciones"])


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def subscription_state(subscription: SuscripcionEmpresa, *, now: datetime | None = None) -> str:
    current = _utc(now or datetime.now(timezone.utc))
    if subscription.estado == "ACTIVA" and _utc(subscription.inicia_en) > current:
        return "PROGRAMADA"
    if subscription.estado == "ACTIVA" and subscription.renueva_en is not None:
        if _utc(subscription.renueva_en) <= current:
            return "VENCIDA"
    return subscription.estado


def current_subscription(db: Session, empresa_id: int) -> tuple[SuscripcionEmpresa, PlanSaaS] | None:
    row = db.execute(
        select(SuscripcionEmpresa, PlanSaaS)
        .join(PlanSaaS, PlanSaaS.id == SuscripcionEmpresa.plan_id)
        .where(SuscripcionEmpresa.empresa_id == empresa_id)
    ).first()
    return row if row is not None else None


def ensure_resource_capacity(db: Session, empresa_id: int, recurso: str, *, cantidad: int = 1) -> None:
    """Comprueba el plan y el cupo actual antes de crear/reactivar un recurso."""
    row = current_subscription(db, empresa_id)
    if row is None:
        raise HTTPException(409, "La empresa no tiene un plan asignado.")
    subscription, plan = row
    if not plan.activo or subscription_state(subscription) != "ACTIVA":
        raise HTTPException(409, "La suscripciÃ³n no estÃ¡ activa. Revisa el plan con la administraciÃ³n de VestiNova.")

    definitions = {
        "sucursales": ("max_sucursales", select(func.count()).select_from(Sucursal).where(Sucursal.empresa_id == empresa_id, Sucursal.activo.is_(True))),
        "productos": ("max_productos", select(func.count()).select_from(Producto).where(Producto.empresa_id == empresa_id, Producto.activo.is_(True))),
        "usuarios": ("max_usuarios", select(func.count()).select_from(MembresiaEmpresa).where(MembresiaEmpresa.empresa_id == empresa_id, MembresiaEmpresa.activo.is_(True))),
    }
    if recurso not in definitions:
        raise ValueError(f"Recurso de plan desconocido: {recurso}")
    limit_name, count_statement = definitions[recurso]
    limit = getattr(plan, limit_name)
    if limit is None:
        return
    current = db.scalar(count_statement) or 0
    if current + cantidad > limit:
        names = {"sucursales": "sucursales activas", "productos": "productos activos", "usuarios": "usuarios activos"}
        raise HTTPException(409, f"El plan {plan.nombre} permite hasta {limit} {names[recurso]}.")


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    descripcion: str
    precio_mensual: Decimal | None
    max_sucursales: int
    max_productos: int | None
    max_usuarios: int | None
    prestaciones: list[str]
    activo: bool

    @field_serializer("precio_mensual")
    def serialize_price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class SuscripcionActualResponse(BaseModel):
    empresa_id: int
    empresa_nombre: str
    estado: str
    plan: PlanResponse
    inicia_en: datetime
    renueva_en: datetime | None


@router.get("", response_model=SuscripcionActualResponse)
def my_plan(context: TenantContext = Depends(require_permission("plan.consultar")), db: Session = Depends(get_db)):
    current = current_subscription(db, context.empresa_id)
    if current is None:
        raise HTTPException(404, "La empresa todavÃ­a no tiene un plan asignado.")
    subscription, plan = current
    plan_response = PlanResponse.model_validate(plan)
    return SuscripcionActualResponse(
        empresa_id=context.empresa_id,
        empresa_nombre=context.empresa.nombre,
        estado=subscription_state(subscription),
        plan=plan_response,
        inicia_en=subscription.inicia_en,
        renueva_en=subscription.renueva_en,
    )
