"""CU15: ventas presenciales en efectivo y comprobante central idempotente.

No utiliza Stripe. Las operaciones offline llegan por CU13, conservan UUID y el
importe capturado. Stock físico, movimientos y comprobante se confirman juntos.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, get_db
from app.models import Cliente, Existencia, MovimientoInventario, Producto, VarianteProducto, Sucursal, utc_now
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, lock_tenant_mutation, require_tenant
from app.organizacion_empresarial.audit import record_audit_event
from app.organizacion_empresarial.plans import current_subscription, subscription_state
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price

router = APIRouter(prefix="/api/admin/caja/ventas", tags=["CU15 · Ventas de contado"])
catalog_router = APIRouter(prefix="/api/admin/caja", tags=["CU15 · Catálogo de caja"])


class CashSale(Base):
    __tablename__ = "ventas_contado_cu15"
    __table_args__ = (
        CheckConstraint("total > 0 AND efectivo >= total AND ROUND(efectivo - total, 2) = cambio", name="ck_cu15_efectivo"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("administradores.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    lineas: Mapped[list] = mapped_column(JSON, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    efectivo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cambio: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    creada_local_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entrega_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SyncIncident(Base):
    __tablename__ = "conflictos_cu13"
    __table_args__ = (UniqueConstraint("empresa_id", "tipo", "operacion_id", name="uq_cu13_tipo_operacion_empresa"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("administradores.id"), nullable=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    operacion_id: Mapped[str] = mapped_column(String(36), nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    datos_originales: Mapped[dict] = mapped_column(JSON, nullable=False)
    motivo: Mapped[str] = mapped_column(String(350), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="CONFLICTO")
    decision: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observacion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("administradores.id"), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CashLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variante_id: StrictInt = Field(gt=0)
    cantidad: StrictInt = Field(gt=0, le=100)
    precio_unitario: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CashInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    sucursal_id: StrictInt = Field(gt=0)
    cliente_id: StrictInt | None = Field(default=None, gt=0)
    lineas: list[CashLine] = Field(min_length=1, max_length=30)
    efectivo: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    origen: Literal["EN_LINEA", "WEB_OFFLINE", "MOVIL_OFFLINE"] = "EN_LINEA"
    creada_local_en: datetime | None = None
    efectivo_cobrado: bool = False
    entrega_local: bool = False

    @model_validator(mode="after")
    def unique(self):
        if len(set(line.variante_id for line in self.lineas)) != len(self.lineas):
            raise ValueError("No se admite repetir variantes dentro de una venta.")
        if self.origen == "EN_LINEA" and (self.efectivo_cobrado or self.entrega_local):
            raise ValueError("El cobro offline solo aplica a operaciones locales.")
        if self.entrega_local and not self.efectivo_cobrado:
            raise ValueError("Registra el cobro local antes de documentar la entrega.")
        return self


def _price(value: Decimal) -> str:
    return f"{value:.2f}"


def _staff(context: TenantContext) -> None:
    if context.acceso is None or context.acceso.codigo_sistema not in {"CAJERO", "ENCARGADO_SUCURSAL"}:
        raise HTTPException(403, "Se requiere perfil Cajero o Encargado autorizado.")


def _hash(context: TenantContext, payload: CashInput) -> str:
    data = {
        "empresa_id": context.empresa_id, "usuario_id": context.usuario.id,
        "sucursal_id": payload.sucursal_id,
        "cliente_id": payload.cliente_id, "lineas": sorted(
            (row.variante_id, row.cantidad, _price(row.precio_unitario)) for row in payload.lineas),
        "efectivo": _price(payload.efectivo), "origen": payload.origen,
        "efectivo_cobrado": payload.efectivo_cobrado, "entrega_local": payload.entrega_local,
    }
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sale_response(sale: CashSale) -> dict:
    return {
        "id": sale.id, "codigo": sale.codigo, "estado": "CONFIRMADA",
        "empresa_id": sale.empresa_id, "sucursal_id": sale.sucursal_id,
        "cliente_id": sale.cliente_id, "lineas": sale.lineas,
        "total": _price(sale.total), "efectivo": _price(sale.efectivo),
        "cambio": _price(sale.cambio), "origen": sale.origen,
        "confirmada_en": sale.confirmada_en.isoformat(),
    }


def _incident_response(row: SyncIncident) -> dict:
    return {"id": row.id, "operacion_id": row.operacion_id, "tipo": row.tipo,
            "estado": row.estado, "motivo": row.motivo,
            "sucursal_id": row.sucursal_id, "creada_en": row.creada_en.isoformat(),
            "decision": row.decision, "observacion": row.observacion,
            "responsable_id": row.responsable_id,
            "resuelta_en": row.resuelta_en.isoformat() if row.resuelta_en else None}


def _conflict(db: Session, context: TenantContext, payload: CashInput,
              fingerprint: str, message: str) -> None:
    """Registra el conflicto offline sin tocar inventario ni reescribir el cobro."""
    message = message[:350]
    if payload.origen != "EN_LINEA":
        row = db.scalar(select(SyncIncident).where(
            SyncIncident.empresa_id == context.empresa_id,
            SyncIncident.tipo == "VENTA_CONTADO",
            SyncIncident.operacion_id == str(payload.id),
        ).with_for_update())
        if row is None:
            row = SyncIncident(
                id=str(uuid4()), empresa_id=context.empresa_id,
                sucursal_id=payload.sucursal_id, usuario_id=context.usuario.id,
                cliente_id=None, tipo="VENTA_CONTADO", operacion_id=str(payload.id), huella=fingerprint,
                datos_originales=payload.model_dump(mode="json"), motivo=message, estado="CONFLICTO",
            )
            db.add(row)
        elif row.huella != fingerprint:
            raise HTTPException(409, "UUID ya registrado con contenido distinto.")
        db.commit()
        raise HTTPException(409, {"mensaje": message, "incidencia_id": row.id})
    raise HTTPException(409, message)


def _check_subscription(db: Session, company_id: int) -> None:
    plan = current_subscription(db, company_id)
    if plan is None or not plan[1].activo or subscription_state(plan[0]) != "ACTIVA":
        raise HTTPException(409, "El plan de la empresa no permite nuevas ventas en este momento.")


def _effective_prices(db: Session, context: TenantContext, variants: list[int]):
    records = db.execute(select(VarianteProducto, Producto).join(
        Producto, (Producto.id == VarianteProducto.producto_id) &
                  (Producto.empresa_id == VarianteProducto.empresa_id)
    ).where(
        VarianteProducto.empresa_id == context.empresa_id,
        VarianteProducto.id.in_(variants),
        VarianteProducto.activo.is_(True), Producto.activo.is_(True),
    )).all()
    if {v.id for v, _ in records} != set(variants):
        raise HTTPException(422, "Una variante no pertenece a una prenda activa de esta empresa.")
    products = {p.id: p for _, p in records}
    promos = active_promotions_for_products(db, list(products.values()))
    return {
        v.id: (v, p, promotional_price(p.precio, promos[p.id]) if p.id in promos else p.precio)
        for v, p in records
    }


@catalog_router.get("/catalogo")
def catalog_for_cash(
    sucursal_id: int = Query(gt=0),
    limit: int = Query(default=100, ge=1, le=300),
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    authorized_branch(db, context, sucursal_id)
    rows = db.execute(select(VarianteProducto, Producto).join(
        Producto, (Producto.id == VarianteProducto.producto_id) &
                  (Producto.empresa_id == VarianteProducto.empresa_id)
    ).where(
        VarianteProducto.empresa_id == context.empresa_id,
        VarianteProducto.activo.is_(True), Producto.activo.is_(True),
    ).order_by(VarianteProducto.id).limit(limit)).all()
    promos = active_promotions_for_products(db, list({p.id: p for _, p in rows}.values()))
    return {"empresa_id": context.empresa_id, "sucursal_id": sucursal_id,
            "descargado_en": utc_now().isoformat(), "items": [
        {"variante_id": v.id, "producto_id": p.id, "nombre": p.nombre,
         "talla": v.talla, "color": v.color,
         "precio_unitario": _price(promotional_price(p.precio, promos[p.id])
                                    if p.id in promos else p.precio)}
        for v, p in rows]}


@router.post("", status_code=201)
def create_cash_sale(
    payload: CashInput, response: Response,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    context = lock_tenant_mutation(db, context)
    authorized_branch(db, context, payload.sucursal_id)
    fingerprint = _hash(context, payload)
    previous = db.get(CashSale, str(payload.id))
    if previous:
        if previous.empresa_id != context.empresa_id or previous.huella != fingerprint:
            raise HTTPException(409, "UUID de venta utilizado con datos diferentes.")
        response.status_code = 200
        return _sale_response(previous)

    incident = db.scalar(select(SyncIncident).where(
        SyncIncident.empresa_id == context.empresa_id, SyncIncident.tipo == "VENTA_CONTADO",
        SyncIncident.operacion_id == str(payload.id)))
    if incident:
        if incident.huella != fingerprint:
            raise HTTPException(409, "UUID ya utilizado con otra venta.")
        raise HTTPException(409, {"mensaje": incident.motivo, "incidencia_id": incident.id})

    _check_subscription(db, context.empresa_id)
    if payload.cliente_id is not None and db.scalar(select(Cliente.id).where(
        Cliente.id == payload.cliente_id, Cliente.empresa_id == context.empresa_id,
        Cliente.activo.is_(True))) is None:
        raise HTTPException(422, "Cliente no válido para esta empresa.")
    prices = _effective_prices(db, context, [item.variante_id for item in payload.lineas])

    # La captura original del efectivo y los precios locales no se alteran.
    mismatch = [item.variante_id for item in payload.lineas
                if item.precio_unitario != prices[item.variante_id][2]]
    if mismatch:
        _conflict(db, context, payload, fingerprint,
                  "Los precios capturados no coinciden con el precio central: "
                  + ", ".join(str(i) for i in mismatch))

    total = sum((item.precio_unitario * item.cantidad for item in payload.lineas), Decimal("0.00"))
    if payload.efectivo < total:
        raise HTTPException(422, "El efectivo recibido no cubre el total.")

    # Bloqueo ordenado por variante y comprobación de stock libre.
    balances = {row.variante_id: row for row in db.scalars(
        select(Existencia).where(
            Existencia.empresa_id == context.empresa_id,
            Existencia.sucursal_id == payload.sucursal_id,
            Existencia.variante_id.in_([item.variante_id for item in payload.lineas]),
        ).order_by(Existencia.variante_id).with_for_update()).all()}
    shortages = []
    for item in payload.lineas:
        row = balances.get(item.variante_id)
        available = max(0, row.cantidad - row.cantidad_comprometida) if row else 0
        if available < item.cantidad:
            shortages.append({"variante_id": item.variante_id, "disponible": available,
                              "solicitado": item.cantidad})
    if shortages:
        _conflict(db, context, payload, fingerprint,
                  "Stock insuficiente para venta en caja: " + json.dumps(shortages))

    now = utc_now()
    lines = []
    for item in payload.lineas:
        v, product, price = prices[item.variante_id]
        balance = balances[item.variante_id]
        balance.cantidad -= item.cantidad
        balance.actualizado_en = now
        move_id = str(uuid5(NAMESPACE_URL, f"vestinova:cu15:{payload.id}:{item.variante_id}"))
        db.add(MovimientoInventario(
            id=move_id, empresa_id=context.empresa_id, sucursal_id=payload.sucursal_id,
            variante_id=item.variante_id, usuario_id=context.usuario.id, cliente_id=None,
            tipo="SALIDA", clase="MOVIMIENTO", origen_tipo=None, origen_id=None,
            motivo=f"CU15: Venta contado {payload.id}",
            delta=-item.cantidad, saldo_resultante=balance.cantidad,
        ))
        lines.append({"variante_id": item.variante_id, "producto_id": product.id,
                      "nombre": product.nombre, "cantidad": item.cantidad,
                      "precio_unitario": _price(price),
                      "subtotal": _price(price * item.cantidad),
                      "movimiento_id": move_id})
    sale = CashSale(
        id=str(payload.id), empresa_id=context.empresa_id, sucursal_id=payload.sucursal_id,
        usuario_id=context.usuario.id, cliente_id=payload.cliente_id, huella=fingerprint,
        lineas=lines, total=total, efectivo=payload.efectivo,
        cambio=payload.efectivo - total, codigo=f"VN-C-{uuid4().hex[:12].upper()}",
        origen=payload.origen, creada_local_en=payload.creada_local_en,
        entrega_local=payload.entrega_local, confirmada_en=now,
    )
    db.add(sale)
    record_audit_event(db, context, accion="caja.venta_confirmada",
                       entidad="venta_contado", entidad_id=sale.id,
                       detalles={"sucursal_id": sale.sucursal_id, "total": _price(total),
                                 "lineas": len(lines), "origen": sale.origen})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.get(CashSale, str(payload.id))
        if previous and previous.empresa_id == context.empresa_id and previous.huella == fingerprint:
            response.status_code = 200
            return _sale_response(previous)
        # Un fallo de CHECK/FK no significa que se duplicó un UUID.
        # No ocultar una anomalía de integridad como una colisión comercial.
        raise HTTPException(500, "No se pudo registrar la venta por una anomalía de integridad.") from None
    return _sale_response(sale)


@router.get("")
def list_cash_sales(
    sucursal_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    allowed = list(db.scalars(authorized_branches_statement(context).with_only_columns(Sucursal.id)).all())
    if sucursal_id is not None:
        authorized_branch(db, context, sucursal_id)
        allowed = [sucursal_id]
    rows = db.scalars(select(CashSale).where(
        CashSale.empresa_id == context.empresa_id,
        CashSale.sucursal_id.in_(allowed),
    ).order_by(CashSale.confirmada_en.desc()).limit(limit)).all()
    return [_sale_response(row) for row in rows]


@router.get("/{sale_id}")
def detail_cash_sale(
    sale_id: UUID,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    row = db.scalar(select(CashSale).where(
        CashSale.id == str(sale_id), CashSale.empresa_id == context.empresa_id))
    if not row:
        raise HTTPException(404, "Venta no encontrada.")
    authorized_branch(db, context, row.sucursal_id)
    return _sale_response(row)
