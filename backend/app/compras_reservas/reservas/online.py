"""CU10: reservas persistentes y stock comprometido por empresa y sucursal.

La confirmacion reserva disponibilidad, no modifica el stock fisico ni crea
movimientos de venta. La ejecucion offline queda fuera de estos endpoints.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal
import json
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.autenticacion_usuarios.customer_auth import active_store, current_customer_session
from app.db import Base, get_db
from app.models import Cliente, Empresa, Existencia, Producto, Sucursal, VarianteProducto
from app.organizacion_empresarial.plans import current_subscription, subscription_state
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, require_tenant

customer_router = APIRouter(prefix="/api/tiendas/{slug}/reservas", tags=["CU10 · Reservas de cliente"])
staff_router = APIRouter(prefix="/api/admin/reservas", tags=["CU10 · Reservas en sucursal"])


class ReservationRecord(Base):
    __tablename__ = "reservas_cu10"
    __table_args__ = (
        CheckConstraint("estado IN ('CONFIRMADA','CANCELADA','VENCIDA','ATENDIDA')", name="ck_reservas_cu10_estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    lineas: Mapped[list] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(String(15), nullable=False)
    eventos: Mapped[list] = mapped_column(JSON, nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReservationLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variante_id: StrictInt = Field(gt=0)
    cantidad: StrictInt = Field(gt=0, le=100)


class ReservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    sucursal_id: StrictInt = Field(gt=0)
    lineas: list[ReservationLineInput] = Field(min_length=1, max_length=30)
    solicitado_en: datetime | None = None
    origen: Literal["EN_LINEA", "WEB_OFFLINE", "MOVIL_OFFLINE"] = "EN_LINEA"

    @model_validator(mode="after")
    def unique_variants(self):
        if len({line.variante_id for line in self.lineas}) != len(self.lineas):
            raise ValueError("Cada variante debe aparecer una sola vez.")
        return self


class StaffReservationInput(ReservationInput):
    cliente_id: StrictInt = Field(gt=0)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _hours() -> int:
    # Configuracion de negocio controlada por backend, no por el cliente.
    from dotenv import dotenv_values
    from app.config import BACKEND_ROOT
    raw = os.environ.get("RESERVATION_TTL_HOURS") or dotenv_values(BACKEND_ROOT / ".env", interpolate=False).get("RESERVATION_TTL_HOURS") or "24"
    try:
        hours = int(raw)
    except ValueError:
        hours = 0
    if not 1 <= hours <= 720:
        raise HTTPException(503, "Configura RESERVATION_TTL_HOURS entre 1 y 720.")
    return hours


def _active_company(db: Session, company_id: int) -> None:
    subscription = current_subscription(db, company_id)
    if subscription is None or not subscription[1].activo or subscription_state(subscription[0]) != "ACTIVA":
        raise HTTPException(403, "La empresa no tiene un plan activo para reservas.")


def _fingerprint(company_id: int, customer_id: int, payload: ReservationInput) -> str:
    canonical = {
        "empresa": company_id,
        "cliente": customer_id,
        "sucursal": payload.sucursal_id,
        "lineas": sorted((line.variante_id, line.cantidad) for line in payload.lineas),
    }
    return sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _serialize(record: ReservationRecord) -> dict:
    return {
        "id": record.id, "codigo": record.codigo, "estado": record.estado,
        "cliente_id": record.cliente_id, "sucursal_id": record.sucursal_id,
        "lineas": record.lineas, "creada_en": _utc(record.creada_en).isoformat(),
        "vence_en": _utc(record.vence_en).isoformat(),
        "actualizada_en": _utc(record.actualizada_en).isoformat(),
    }


def _event(record: ReservationRecord, state: str, actor: str, at: datetime) -> None:
    record.eventos = [*record.eventos, {
        "estado": state, "actor": actor, "en": at.isoformat(),
    }]
    record.estado = state
    record.actualizada_en = at


def _balances(db: Session, company_id: int, branch_id: int, variant_ids: list[int]) -> dict[int, Existencia]:
    # Orden determinista de bloqueos: evita bloquear variantes en ordenes opuestos.
    rows = db.scalars(select(Existencia).where(
        Existencia.empresa_id == company_id,
        Existencia.sucursal_id == branch_id,
        Existencia.variante_id.in_(variant_ids),
    ).order_by(Existencia.variante_id).with_for_update()).all()
    return {row.variante_id: row for row in rows}


def _release(db: Session, record: ReservationRecord) -> None:
    balances = _balances(db, record.empresa_id, record.sucursal_id,
                         [line["variante_id"] for line in record.lineas])
    for line in record.lineas:
        balance = balances.get(line["variante_id"])
        if balance is None or balance.cantidad_comprometida < line["cantidad"]:
            raise HTTPException(409, "El compromiso no coincide con el inventario; requiere revisión.")
        balance.cantidad_comprometida -= line["cantidad"]


def expire_due(db: Session, company_id: int, at: datetime | None = None) -> int:
    """Vence y libera compromisos una sola vez; misma transaccion que el cambio."""
    now = at or _now()
    expired = db.scalars(select(ReservationRecord).where(
        ReservationRecord.empresa_id == company_id,
        ReservationRecord.estado == "CONFIRMADA",
        ReservationRecord.vence_en <= now,
    ).order_by(ReservationRecord.id).with_for_update()).all()
    for record in expired:
        _release(db, record)
        _event(record, "VENCIDA", "SISTEMA", now)
    return len(expired)


def expire_all_due(session_factory) -> int:
    """Vence reservas de todas las empresas; seguro ante varios workers.

    Cada empresa se procesa y confirma en una transacción independiente. El
    vencimiento utiliza los mismos bloqueos que alta/cancelación/atención.
    """
    total = 0
    with session_factory() as db:
        companies = db.scalars(
            select(ReservationRecord.empresa_id)
            .where(ReservationRecord.estado == "CONFIRMADA")
            .distinct()
        ).all()
        for company_id in companies:
            try:
                total += expire_due(db, company_id)
                db.commit()
            except Exception:
                db.rollback()
                raise
    return total


def _validate_refs(db: Session, company_id: int, branch_id: int,
                   customer_id: int, items: list[ReservationLineInput]) -> None:
    branch = db.scalar(select(Sucursal.id).where(
        Sucursal.id == branch_id, Sucursal.empresa_id == company_id, Sucursal.activo.is_(True)))
    customer = db.scalar(select(Cliente.id).where(
        Cliente.id == customer_id, Cliente.empresa_id == company_id, Cliente.activo.is_(True)))
    if branch is None or customer is None:
        raise HTTPException(404, "Cliente o sucursal no disponible en esta empresa.")
    variants = set(db.scalars(select(VarianteProducto.id).join(
        Producto, Producto.id == VarianteProducto.producto_id,
    ).where(
        VarianteProducto.id.in_([line.variante_id for line in items]),
        VarianteProducto.empresa_id == company_id, VarianteProducto.activo.is_(True),
        Producto.empresa_id == company_id, Producto.activo.is_(True),
    )).all())
    if variants != {line.variante_id for line in items}:
        raise HTTPException(404, "Hay variantes que no pertenecen al catálogo de esta empresa.")


def _create(db: Session, company_id: int, customer_id: int, actor: str,
            payload: ReservationInput) -> dict:
    fingerprint = _fingerprint(company_id, customer_id, payload)
    previous = db.scalar(select(ReservationRecord).where(
        ReservationRecord.id == str(payload.id)).with_for_update())
    if previous is not None:
        if (previous.empresa_id != company_id or previous.cliente_id != customer_id
                or previous.huella != fingerprint):
            raise HTTPException(409, "El identificador ya pertenece a otra solicitud.")
        return _serialize(previous)

    _active_company(db, company_id)
    # El vencimiento es una operación independiente: si esta nueva solicitud
    # falla por validación, no debe deshacer las liberaciones ya vencidas.
    expire_due(db, company_id)
    db.commit()
    _validate_refs(db, company_id, payload.sucursal_id, customer_id, payload.lineas)
    balances = _balances(db, company_id, payload.sucursal_id,
                         [line.variante_id for line in payload.lineas])
    # Tras esperar los bloqueos de stock, otro proceso puede haber confirmado
    # este mismo UUID. Volver a consultar para resolver el reintento sin
    # duplicar compromisos ni producir un falso "stock insuficiente".
    concurrent = db.get(ReservationRecord, str(payload.id))
    if concurrent is not None:
        if (concurrent.empresa_id == company_id and concurrent.cliente_id == customer_id
                and concurrent.huella == fingerprint):
            db.rollback()
            return _serialize(concurrent)
        raise HTTPException(409, "El identificador ya pertenece a otra solicitud.")
    shortages = []
    for line in payload.lineas:
        balance = balances.get(line.variante_id)
        available = max(0, balance.cantidad - balance.cantidad_comprometida) if balance else 0
        if available < line.cantidad:
            shortages.append({
                "variante_id": line.variante_id,
                "disponible": available,
                "solicitado": line.cantidad,
            })
    if shortages:
        raise HTTPException(409, {
            "mensaje": "No hay disponibilidad suficiente para confirmar la reserva.",
            "disponibilidades": shortages,
        })
    for line in payload.lineas:
        balances[line.variante_id].cantidad_comprometida += line.cantidad
    now = _now()
    record = ReservationRecord(
        id=str(payload.id), empresa_id=company_id, cliente_id=customer_id,
        sucursal_id=payload.sucursal_id, codigo=f"VN-R-{uuid4().hex[:12].upper()}",
        huella=fingerprint, lineas=[line.model_dump() for line in payload.lineas],
        estado="CONFIRMADA", eventos=[{
            "estado": "CONFIRMADA", "actor": actor, "en": now.isoformat(),
            "origen": payload.origen,
            "registrada_local_en": (
                _utc(payload.solicitado_en).isoformat() if payload.solicitado_en else None
            ),
        }],
        creada_en=now, vence_en=now + timedelta(hours=_hours()), actualizada_en=now,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Convergencia de reintentos simultaneos: nunca comprometer dos veces.
        stored = db.get(ReservationRecord, str(payload.id))
        if (stored is not None and stored.empresa_id == company_id
                and stored.cliente_id == customer_id and stored.huella == fingerprint):
            return _serialize(stored)
        raise HTTPException(409, "La solicitud ya fue procesada o el código está ocupado.") from None
    return _serialize(record)


def _find(db: Session, company_id: int, reservation_id: UUID) -> ReservationRecord:
    record = db.scalar(select(ReservationRecord).where(
        ReservationRecord.id == str(reservation_id),
        ReservationRecord.empresa_id == company_id,
    ).with_for_update())
    if record is None:
        raise HTTPException(404, "Reserva no encontrada.")
    return record


def _cancel(db: Session, record: ReservationRecord, actor: str, *,
            motivo: str | None = None, commit: bool = True) -> dict:
    expire_due(db, record.empresa_id)
    # Identidad ORM compartida: conservar el nuevo estado VENCIDA y su historial.
    # refresh() aqui perderia las mutaciones no volcadas al registro.
    if record.estado != "CONFIRMADA":
        db.commit()  # Conserva vencimientos liberados si existieron.
        raise HTTPException(409, "Solo se puede cancelar una reserva confirmada y vigente.")
    if _utc(record.vence_en) <= _now():
        expire_due(db, record.empresa_id)
        db.commit()
        raise HTTPException(409, "Esta reserva ya venció.")
    _release(db, record)
    _event(record, "CANCELADA", actor, _now())
    if motivo is not None:
        record.eventos = [*record.eventos[:-1], {**record.eventos[-1], "motivo": motivo}]
    if commit:
        db.commit()
    return _serialize(record)


def _list(db: Session, company_id: int, *, customer_id: int | None = None,
          branches: list[int] | None = None, limit: int = 50) -> list[dict]:
    expire_due(db, company_id)
    query = select(ReservationRecord).where(ReservationRecord.empresa_id == company_id)
    if customer_id is not None:
        query = query.where(ReservationRecord.cliente_id == customer_id)
    if branches is not None:
        query = query.where(ReservationRecord.sucursal_id.in_(branches))
    rows = db.scalars(query.order_by(ReservationRecord.creada_en.desc()).limit(limit)).all()
    db.commit()
    return [_serialize(row) for row in rows]


@customer_router.get("/politica")
def customer_policy(company: Empresa = Depends(active_store),
                    db: Session = Depends(get_db)):
    """Política pública de reservas; consultar no requiere iniciar sesión."""
    _active_company(db, company.id)
    return {"vigencia_horas": _hours(), "requiere_conexion": True}


@customer_router.post("", status_code=201)
def customer_create(payload: ReservationInput, response: Response,
                    current=Depends(current_customer_session), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    client, _, company = current
    try:
        return _create(db, company.id, client.id, f"CLIENTE:{client.id}", payload)
    except HTTPException as exc:
        # CU13: solo el fallo de stock de una solicitud realmente offline genera
        # una incidencia central, y siempre bajo identidad de cliente autenticada.
        if (payload.origen not in ("WEB_OFFLINE", "MOVIL_OFFLINE") or exc.status_code != 409 or
                not isinstance(exc.detail, dict) or
                "disponibilidades" not in exc.detail):
            raise
        from app.operacion_sin_conexion.caja.online import SyncIncident
        existing = db.scalar(select(SyncIncident).where(
            SyncIncident.empresa_id == company.id, SyncIncident.tipo == "RESERVA",
            SyncIncident.operacion_id == str(payload.id),
        ).with_for_update())
        fingerprint = _fingerprint(company.id, client.id, payload)
        if existing is not None:
            if existing.huella != fingerprint:
                raise HTTPException(409, "UUID ya usado por otra reserva.") from None
            incident_id = existing.id
        else:
            incident_id = str(uuid4())
            db.add(SyncIncident(
                id=incident_id, empresa_id=company.id, sucursal_id=payload.sucursal_id,
                usuario_id=None, cliente_id=client.id, tipo="RESERVA",
                operacion_id=str(payload.id), huella=fingerprint,
                datos_originales=payload.model_dump(mode="json"),
                motivo="Stock insuficiente para reservar.",
                estado="CONFLICTO",
            ))
        db.commit()
        raise HTTPException(409, {
            **exc.detail, "incidencia_id": incident_id,
            "mensaje": "Reserva no confirmada por stock insuficiente.",
        }) from None


@customer_router.get("")
def customer_list(response: Response, current=Depends(current_customer_session),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    client, _, company = current
    return _list(db, company.id, customer_id=client.id)


@customer_router.get("/{reservation_id}")
def customer_detail(reservation_id: UUID, response: Response,
                    current=Depends(current_customer_session), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    client, _, company = current
    expire_due(db, company.id)
    row = _find(db, company.id, reservation_id)
    if row.cliente_id != client.id:
        raise HTTPException(404, "Reserva no encontrada.")
    db.commit()
    return _serialize(row)


@customer_router.post("/{reservation_id}/cancelar")
def customer_cancel(reservation_id: UUID, current=Depends(current_customer_session),
                    db: Session = Depends(get_db)):
    client, _, company = current
    record = _find(db, company.id, reservation_id)
    if record.cliente_id != client.id:
        raise HTTPException(404, "Reserva no encontrada.")
    return _cancel(db, record, f"CLIENTE:{client.id}")


def _staff(context: TenantContext) -> None:
    if context.acceso is None or context.acceso.codigo_sistema not in {
        "ADMINISTRADOR", "ENCARGADO_SUCURSAL", "CAJERO"
    }:
        raise HTTPException(403, "Se requiere un perfil comercial autorizado para reservas.")


@staff_router.post("", status_code=201)
def staff_create(payload: StaffReservationInput, context: TenantContext = Depends(require_tenant),
                 db: Session = Depends(get_db)):
    _staff(context)
    authorized_branch(db, context, payload.sucursal_id)
    return _create(db, context.empresa_id, payload.cliente_id,
                   f"PERSONAL:{context.usuario.id}", payload)


@staff_router.get("")
def staff_list(context: TenantContext = Depends(require_tenant), db: Session = Depends(get_db),
               sucursal_id: int | None = Query(default=None, gt=0)):
    _staff(context)
    if sucursal_id is not None:
        authorized_branch(db, context, sucursal_id)
        branches = [sucursal_id]
    else:
        branches = list(db.scalars(authorized_branches_statement(context).with_only_columns(Sucursal.id)).all())
    return _list(db, context.empresa_id, branches=branches)


@staff_router.get("/{reservation_id}")
def staff_detail(reservation_id: UUID, context: TenantContext = Depends(require_tenant),
                 db: Session = Depends(get_db)):
    _staff(context)
    expire_due(db, context.empresa_id)
    record = _find(db, context.empresa_id, reservation_id)
    authorized_branch(db, context, record.sucursal_id)
    db.commit()
    return _serialize(record)


@staff_router.post("/{reservation_id}/cancelar")
def staff_cancel(reservation_id: UUID, context: TenantContext = Depends(require_tenant),
                 db: Session = Depends(get_db)):
    _staff(context)
    record = _find(db, context.empresa_id, reservation_id)
    authorized_branch(db, context, record.sucursal_id)
    return _cancel(db, record, f"PERSONAL:{context.usuario.id}")
