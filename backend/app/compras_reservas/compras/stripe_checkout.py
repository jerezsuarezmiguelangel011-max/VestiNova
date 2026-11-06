"""CU09: Stripe Checkout de PRUEBA, webhook verificado y venta transaccional.

No confirma compras por redirecciones del navegador. La orden se registra
únicamente después de un pago verificado y una nueva validación de existencias.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
import stripe

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.compras_reservas.compras.domain import Purchase, PurchaseCommand, PurchaseContext, PurchaseItem, PurchaseLine
from app.compras_reservas.compras.persistence import add_purchase, find_purchase_for_customer
from app.db import Base, get_db
from app.inventario.domain import InventoryKey
from app.models import (
    Cliente, Empresa, Existencia, MovimientoInventario, Producto, SesionCliente,
    Sucursal, VarianteProducto, utc_now,
)
from app.organizacion_empresarial.plans import current_subscription


router = APIRouter(prefix="/api/tiendas/{slug}/compras", tags=["CU09 · Stripe Checkout"])
webhook_router = APIRouter(tags=["CU09 · Stripe webhook"])


class CheckoutAttempt(Base):
    __tablename__ = "checkout_stripe_intentos"
    __table_args__ = (
        UniqueConstraint("stripe_session_id", name="uq_checkout_stripe_session"),
        CheckConstraint("monto_centavos > 0", name="ck_checkout_stripe_monto"),
        CheckConstraint("estado IN ('PENDIENTE', 'PAGO_PENDIENTE', 'CONFIRMADA', 'INCIDENCIA', 'RECHAZADA', 'EXPIRADA')", name="ck_checkout_stripe_estado"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    datos: Mapped[dict] = mapped_column(JSON, nullable=False)
    monto_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aviso: Mapped[str | None] = mapped_column(String(350), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CheckoutLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producto_id: StrictInt = Field(gt=0)
    variante_id: StrictInt = Field(gt=0)
    cantidad: StrictInt = Field(gt=0, le=10000)


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    sucursal_id: StrictInt = Field(gt=0)
    entrega: Literal["RETIRO", "DOMICILIO"]
    direccion: str = Field(default="", max_length=250)
    items: list[CheckoutLine] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_order(self):
        if self.entrega == "DOMICILIO" and len(self.direccion.strip()) < 10:
            raise ValueError("Escribe una dirección de entrega de al menos 10 caracteres.")
        if len({line.variante_id for line in self.items}) != len(self.items):
            raise ValueError("Las variantes de la compra no deben repetirse.")
        return self


class CommercialConflict(Exception):
    pass


def _configuration() -> tuple[str, str] | None:
    secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    signing = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    # El proyecto utiliza exclusivamente transacciones de prueba.
    if not (secret.startswith("sk_test_") and len(secret) > 12
            and signing.startswith("whsec_") and len(signing) > 8):
        return None
    return secret, signing


def _lines(db: Session, company_id: int, branch_id: int, items: list[dict], *, stock: bool) -> tuple[list[dict], int]:
    branch = db.scalar(select(Sucursal).where(
        Sucursal.id == branch_id, Sucursal.empresa_id == company_id, Sucursal.activo.is_(True)))
    if branch is None:
        raise CommercialConflict("La sucursal no pertenece a la empresa seleccionada.")
    quoted = []
    products = []
    for request_item in items:
        product = db.scalar(select(Producto).where(
            Producto.id == request_item["producto_id"],
            Producto.empresa_id == company_id, Producto.activo.is_(True)))
        variant = db.scalar(select(VarianteProducto).where(
            VarianteProducto.id == request_item["variante_id"],
            VarianteProducto.producto_id == request_item["producto_id"],
            VarianteProducto.empresa_id == company_id, VarianteProducto.activo.is_(True)))
        if product is None or variant is None:
            raise CommercialConflict("Una prenda o variante ya no está publicada en esta empresa.")
        products.append(product)
        quoted.append((product, variant, request_item["cantidad"]))
    promotions = active_promotions_for_products(db, products)
    result: list[dict] = []
    amount = 0
    for product, variant, quantity in quoted:
        promo = promotions.get(product.id)
        price = promotional_price(product.precio, promo) if promo else product.precio
        cents = int((price * 100).to_integral_exact())
        if cents <= 0 or cents > 99999999:
            raise CommercialConflict("El precio de una prenda no admite pago electrónico.")
        if stock:
            existence = db.scalar(select(Existencia).where(
                Existencia.empresa_id == company_id,
                Existencia.sucursal_id == branch_id,
                Existencia.variante_id == variant.id).with_for_update())
            if existence is None or existence.cantidad - existence.cantidad_comprometida < quantity:
                raise CommercialConflict("No hay stock disponible suficiente para completar la compra.")
        result.append({
            "producto_id": product.id, "variante_id": variant.id, "nombre": product.nombre,
            "talla": variant.talla, "color": variant.color, "cantidad": quantity,
            "precio_centavos": cents,
        })
        amount += cents * quantity
    if amount <= 0 or amount > 99999999:
        raise CommercialConflict("El total de la compra excede el máximo permitido.")
    return result, amount


def _fingerprint(payload: CheckoutInput) -> str:
    return sha256(payload.model_dump_json(exclude={"id"}).encode()).hexdigest()


def _serialize(attempt: CheckoutAttempt, checkout_url: str | None = None) -> dict:
    return {
        "id": attempt.id, "estado": attempt.estado, "moneda": "BOB",
        "total": f"{Decimal(attempt.monto_centavos) / 100:.2f}",
        "checkout_url": checkout_url,
        "detalle": attempt.aviso,
    }


@router.get("/capacidades")
def capabilities(response: Response):
    response.headers["Cache-Control"] = "no-store"
    ready = _configuration() is not None
    return {"habilitado": ready, "pasarela": "STRIPE_TEST", "detail":
            "Stripe Checkout de prueba disponible." if ready
            else "Stripe aún no está configurado. No se realizarán cobros ni se confirmarán compras."}


@router.post("/checkout", status_code=201)
def create_checkout(
    payload: CheckoutInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    config = _configuration()
    if config is None:
        raise HTTPException(503, "Stripe no está configurado para pagos de prueba.")
    client, _, company = current
    if current_subscription(db, company.id) is None:
        raise HTTPException(403, "La empresa no tiene un plan activo para compras.")
    fingerprint = _fingerprint(payload)
    attempt = db.get(CheckoutAttempt, str(payload.id))
    if attempt is not None:
        if attempt.empresa_id != company.id or attempt.cliente_id != client.id or attempt.huella != fingerprint:
            raise HTTPException(409, "El identificador ya corresponde a otra solicitud.")
        if attempt.estado in ("CONFIRMADA", "INCIDENCIA", "RECHAZADA", "EXPIRADA"):
            return _serialize(attempt)
    else:
        try:
            lines, amount = _lines(db, company.id, payload.sucursal_id,
                                   [item.model_dump() for item in payload.items], stock=True)
        except CommercialConflict as error:
            raise HTTPException(409, str(error)) from None
        attempt = CheckoutAttempt(
            id=str(payload.id), empresa_id=company.id, cliente_id=client.id,
            sucursal_id=payload.sucursal_id, huella=fingerprint,
            datos={"entrega": payload.entrega, "direccion": payload.direccion,
                   "items": lines}, monto_centavos=amount, estado="PENDIENTE")
        db.add(attempt)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "La solicitud de compra ya está siendo procesada.") from None

    # Una repetición con el mismo UUID reutiliza la sesión persistida.
    if attempt.stripe_session_id:
        try:
            existing = stripe.checkout.Session.retrieve(attempt.stripe_session_id, api_key=config[0])
            if existing.status == "open" and existing.url:
                return _serialize(attempt, str(existing.url))
        except stripe.StripeError:
            raise HTTPException(503, "No se pudo consultar la sesión de Stripe.") from None
        return _serialize(attempt)

    base = "http://127.0.0.1:4201"
    try:
        checkout = stripe.checkout.Session.create(
            api_key=config[0], idempotency_key=f"vestinova-cu09-{attempt.id}",
            mode="payment", payment_method_types=["card"], customer_email=client.correo,
            client_reference_id=attempt.id, metadata={"compra_id": attempt.id},
            line_items=[{"price_data": {"currency": "bob", "product_data": {
                "name": f"{line['nombre']} · {line['talla']} / {line['color']}"},
                "unit_amount": line["precio_centavos"]}, "quantity": line["cantidad"]}
                for line in attempt.datos["items"]],
            success_url=f"{base}/catalogo/acciones/compra?checkout={attempt.id}&resultado=retorno",
            cancel_url=f"{base}/catalogo/acciones/compra?checkout={attempt.id}&resultado=cancelado",
        )
    except stripe.StripeError:
        raise HTTPException(503, "Stripe no pudo iniciar el pago; el carrito permanece sin confirmar.") from None
    attempt.stripe_session_id = checkout.id
    attempt.estado = "PAGO_PENDIENTE"
    attempt.actualizado_en = utc_now()
    db.commit()
    return _serialize(attempt, str(checkout.url))


@router.get("/{purchase_id}/estado")
def checkout_status(
    purchase_id: UUID, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    client, _, company = current
    attempt = db.scalar(select(CheckoutAttempt).where(
        CheckoutAttempt.id == str(purchase_id), CheckoutAttempt.cliente_id == client.id,
        CheckoutAttempt.empresa_id == company.id))
    if attempt is None:
        raise HTTPException(404, "No existe esta compra en la cuenta.")
    result = _serialize(attempt)
    if attempt.estado == "CONFIRMADA":
        purchase = find_purchase_for_customer(db, company.id, client.id, purchase_id)
        if purchase:
            result["comprobante"] = {
                "numero": attempt.id, "estado": "CONFIRMADA", "entrega": "PENDIENTE",
                "total": f"{purchase.total:.2f}", "moneda": "BOB",
                "creado_en": purchase.creado_en.isoformat(),
                "items": [{"nombre": line.nombre, "variante_id": line.key.variante_id,
                           "cantidad": line.cantidad, "precio_unitario": f"{line.precio_unitario:.2f}"}
                          for line in purchase.lines],
            }
    return result


def _finish_paid(db: Session, attempt: CheckoutAttempt, payment_intent: str | None) -> None:
    """El bloqueo de intento y stock hace idempotentes los eventos pagados."""
    try:
        items = attempt.datos["items"]
        current, amount = _lines(db, attempt.empresa_id, attempt.sucursal_id, items, stock=True)
        if amount != attempt.monto_centavos or any(
            (a["variante_id"], a["precio_centavos"], a["cantidad"]) !=
            (b["variante_id"], b["precio_centavos"], b["cantidad"])
            for a, b in zip(current, items, strict=True)
        ):
            raise CommercialConflict("El precio o las variantes cambiaron tras el cobro.")
    except CommercialConflict as error:
        attempt.estado = "INCIDENCIA"
        attempt.aviso = f"Pago acreditado sin confirmación comercial: {error}. Se requiere compensación o reembolso."
        attempt.stripe_payment_id = payment_intent
        attempt.actualizado_en = utc_now()
        db.commit()
        return

    command = PurchaseCommand(UUID(attempt.id), tuple(
        PurchaseItem(line["producto_id"], line["cantidad"]) for line in items))
    context = PurchaseContext(attempt.cliente_id, attempt.empresa_id,
                              attempt.cliente_id, attempt.sucursal_id)
    purchase_lines = tuple(PurchaseLine(
        InventoryKey(attempt.empresa_id, attempt.sucursal_id, line["variante_id"]),
        line["producto_id"], line["nombre"], line["cantidad"],
        Decimal(line["precio_centavos"]) / 100) for line in current)
    purchase = Purchase(UUID(attempt.id), context, command.fingerprint, purchase_lines, utc_now())
    for line in current:
        balance = db.scalar(select(Existencia).where(
            Existencia.empresa_id == attempt.empresa_id,
            Existencia.sucursal_id == attempt.sucursal_id,
            Existencia.variante_id == line["variante_id"]).with_for_update())
        balance.cantidad -= line["cantidad"]
        balance.actualizado_en = utc_now()
        db.add(MovimientoInventario(
            id=str(uuid4()), empresa_id=attempt.empresa_id,
            sucursal_id=attempt.sucursal_id, variante_id=line["variante_id"],
            usuario_id=None, cliente_id=attempt.cliente_id, tipo="SALIDA",
            clase="MOVIMIENTO", delta=-line["cantidad"],
            saldo_resultante=balance.cantidad, motivo=f"Compra digital {attempt.id}",
        ))
    add_purchase(db, purchase)
    attempt.estado = "CONFIRMADA"
    attempt.stripe_payment_id = payment_intent
    attempt.actualizado_en = utc_now()
    db.commit()


@webhook_router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    config = _configuration()
    if config is None:
        raise HTTPException(503, "Stripe no está configurado.")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Evento demasiado grande.")
    try:
        event = stripe.Webhook.construct_event(raw, request.headers.get("stripe-signature"), config[1])
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, "Firma de Stripe inválida.") from None
    kind = event["type"]
    if kind not in ("checkout.session.completed", "checkout.session.async_payment_succeeded",
                    "checkout.session.async_payment_failed", "checkout.session.expired"):
        return {"recibido": True}
    obj = event["data"]["object"]
    # Stripe 16 devuelve StripeObject, que no implementa dict.get.
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    ref = obj.get("client_reference_id")
    try:
        attempt_id = str(UUID(str(ref)))
    except (ValueError, TypeError):
        return {"recibido": True}
    attempt = db.scalar(select(CheckoutAttempt).where(
        CheckoutAttempt.id == attempt_id).with_for_update())
    if attempt is None or attempt.stripe_session_id != obj.get("id"):
        # Stripe puede reintentar; nunca confirmar una sesión no asociada.
        raise HTTPException(503, "No se pudo verificar la sesión pendiente.")
    if attempt.estado in ("CONFIRMADA", "INCIDENCIA"):
        return {"recibido": True}
    if kind in ("checkout.session.async_payment_failed", "checkout.session.expired"):
        attempt.estado = "RECHAZADA" if kind.endswith("failed") else "EXPIRADA"
        attempt.actualizado_en = utc_now()
        db.commit()
        return {"recibido": True}
    if obj.get("payment_status") != "paid":
        return {"recibido": True}
    if (obj.get("currency") != "bob" or obj.get("amount_total") != attempt.monto_centavos
            or obj.get("metadata", {}).get("compra_id") != attempt.id):
        attempt.estado = "INCIDENCIA"
        attempt.aviso = "La información del pago no coincide con el pedido. Revisión financiera necesaria."
        attempt.stripe_payment_id = str(obj.get("payment_intent") or "")
        attempt.actualizado_en = utc_now()
        db.commit()
        return {"recibido": True}
    _finish_paid(db, attempt, str(obj.get("payment_intent") or ""))
    return {"recibido": True}
