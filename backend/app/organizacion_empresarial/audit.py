"""CU02: bitácora empresarial de solo anexado y filtrada por tenant."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EventoAuditoria
from app.tenancy import TenantContext, require_permission


router = APIRouter(prefix="/api/admin/auditoria", tags=["CU02 · Bitácora de auditoría"])


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    actor_id: int
    actor_nombre: str
    actor_correo: str
    accion: str
    entidad: str
    entidad_id: str
    detalles: dict[str, object]
    creado_en: datetime


class AuditPage(BaseModel):
    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


def record_audit_event(
    db: Session,
    context: TenantContext,
    *,
    accion: str,
    entidad: str,
    entidad_id: int | str,
    detalles: dict[str, object] | None = None,
) -> None:
    """Agrega un evento a la misma transacción que la modificación auditada."""
    db.add(EventoAuditoria(
        empresa_id=context.empresa_id,
        actor_id=context.usuario.id,
        actor_nombre=context.membresia.nombre or context.usuario.nombre,
        actor_correo=context.usuario.correo,
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id),
        detalles=detalles or {},
    ))


@router.get("", response_model=AuditPage)
def list_audit_events(
    q: str | None = Query(default=None, max_length=120),
    accion: str | None = Query(default=None, max_length=80),
    entidad: Literal["usuario", "rol", "sucursal", "categoria", "producto", "variante"] | None = None,
    actor_id: int | None = Query(default=None, gt=0),
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission("auditoria.consultar")),
    db: Session = Depends(get_db),
):
    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la fecha final.")

    filters = [EventoAuditoria.empresa_id == context.empresa_id]
    if q and q.strip():
        needle = q.strip().lower()
        filters.append(or_(
            func.lower(EventoAuditoria.actor_nombre).contains(needle, autoescape=True),
            func.lower(EventoAuditoria.actor_correo).contains(needle, autoescape=True),
            func.lower(EventoAuditoria.accion).contains(needle, autoescape=True),
            func.lower(EventoAuditoria.entidad).contains(needle, autoescape=True),
            func.lower(EventoAuditoria.entidad_id).contains(needle, autoescape=True),
        ))
    if accion:
        filters.append(EventoAuditoria.accion == accion)
    if entidad:
        filters.append(EventoAuditoria.entidad == entidad)
    if actor_id is not None:
        filters.append(EventoAuditoria.actor_id == actor_id)
    if desde is not None:
        filters.append(EventoAuditoria.creado_en >= datetime.combine(desde, time.min, tzinfo=timezone.utc))
    if hasta is not None:
        filters.append(EventoAuditoria.creado_en < datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=timezone.utc))

    total = db.scalar(select(func.count()).select_from(EventoAuditoria).where(*filters)) or 0
    items = db.scalars(
        select(EventoAuditoria)
        .where(*filters)
        .order_by(EventoAuditoria.creado_en.desc(), EventoAuditoria.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AuditPage(items=items, total=total, limit=limit, offset=offset)
