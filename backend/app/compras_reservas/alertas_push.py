"""CU26: avisos Web Push de reposición con aislamiento, consentimiento y cola duradera."""
from datetime import datetime
from hashlib import sha256
import json
import logging
import re
import os
from urllib.parse import urlsplit
from dotenv import dotenv_values
from app.config import BACKEND_ROOT

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.db import Base, get_db
from app.models import Cliente, Empresa, Existencia, Producto, SesionCliente, Sucursal, VarianteProducto, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/alertas-push", tags=["CU26 · Alertas de reposición"])


class PushChannel(Base):
    __tablename__ = "canales_push_cliente"
    __table_args__ = (
        UniqueConstraint("empresa_id", "cliente_id", "endpoint_sha", name="uq_cu26_canal_cliente_endpoint"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    endpoint_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    clave_publica: Mapped[str] = mapped_column(String(256), nullable=False)
    clave_auth: Mapped[str] = mapped_column(String(256), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AlertaReposicion(Base):
    __tablename__ = "alertas_reposicion"
    __table_args__ = (
        ForeignKeyConstraint(["variante_id", "empresa_id"],
                             ["variantes_producto.id", "variantes_producto.empresa_id"],
                             name="fk_cu26_alerta_variante_tenant"),
        ForeignKeyConstraint(["sucursal_id", "empresa_id"],
                             ["sucursales.id", "sucursales.empresa_id"],
                             name="fk_cu26_alerta_sucursal_tenant"),
        UniqueConstraint("empresa_id", "cliente_id", "variante_id", "sucursal_id",
                         name="uq_cu26_alerta_cliente_variante_sucursal"),
        CheckConstraint("estado IN ('ACTIVA', 'CANCELADA')", name="ck_cu26_alerta_estado"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    variante_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="ACTIVA")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PushOutbox(Base):
    __tablename__ = "avisos_push_reposicion"
    __table_args__ = (
        UniqueConstraint("alerta_id", "movimiento_id", "canal_id", name="uq_cu26_aviso_evento_canal"),
        CheckConstraint("estado IN ('PENDIENTE', 'ENVIADO', 'REVOCADO', 'ERROR', 'CANCELADO')", name="ck_cu26_aviso_estado"),
        Index("ix_cu26_aviso_pendiente", "estado", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    alerta_id: Mapped[int] = mapped_column(ForeignKey("alertas_reposicion.id"), nullable=False)
    canal_id: Mapped[int] = mapped_column(ForeignKey("canales_push_cliente.id"), nullable=False)
    movimiento_id: Mapped[str] = mapped_column(String(36), nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDIENTE")
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auth: str = Field(min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_-]+={0,2}$")
    p256dh: str = Field(min_length=40, max_length=256, pattern=r"^[A-Za-z0-9_-]+={0,2}$")


class ChannelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(min_length=25, max_length=2048)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        # Impedir SSRF: nunca realizar solicitudes a hosts, IP o puertos arbitrarios.
        trusted = (
            host == "fcm.googleapis.com" or host == "updates.push.services.mozilla.com"
            or host == "web.push.apple.com" or host == "webpush.push.apple.com"
            or host.endswith(".notify.windows.com")
        )
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443) or parts.fragment or not parts.path or not trusted:
            raise ValueError("Servidor Web Push no autorizado.")
        return value


class NativeChannelInput(BaseModel):
    """Un token FCM debe ser enviado por una app cliente autenticada."""
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=30, max_length=1700,
                       pattern=r"^[A-Za-z0-9_:~.\-]+$")


def _fcm_credentials() -> str | None:
    values = dotenv_values(BACKEND_ROOT / ".env", interpolate=False)
    path = (os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE") or
            values.get("FIREBASE_SERVICE_ACCOUNT_FILE") or "").strip()
    return path if path and os.path.isfile(path) else None


def _send_fcm(channel, payload):
    """Nunca incluir el token privado en logs, errores o respuestas HTTP."""
    import firebase_admin
    from firebase_admin import credentials, messaging
    config = _fcm_credentials()
    if not config:
        raise RuntimeError("FCM sin credenciales")
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials.Certificate(config))
    notification = payload["notification"]
    path = notification.get("data", {}).get("onActionClick", {}).get(
        "default", {}).get("url", "")
    messaging.send(messaging.Message(
        token=channel.endpoint[4:],
        notification=messaging.Notification(
            title=notification["title"], body=notification["body"]),
        data={"ruta": path},
        android=messaging.AndroidConfig(priority="high")), app=app)


class AlertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variante_id: StrictInt = Field(gt=0)
    sucursal_id: StrictInt = Field(gt=0)


def _alert_json(record: AlertaReposicion) -> dict:
    return {
        "id": record.id, "variante_id": record.variante_id, "sucursal_id": record.sucursal_id,
        "estado": record.estado, "creado_en": record.creado_en.isoformat(),
    }


def push_enabled(settings) -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key and
                settings.vapid_contact.startswith("mailto:"))


@router.get("/config")
def push_config(request: Request, response: Response,
                current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session)):
    response.headers["Cache-Control"] = "no-store"
    settings = request.app.state.settings
    enabled = push_enabled(settings)
    return {"habilitado": enabled, "vapid_public_key": settings.vapid_public_key if enabled else None,
            "movil_habilitado": _fcm_credentials() is not None}


@router.post("/canales", status_code=201)
def register_channel(
    payload: ChannelInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    endpoint_sha = sha256(payload.endpoint.encode("utf-8")).hexdigest()
    record = db.scalar(select(PushChannel).where(
        PushChannel.empresa_id == company.id, PushChannel.cliente_id == customer.id,
        PushChannel.endpoint_sha == endpoint_sha,
    ))
    if record:
        record.activo = True
        record.clave_publica = payload.keys.p256dh
        record.clave_auth = payload.keys.auth
        response.status_code = 200
    else:
        record = PushChannel(
            empresa_id=company.id, cliente_id=customer.id, endpoint_sha=endpoint_sha,
            endpoint=payload.endpoint, clave_publica=payload.keys.p256dh, clave_auth=payload.keys.auth,
        )
        db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Canal de notificación registrado concurrentemente.") from None
    return {"id": record.id, "activo": True}


@router.post("/canales-movil", status_code=201)
def register_native_channel(
    payload: NativeChannelInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    """Registra un canal Android FCM. Nunca crea una suscripción sin permiso."""
    response.headers["Cache-Control"] = "no-store"
    if _fcm_credentials() is None:
        raise HTTPException(503, "FCM móvil todavía no está configurado en este servidor.")
    customer, _, company = current
    endpoint = "fcm:" + payload.token
    digest = sha256(endpoint.encode("utf-8")).hexdigest()
    record = db.scalar(select(PushChannel).where(
        PushChannel.empresa_id == company.id,
        PushChannel.cliente_id == customer.id,
        PushChannel.endpoint_sha == digest,
    ))
    if record:
        record.activo = True
        response.status_code = 200
    else:
        record = PushChannel(
            empresa_id=company.id, cliente_id=customer.id,
            endpoint_sha=digest, endpoint=endpoint,
            clave_publica="FCM_NATIVE", clave_auth="FCM_NATIVE",
        )
        db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El canal ya fue registrado.") from None
    return {"id": record.id, "activo": True, "tipo": "FCM"}


@router.get("/avisos")
def list_alerts(
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    # Incluir nombres públicos para que el cliente no vea identificadores técnicos.
    # LEFT JOIN conserva las alertas incluso si una prenda fue despublicada.
    rows = db.execute(
        select(AlertaReposicion, VarianteProducto, Producto, Sucursal)
        .outerjoin(VarianteProducto,
            (VarianteProducto.id == AlertaReposicion.variante_id) &
            (VarianteProducto.empresa_id == AlertaReposicion.empresa_id))
        .outerjoin(Producto,
            (Producto.id == VarianteProducto.producto_id) &
            (Producto.empresa_id == AlertaReposicion.empresa_id))
        .outerjoin(Sucursal,
            (Sucursal.id == AlertaReposicion.sucursal_id) &
            (Sucursal.empresa_id == AlertaReposicion.empresa_id))
        .where(
            AlertaReposicion.empresa_id == company.id,
            AlertaReposicion.cliente_id == customer.id,
            AlertaReposicion.estado == "ACTIVA",
        )
        .order_by(AlertaReposicion.creado_en.desc()).limit(100)
    ).all()
    return {"items": [
        {
            **_alert_json(alert),
            "producto_nombre": product.nombre if product else None,
            "producto_slug": product.slug if product and product.activo else None,
            "talla": variant.talla if variant else None,
            "color": variant.color if variant else None,
            "sucursal_nombre": branch.nombre if branch else None,
        }
        for alert, variant, product, branch in rows
    ]}


@router.post("/avisos", status_code=201)
def subscribe_alert(
    payload: AlertInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    channels = db.scalar(select(PushChannel.id).where(
        PushChannel.empresa_id == company.id, PushChannel.cliente_id == customer.id,
        PushChannel.activo.is_(True),
    ).limit(1))
    if not channels:
        raise HTTPException(409, "Autoriza y registra un navegador compatible para recibir notificaciones.")
    variant = db.scalar(select(VarianteProducto).join(
        Producto, (Producto.id == VarianteProducto.producto_id) &
                  (Producto.empresa_id == VarianteProducto.empresa_id)
    ).where(
        VarianteProducto.id == payload.variante_id,
        VarianteProducto.empresa_id == company.id, VarianteProducto.activo.is_(True),
        Producto.activo.is_(True),
    ))
    branch = db.scalar(select(Sucursal).where(
        Sucursal.id == payload.sucursal_id, Sucursal.empresa_id == company.id, Sucursal.activo.is_(True),
    ))
    if variant is None or branch is None:
        raise HTTPException(404, "Variante o sucursal no disponible en esta tienda.")
    # Un saldo no registrado no equivale a agotado: se exige confirmación central.
    balance = db.scalar(select(Existencia).where(
        Existencia.empresa_id == company.id, Existencia.sucursal_id == branch.id,
        Existencia.variante_id == variant.id,
    ).with_for_update())
    if balance is None:
        raise HTTPException(409, "La disponibilidad de esta variante aún no está verificada.")
    if balance.cantidad > balance.cantidad_comprometida:
        raise HTTPException(409, "Esta variante ya está disponible; no requiere aviso.")
    old = db.scalar(select(AlertaReposicion).where(
        AlertaReposicion.empresa_id == company.id, AlertaReposicion.cliente_id == customer.id,
        AlertaReposicion.variante_id == variant.id, AlertaReposicion.sucursal_id == branch.id,
    ).with_for_update())
    if old:
        if old.estado == "ACTIVA":
            raise HTTPException(409, "Ya tienes una alerta activa para esta variante y sucursal.")
        old.estado = "ACTIVA"
        old.actualizado_en = utc_now()
        alert = old
    else:
        alert = AlertaReposicion(empresa_id=company.id, cliente_id=customer.id,
                                variante_id=variant.id, sucursal_id=branch.id)
        db.add(alert)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La alerta ya estaba registrada.") from None
    return _alert_json(alert)


@router.delete("/avisos/{alerta_id}", status_code=204)
def cancel_alert(
    alerta_id: int,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    customer, _, company = current
    row = db.scalar(select(AlertaReposicion).where(
        AlertaReposicion.id == alerta_id,
        AlertaReposicion.empresa_id == company.id,
        AlertaReposicion.cliente_id == customer.id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Alerta no encontrada en esta cuenta.")
    row.estado = "CANCELADA"
    row.actualizado_en = utc_now()
    db.commit()
    return Response(status_code=204)


def queue_restock(db: Session, *, empresa_id: int, sucursal_id: int, variante_id: int,
                  previous_free: int, current_free: int, movement_id: str) -> None:
    """Agregar eventos en la MISMA transacción del inventario; no comunicar antes del commit."""
    if previous_free > 0 or current_free <= 0:
        return
    alerts = db.scalars(select(AlertaReposicion).where(
        AlertaReposicion.empresa_id == empresa_id, AlertaReposicion.sucursal_id == sucursal_id,
        AlertaReposicion.variante_id == variante_id, AlertaReposicion.estado == "ACTIVA",
    )).all()
    for alert in alerts:
        channels = db.scalars(select(PushChannel).where(
            PushChannel.empresa_id == empresa_id, PushChannel.cliente_id == alert.cliente_id,
            PushChannel.activo.is_(True),
        )).all()
        for channel in channels:
            exists = db.scalar(select(PushOutbox.id).where(
                PushOutbox.alerta_id == alert.id, PushOutbox.movimiento_id == movement_id,
                PushOutbox.canal_id == channel.id,
            ))
            if exists is None:
                db.add(PushOutbox(empresa_id=empresa_id, alerta_id=alert.id,
                                  canal_id=channel.id, movimiento_id=movement_id))


def _send_webpush(channel: PushChannel, payload: dict, settings) -> None:
    if channel.endpoint.startswith("fcm:"):
        _send_fcm(channel, payload)
        return
    from pywebpush import webpush
    webpush(
        subscription_info={"endpoint": channel.endpoint,
                           "keys": {"p256dh": channel.clave_publica, "auth": channel.clave_auth}},
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_contact},
        ttl=86400,
    )


def dispatch_pending(session_factory, settings) -> None:
    """Lote reintentable. Error de red jamás revierte el inventario ni revela secretos."""
    if not push_enabled(settings) and _fcm_credentials() is None:
        return
    with session_factory() as db:
        jobs = db.scalars(select(PushOutbox).where(
            PushOutbox.estado == "PENDIENTE",
        ).order_by(PushOutbox.id).limit(40).with_for_update(skip_locked=True)).all()
        for job in jobs:
            alert = db.get(AlertaReposicion, job.alerta_id)
            channel = db.get(PushChannel, job.canal_id)
            if alert is None or channel is None or alert.estado != "ACTIVA" or not channel.activo:
                job.estado = "CANCELADO"
                continue
            # No agotar los reintentos de un canal cuyo proveedor aún no
            # está configurado. Conservar el aviso PENDIENTE para más tarde.
            if channel.endpoint.startswith("fcm:"):
                if _fcm_credentials() is None:
                    continue
            elif not push_enabled(settings):
                continue
            variant = db.get(VarianteProducto, alert.variante_id)
            product = db.get(Producto, variant.producto_id) if variant else None
            branch = db.get(Sucursal, alert.sucursal_id)
            company = db.get(Empresa, alert.empresa_id)
            if not product or not product.activo or not variant or not variant.activo or not branch or not branch.activo or not company:
                job.estado = "CANCELADO"
                continue
            free = db.get(Existencia, (alert.empresa_id, alert.sucursal_id, alert.variante_id))
            if free is None or free.cantidad <= free.cantidad_comprometida:
                job.estado = "CANCELADO"
                continue
            payload = {"notification": {
                "title": "VestiNova · Prenda repuesta",
                "body": product.nombre + " vuelve a estar disponible en " + branch.nombre,
                "tag": "reposicion-" + str(job.id),
                "data": {"onActionClick": {"default": {
                    "operation": "navigateLastFocusedOrOpen",
                    "url": "/tienda/" + company.slug + "/prenda/" + product.slug,
                }}},
            }}
            try:
                _send_webpush(channel, payload, settings)
                job.estado = "ENVIADO"
                job.enviado_en = utc_now()
            except Exception as exc:
                # No registrar endpoint, claves, cuerpo remoto ni datos del navegador.
                status = getattr(exc, "status_code", None)
                job.intentos += 1
                if status in (404, 410):
                    channel.activo = False
                    job.estado = "REVOCADO"
                elif job.intentos >= 3:
                    job.estado = "ERROR"
                logger.warning("CU26: envío de evento %s no confirmado (intento %s)", job.id, job.intentos)
        db.commit()
