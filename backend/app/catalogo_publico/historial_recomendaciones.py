"""CU19: visitas opcionales y transparentes para recomendaciones del cliente.

Solo se registran vistas posteriores a un consentimiento explícito. Se pueden
desactivar y eliminar los registros en cualquier momento. Sin datos personales
sensibles ni identificación entre distintas tiendas.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.db import Base, get_db
from app.models import Cliente, Empresa, Producto, SesionCliente, utc_now


router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/recomendaciones",
                   tags=["CU19 · Preferencias opcionales del cliente"])


class ConsentimientoCU19(Base):
    __tablename__ = "consentimientos_cu19"
    __table_args__ = (
        ForeignKeyConstraint(["cliente_id", "empresa_id"], ["clientes.id", "clientes.empresa_id"],
                             name="fk_cu19_consentimiento_cliente_empresa"),
    )
    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class VistaCU19(Base):
    __tablename__ = "visitas_prendas_cu19"
    __table_args__ = (
        ForeignKeyConstraint(["cliente_id", "empresa_id"], ["clientes.id", "clientes.empresa_id"],
                             name="fk_cu19_visita_cliente_empresa"),
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"],
                             name="fk_cu19_visita_producto_empresa"),
    )
    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vistas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    vista_reciente_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    habilitado: bool = Field(strict=True)


class ViewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    producto_slug: str = Field(min_length=3, max_length=140, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _consent(db: Session, company_id: int, customer_id: int) -> ConsentimientoCU19 | None:
    return db.get(ConsentimientoCU19, (company_id, customer_id))


@router.get("/preferencias")
def get_preferences(
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    customer, _, company = current
    response.headers["Cache-Control"] = "no-store"
    consent = _consent(db, company.id, customer.id)
    return {"habilitado": bool(consent and consent.habilitado)}


@router.put("/preferencias")
def set_preferences(
    payload: ConsentInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    customer, _, company = current
    consent = _consent(db, company.id, customer.id)
    if consent is None:
        consent = ConsentimientoCU19(empresa_id=company.id, cliente_id=customer.id)
        db.add(consent)
    consent.habilitado = payload.habilitado
    consent.actualizado_en = utc_now()
    if not payload.habilitado:
        db.execute(delete(VistaCU19).where(
            VistaCU19.empresa_id == company.id, VistaCU19.cliente_id == customer.id))
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"habilitado": payload.habilitado, "historial_borrado": not payload.habilitado}


@router.post("/visitas", status_code=202)
def record_view(
    payload: ViewInput, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    customer, _, company = current
    consent = _consent(db, company.id, customer.id)
    if consent is None or not consent.habilitado:
        raise HTTPException(403, "Activa primero la personalización para registrar visitas.")
    product = db.scalar(select(Producto).where(
        Producto.empresa_id == company.id, Producto.slug == payload.producto_slug,
        Producto.activo.is_(True),
    ))
    if product is None:
        raise HTTPException(404, "Prenda no disponible en esta tienda.")
    event = db.get(VistaCU19, (company.id, customer.id, product.id))
    if event is None:
        db.add(VistaCU19(empresa_id=company.id, cliente_id=customer.id,
                         producto_id=product.id, vistas=1, vista_reciente_en=utc_now()))
    else:
        event.vistas = min(event.vistas + 1, 50)
        event.vista_reciente_en = utc_now()
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"registrado": True}


@router.get("/sugerencias")
def personal_recommendations(
    response: Response, talla: str | None = None, color: str | None = None,
    sucursal_id: int | None = None, limit: int = 12,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    from app.catalogo_publico.recomendaciones import build_recommendations
    customer, _, company = current
    response.headers["Cache-Control"] = "no-store"
    if not (consent := _consent(db, company.id, customer.id)) or not consent.habilitado:
        raise HTTPException(403, "La personalización no está habilitada.")
    if not 1 <= limit <= 20:
        raise HTTPException(422, "Límite inválido.")
    if talla and len(talla) > 30 or color and len(color) > 60:
        raise HTTPException(422, "Preferencia demasiado larga.")
    history = db.execute(select(VistaCU19, Producto).join(
        Producto, (Producto.id == VistaCU19.producto_id)
        & (Producto.empresa_id == VistaCU19.empresa_id),
    ).where(
        VistaCU19.empresa_id == company.id, VistaCU19.cliente_id == customer.id,
        Producto.activo.is_(True),
    ).order_by(VistaCU19.vista_reciente_en.desc()).limit(30)).all()
    weighted = [(product, min(event.vistas, 10)) for event, product in history]
    return build_recommendations(db, company.id, company.slug, None,
                                 talla, color, sucursal_id, limit, weighted)
