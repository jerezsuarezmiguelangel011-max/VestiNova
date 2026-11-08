"""CU09 móvil: tarjeta preparada online y solicitud diferida con cargo Stripe TEST.

No almacena PAN/CVV. Una solicitud enviada desde SQLite NO es pago ni reserva.
Solo el servidor puede iniciar un cargo tras validar precio, tenant y stock.
El UUID y Stripe idempotency_key impiden el doble cobro por reintentos.
"""
from datetime import datetime
from hashlib import sha256
from decimal import Decimal
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
import stripe

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.compras_reservas.compras.stripe_checkout import (
    CheckoutAttempt, CheckoutLine, CommercialConflict, _configuration,
    _finish_paid, _lines, _serialize,
)
from app.db import Base, get_db
from app.models import Cliente, Empresa, SesionCliente, utc_now
from app.organizacion_empresarial.plans import current_subscription, subscription_state

router = APIRouter(prefix="/api/tiendas/{slug}/compras/offline",
                   tags=["CU09 · Compra móvil diferida Stripe TEST"])


class MetodoDiferido(Base):
    __tablename__ = "cu09_metodos_diferidos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "cliente_id", name="uq_cu09_metodo_empresa_cliente"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    setup_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CompraDiferidaInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    sucursal_id: StrictInt = Field(gt=0)
    entrega: str = Field(pattern="^(RETIRO|DOMICILIO)$")
    direccion: str = Field(default="", max_length=250)
    items: list[CheckoutLine] = Field(min_length=1, max_length=30)
    importe_aceptado_centavos: StrictInt = Field(gt=0, le=99999999)
    autoriza_cobro_diferido: bool = Field(strict=True)
    creado_local_en: datetime

    @model_validator(mode="after")
    def validacion(self):
        if not self.autoriza_cobro_diferido:
            raise ValueError("La autorización expresa del cargo diferido es obligatoria.")
        if self.entrega == "DOMICILIO" and len(self.direccion.strip()) < 10:
            raise ValueError("La dirección de domicilio debe contener al menos 10 caracteres.")
        if len(set(x.variante_id for x in self.items)) != len(self.items):
            raise ValueError("No repitas variantes.")
        if self.creado_local_en.tzinfo is None:
            raise ValueError("creado_local_en requiere zona horaria.")
        return self


def _stripe() -> str:
    config = _configuration()
    if not config:
        raise HTTPException(503, "Stripe TEST no está disponible: no se cobrará la compra.")
    return config[0]


def _row(db: Session, company: Empresa, customer: Cliente) -> MetodoDiferido | None:
    return db.scalar(select(MetodoDiferido).where(
        MetodoDiferido.empresa_id == company.id,
        MetodoDiferido.cliente_id == customer.id,
    ).with_for_update())


def _verify_method(db: Session, row: MetodoDiferido | None, key: str) -> tuple[str, str] | None:
    if row is None:
        return None
    if row.setup_session_id and not row.payment_method_id:
        try:
            session = stripe.checkout.Session.retrieve(row.setup_session_id, api_key=key)
            if session.status == "complete" and session.mode == "setup" and session.customer == row.stripe_customer_id:
                intent = stripe.SetupIntent.retrieve(session.setup_intent, api_key=key)
                if intent.status == "succeeded" and intent.customer == row.stripe_customer_id and intent.payment_method:
                    row.payment_method_id = str(intent.payment_method)
                    row.actualizado_en = utc_now()
                    db.commit()
        except stripe.StripeError:
            # Sin comprobación de Stripe no se declara una tarjeta autorizada nueva.
            return None
    if not row.payment_method_id:
        return None
    try:
        method = stripe.PaymentMethod.retrieve(row.payment_method_id, api_key=key)
    except stripe.StripeError:
        return None
    if method.customer != row.stripe_customer_id or method.type != "card":
        return None
    return str(method.card.brand), str(method.card.last4)


@router.get("/metodo")
def estado_metodo(
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    row = _row(db, company, customer)
    if _configuration() is None:
        return {"preparado": False, "stripe_test": False, "detalle": "Stripe TEST sin configurar."}
    card = _verify_method(db, row, _stripe())
    return {"preparado": card is not None, "stripe_test": True,
            "marca": card[0] if card else None, "ultimos4": card[1] if card else None}


@router.post("/preparar-metodo")
def preparar_metodo(
    request: Request, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    """Setup Checkout se abre exclusivamente con conexión y aceptación expresa."""
    response.headers["Cache-Control"] = "no-store"
    key = _stripe()
    customer, _, company = current
    row = _row(db, company, customer)
    if row is None:
        try:
            remote = stripe.Customer.create(api_key=key, email=customer.correo,
                                            metadata={"empresa_id": str(company.id),
                                                      "cliente_id": str(customer.id)})
        except stripe.StripeError:
            raise HTTPException(503, "No se pudo preparar Stripe.") from None
        row = MetodoDiferido(empresa_id=company.id, cliente_id=customer.id,
                            stripe_customer_id=remote.id)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "La vinculación ya está en curso.") from None
    origin = str(request.base_url).rstrip("/")
    route = f"{origin}/api/tiendas/{company.slug}/compras/offline/retorno"
    try:
        setup = stripe.checkout.Session.create(
            api_key=key, mode="setup", customer=row.stripe_customer_id,
            success_url=route + "?resultado=preparado",
            cancel_url=route + "?resultado=cancelado",
            metadata={"empresa_id": str(company.id), "cliente_id": str(customer.id)},
        )
    except stripe.StripeError:
        raise HTTPException(503, "No se pudo abrir el registro seguro de tarjeta en Stripe.") from None
    row.setup_session_id = setup.id
    row.payment_method_id = None  # Nueva autorización invalida la anterior para uso automático.
    row.actualizado_en = utc_now()
    db.commit()
    return {"checkout_url": str(setup.url), "estado": "PENDIENTE",
            "detalle": "La tarjeta solo se considera preparada tras confirmación de Stripe."}


@router.get("/retorno", response_class=HTMLResponse)
def retorno(resultado: str = ""):
    """Página estática; nunca acredita pagos ni habilita tarjetas por una URL."""
    mensaje = ("Vuelve a VestiNova y pulsa Verificar tarjeta."
               if resultado == "preparado" else
               "No se completó la preparación. Vuelve a VestiNova.")
    return HTMLResponse("<!doctype html><html lang='es'><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width'>"
                        "<h2>VestiNova · Stripe TEST</h2><p>" + mensaje + "</p></html>")


def _serializar(attempt: CheckoutAttempt) -> dict:
    return {**_serialize(attempt), "es_diferida": True,
            "pago_verificado": attempt.estado == "CONFIRMADA",
            "reserva_confirmada": False,
            "detalle": attempt.aviso or "Consulta el estado antes de asumir un cobro."}


@router.post("/sincronizar")
def sincronizar_compra(
    payload: CompraDiferidaInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    key = _stripe()
    customer, _, company = current
    subscription = current_subscription(db, company.id)
    if not subscription or not subscription[1].activo or subscription_state(subscription[0]) != "ACTIVA":
        raise HTTPException(403, "La empresa no tiene suscripción de compras activa.")
    signature = sha256(json.dumps(payload.model_dump(mode="json", exclude={"id"}),
                                   sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    attempt = db.scalar(select(CheckoutAttempt).where(
        CheckoutAttempt.id == str(payload.id)).with_for_update())
    if attempt:
        if (attempt.empresa_id != company.id or attempt.cliente_id != customer.id
                or attempt.huella != signature or not attempt.datos.get("movil_diferido")):
            raise HTTPException(409, "El UUID pertenece a otra solicitud.")
        if attempt.estado in ("CONFIRMADA", "INCIDENCIA", "RECHAZADA", "EXPIRADA"):
            return _serializar(attempt)
    else:
        row = _row(db, company, customer)
        if not _verify_method(db, row, key):
            raise HTTPException(409, "Prepara y autoriza una tarjeta en Stripe antes de cobrar.")
        try:
            lines, amount = _lines(db, company.id, payload.sucursal_id,
                                   [line.model_dump() for line in payload.items], stock=True)
        except CommercialConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if amount != payload.importe_aceptado_centavos:
            raise HTTPException(409, "Cambió el precio de la compra. Revisa y autoriza el nuevo importe.")
        attempt = CheckoutAttempt(
            id=str(payload.id), empresa_id=company.id, cliente_id=customer.id,
            sucursal_id=payload.sucursal_id, huella=signature,
            datos={"entrega": payload.entrega, "direccion": payload.direccion,
                   "items": lines, "movil_diferido": True},
            monto_centavos=amount, estado="PENDIENTE",
        )
        db.add(attempt)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "La compra ya está siendo sincronizada.") from None
    if attempt.estado == "PAGO_PENDIENTE" and attempt.stripe_payment_id:
        try:
            payment = stripe.PaymentIntent.retrieve(attempt.stripe_payment_id, api_key=key)
        except stripe.StripeError:
            raise HTTPException(503, "No se verificó el pago anterior; se conserva pendiente.") from None
        if payment.status == "succeeded":
            _finish_paid(db, attempt, str(payment.id))
        else:
            attempt.aviso = "Stripe requiere seguimiento o autenticación del cliente."
            db.commit()
        return _serializar(attempt)
    if attempt.estado == "PAGO_PENDIENTE":
        # El primer intento pudo quedar ambiguo; el mismo UUID es obligatorio.
        pass
    row = _row(db, company, customer)
    if not _verify_method(db, row, key):
        raise HTTPException(409, "La tarjeta autorizada dejó de estar disponible.")
    try:
        # Revalidación justo antes del cobro, incluso para reintentos.
        fresh, total = _lines(db, company.id, attempt.sucursal_id,
                              attempt.datos["items"], stock=True)
        if total != attempt.monto_centavos:
            raise CommercialConflict("Precio o disponibilidad cambiaron; no se realiza cargo.")
    except CommercialConflict as exc:
        attempt.estado = "RECHAZADA"
        attempt.aviso = str(exc)
        db.commit()
        return _serializar(attempt)
    attempt.estado = "PAGO_PENDIENTE"
    db.commit()
    try:
        payment = stripe.PaymentIntent.create(
            api_key=key, idempotency_key=f"vestinova-offline-cu09-{attempt.id}",
            amount=attempt.monto_centavos, currency="bob",
            customer=row.stripe_customer_id, payment_method=row.payment_method_id,
            confirm=True, off_session=True,
            metadata={"compra_id": attempt.id, "empresa_id": str(company.id)},
        )
    except stripe.CardError:
        attempt.estado = "RECHAZADA"
        attempt.aviso = "La tarjeta rechazó el cargo o requiere autenticación adicional. No hay compra confirmada."
        db.commit()
        return _serializar(attempt)
    except stripe.StripeError:
        # No afirmar que Stripe NO cobró: conservar UUID para conciliación segura.
        raise HTTPException(503, "No se pudo verificar Stripe; conserva el mismo UUID y reintenta.") from None
    attempt.stripe_payment_id = str(payment.id)
    if payment.status == "succeeded":
        _finish_paid(db, attempt, str(payment.id))
    else:
        attempt.aviso = "Pago pendiente o requiere autenticación. No se confirmó la compra."
        db.commit()
    return _serializar(attempt)
