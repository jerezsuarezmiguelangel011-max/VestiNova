"""CU23: lista de deseos personal por cliente y empresa; no reserva stock."""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.db import Base, get_db
from app.models import Cliente, Empresa, Producto, SesionCliente, VarianteProducto, utc_now


router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/deseos",
                   tags=["CU23 · Lista de deseos"])


class Deseo(Base):
    __tablename__ = "deseos_cu23"
    __table_args__ = (
        ForeignKeyConstraint(["variante_id", "empresa_id"],
                             ["variantes_producto.id", "variantes_producto.empresa_id"],
                             name="fk_deseos_variante_empresa"),
    )

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True)
    variante_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DeseoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variante_id: StrictInt = Field(gt=0)


def _serialize(db: Session, customer: Cliente, company: Empresa, rows: list[Deseo]):
    ids = [item.variante_id for item in rows]
    if not ids:
        return []
    variants = db.execute(select(VarianteProducto, Producto).join(
        Producto, (Producto.id == VarianteProducto.producto_id)
        & (Producto.empresa_id == VarianteProducto.empresa_id),
    ).where(
        VarianteProducto.empresa_id == company.id, VarianteProducto.id.in_(ids),
        Producto.empresa_id == company.id,
    )).all()
    by_id = {v.id: (v, p) for v, p in variants}
    promotions = active_promotions_for_products(db, list({p.id: p for _, p in variants}.values()))
    result = []
    for item in rows:
        entry = by_id.get(item.variante_id)
        if entry is None:
            continue
        variant, product = entry
        visible = variant.activo and product.activo
        promo = promotions.get(product.id) if visible else None
        price = promotional_price(product.precio, promo) if promo else product.precio
        result.append({
            "variante_id": variant.id,
            "producto_id": product.id,
            "slug": product.slug if visible else None,
            "nombre": product.nombre,
            "talla": variant.talla,
            "color": variant.color,
            "imagen_url": product.imagen_url if visible else None,
            "precio_vigente": f"{price:.2f}" if visible else None,
            "moneda": "BOB",
            "publicada": bool(visible),
            "creado_en": item.creado_en.isoformat(),
        })
    return result


@router.get("")
def list_deseos(response: Response,
                current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
                db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    rows = db.scalars(select(Deseo).where(
        Deseo.empresa_id == company.id, Deseo.cliente_id == customer.id
    ).order_by(Deseo.creado_en.desc(), Deseo.variante_id.desc()).limit(200)).all()
    return {"items": _serialize(db, customer, company, rows), "total": len(rows)}


@router.post("", status_code=201)
def add_deseo(payload: DeseoInput, response: Response,
              current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
              db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    allowed = db.scalar(select(VarianteProducto.id).join(
        Producto, (Producto.id == VarianteProducto.producto_id)
        & (Producto.empresa_id == VarianteProducto.empresa_id)
    ).where(
        VarianteProducto.id == payload.variante_id,
        VarianteProducto.empresa_id == company.id, VarianteProducto.activo.is_(True),
        Producto.activo.is_(True), Producto.empresa_id == company.id,
    ))
    if allowed is None:
        raise HTTPException(404, "La variante no está publicada en esta tienda.")
    key = (company.id, customer.id, payload.variante_id)
    existing = db.get(Deseo, key)
    if existing is not None:
        response.status_code = 200
        return {"variante_id": payload.variante_id, "agregado": False}
    db.add(Deseo(empresa_id=company.id, cliente_id=customer.id,
                 variante_id=payload.variante_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(Deseo, key) is None:
            raise HTTPException(409, "No pudo guardarse la prenda.") from None
        response.status_code = 200
        return {"variante_id": payload.variante_id, "agregado": False}
    return {"variante_id": payload.variante_id, "agregado": True}


@router.delete("/{variante_id}", status_code=204)
def remove_deseo(variante_id: int, response: Response,
                 current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
                 db: Session = Depends(get_db)):
    customer, _, company = current
    item = db.get(Deseo, (company.id, customer.id, variante_id))
    if item is not None:
        db.delete(item)
        db.commit()
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
