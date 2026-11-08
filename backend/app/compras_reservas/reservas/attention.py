"""CU14: atención y entrega de reservas confirmadas en una sucursal autorizada.

Las salidas físicas y el compromiso se modifican en la misma transacción.
No acepta borradores ni solicitudes PENDIENTE de dispositivos offline.
"""
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Cliente, MovimientoInventario, Producto, Sucursal, VarianteProducto, utc_now
from app.organizacion_empresarial.audit import record_audit_event
from app.tenancy import (
    TenantContext, authorized_branch, authorized_branches_statement,
    lock_tenant_mutation, require_tenant,
)
from app.compras_reservas.reservas.online import (
    ReservationRecord, _balances, _cancel, _find, _now, _serialize,
    _utc, expire_due,
)

router = APIRouter(prefix="/api/admin/atencion-reservas", tags=["CU14 · Atención de reservas"])


class DeliveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identidad_verificada: bool
    comprobacion: str = Field(min_length=3, max_length=180)


class CancellationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=5, max_length=300)


def _staff(context: TenantContext) -> None:
    if context.acceso is None or context.acceso.codigo_sistema not in {
        "ENCARGADO_SUCURSAL", "CAJERO",
    }:
        raise HTTPException(403, "La entrega requiere perfil Encargado o Cajero autorizado.")


def _scope(db: Session, context: TenantContext, branch_id: int | None = None) -> list[int]:
    if branch_id is not None:
        authorized_branch(db, context, branch_id)
        return [branch_id]
    return list(db.scalars(
        authorized_branches_statement(context).with_only_columns(Sucursal.id)
    ).all())


def _detail(db: Session, record: ReservationRecord) -> dict:
    """Detalle de CU14 con nombres visibles, siempre limitado a una empresa."""
    data = _serialize(record)
    data["eventos"] = record.eventos
    data["cliente_nombre"] = db.scalar(select(Cliente.nombre).where(
        Cliente.id == record.cliente_id, Cliente.empresa_id == record.empresa_id,
    ))
    data["sucursal_nombre"] = db.scalar(select(Sucursal.nombre).where(
        Sucursal.id == record.sucursal_id, Sucursal.empresa_id == record.empresa_id,
    ))
    variant_ids = [line["variante_id"] for line in record.lineas]
    records = db.execute(select(VarianteProducto, Producto).join(
        Producto,
        (Producto.id == VarianteProducto.producto_id) &
        (Producto.empresa_id == VarianteProducto.empresa_id),
    ).where(
        VarianteProducto.empresa_id == record.empresa_id,
        VarianteProducto.id.in_(variant_ids),
    )).all()
    names = {
        variant.id: {
            "producto_nombre": product.nombre,
            "talla": variant.talla,
            "color": variant.color,
        } for variant, product in records
    }
    data["lineas"] = [{**line, **names.get(line["variante_id"], {})}
                      for line in record.lineas]
    return data


@router.get("")
def list_attention(
    sucursal_id: int | None = Query(default=None, gt=0),
    codigo: str | None = Query(default=None, max_length=36),
    cliente_id: int | None = Query(default=None, gt=0),
    estado: Literal["CONFIRMADA", "CANCELADA", "VENCIDA", "ATENDIDA", "TODAS"] = "CONFIRMADA",
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    branches = _scope(db, context, sucursal_id)
    expire_due(db, context.empresa_id)
    stmt = select(ReservationRecord).where(
        ReservationRecord.empresa_id == context.empresa_id,
        ReservationRecord.sucursal_id.in_(branches),
    )
    if estado != "TODAS":
        stmt = stmt.where(ReservationRecord.estado == estado)
    if codigo is not None and codigo.strip():
        stmt = stmt.where(ReservationRecord.codigo == codigo.strip().upper())
    if cliente_id is not None:
        stmt = stmt.where(ReservationRecord.cliente_id == cliente_id)
    rows = db.scalars(stmt.order_by(
        ReservationRecord.creada_en.desc()).limit(100)).all()
    # Persistir vencimientos aunque el filtro solicite solo confirmadas.
    db.commit()
    return [_detail(db, row) for row in rows]

@router.get("/{reservation_id}")
def detail_attention(
    reservation_id: UUID,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    expire_due(db, context.empresa_id)
    db.commit()
    record = _find(db, context.empresa_id, reservation_id)
    authorized_branch(db, context, record.sucursal_id)
    return _detail(db, record)


@router.post("/{reservation_id}/entregar")
def deliver_reservation(
    reservation_id: UUID, payload: DeliveryInput, response: Response,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    if not payload.identidad_verificada:
        raise HTTPException(422, "Debes verificar la identidad del cliente antes de entregar.")
    context = lock_tenant_mutation(db, context)
    record = _find(db, context.empresa_id, reservation_id)
    authorized_branch(db, context, record.sucursal_id)

    if record.estado == "ATENDIDA":
        response.status_code = 200
        return _detail(db, record)
    if record.estado != "CONFIRMADA":
        raise HTTPException(409, "La reserva no está confirmada y vigente.")

    if _utc(record.vence_en) <= _now():
        expire_due(db, context.empresa_id)
        db.commit()
        raise HTTPException(409, "La reserva venció; no se entregaron prendas.")

    lines = sorted(record.lineas, key=lambda line: line["variante_id"])
    balances = _balances(db, context.empresa_id, record.sucursal_id,
                         [line["variante_id"] for line in lines])
    for line in lines:
        balance = balances.get(line["variante_id"])
        if (balance is None or balance.cantidad_comprometida < line["cantidad"]
                or balance.cantidad < line["cantidad"]):
            raise HTTPException(409, "Inventario comprometido inconsistente; no se puede entregar.")

    now = utc_now()
    movements: list[str] = []
    for line in lines:
        balance = balances[line["variante_id"]]
        balance.cantidad -= line["cantidad"]
        balance.cantidad_comprometida -= line["cantidad"]
        balance.actualizado_en = now
        movement_id = str(uuid5(NAMESPACE_URL, f"vestinova:cu14:{record.id}:{line['variante_id']}"))
        movements.append(movement_id)
        db.add(MovimientoInventario(
            id=movement_id, empresa_id=context.empresa_id,
            sucursal_id=record.sucursal_id, variante_id=line["variante_id"],
            usuario_id=context.usuario.id, cliente_id=None, tipo="SALIDA",
            clase="MOVIMIENTO", origen_tipo=None, origen_id=None,
            delta=-line["cantidad"], saldo_resultante=balance.cantidad,
            motivo=f"CU14: Entrega reserva {record.codigo}",
        ))
    record.estado = "ATENDIDA"
    record.actualizada_en = now
    record.eventos = [*record.eventos, {
        "estado": "ATENDIDA", "actor": f"PERSONAL:{context.usuario.id}",
        "en": now.isoformat(), "comprobacion": payload.comprobacion,
        "movimientos": movements,
    }]
    record_audit_event(
        db, context, accion="reserva.entregada", entidad="reserva",
        entidad_id=record.id, detalles={"sucursal_id": record.sucursal_id,
        "codigo": record.codigo, "movimientos": movements,
        "verificacion_realizada": True},
    )
    db.commit()
    return _detail(db, record)


@router.post("/{reservation_id}/cancelar")
def cancel_attention(
    reservation_id: UUID, payload: CancellationInput,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    context = lock_tenant_mutation(db, context)
    record = _find(db, context.empresa_id, reservation_id)
    authorized_branch(db, context, record.sucursal_id)
    _cancel(db, record, f"PERSONAL:{context.usuario.id}", motivo=payload.motivo, commit=False)
    record_audit_event(
        db, context, accion="reserva.cancelada_atencion", entidad="reserva",
        entidad_id=record.id, detalles={"sucursal_id": record.sucursal_id, "motivo": payload.motivo},
    )
    db.commit()
    return _detail(db, record)
