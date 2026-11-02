"""CU08: consulta pública del catálogo, precios y existencias referenciales."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Empresa, Existencia, Producto, Sucursal, VarianteProducto, utc_now
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.schemas import ListaProductos, ProductoResponse


router = APIRouter(prefix="/api/catalogo/productos", tags=["CU08 · Catálogo de prendas"])


@router.get("", response_model=ListaProductos)
def public_list(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    filters = [
        Producto.activo.is_(True),
        Producto.empresa_id.in_(select(Empresa.id).where(Empresa.activo.is_(True))),
    ]
    if q and q.strip():
        filters.append(func.lower(Producto.nombre).contains(q.strip().lower(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(Producto).where(*filters)) or 0
    products = db.scalars(
        select(Producto).where(*filters).order_by(Producto.id.desc()).offset(offset).limit(limit)
    ).all()
    promotions = active_promotions_for_products(db, products)
    items = []
    for product in products:
        response = ProductoResponse.model_validate(product)
        promotion = promotions.get(product.id)
        if promotion is not None:
            response = response.model_copy(update={
                "precio_promocional": promotional_price(product.precio, promotion),
                "promocion_nombre": promotion.nombre,
            })
        items.append(response)
    return ListaProductos(items=items, total=total, limit=limit, offset=offset)


@router.get("/{slug}/disponibilidad", tags=["CU08 · Existencias físicas referenciales"])
def public_availability(slug: str, response: Response, db: Session = Depends(get_db)):
    """Consulta existencias físicas; no reserva ni promete disponibilidad de compra."""
    response.headers["Cache-Control"] = "no-store"
    product = db.scalar(
        select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
            Producto.slug == slug,
            Producto.activo.is_(True),
            Empresa.activo.is_(True),
        )
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")

    branches = db.scalars(
        select(Sucursal).where(Sucursal.empresa_id == product.empresa_id, Sucursal.activo.is_(True))
        .order_by(Sucursal.id)
    ).all()
    variants = db.scalars(
        select(VarianteProducto).where(
            VarianteProducto.empresa_id == product.empresa_id,
            VarianteProducto.producto_id == product.id,
            VarianteProducto.activo.is_(True),
        ).order_by(VarianteProducto.id)
    ).all()
    quantities = {
        (row.sucursal_id, row.variante_id): row.cantidad
        for row in db.scalars(select(Existencia).where(
            Existencia.empresa_id == product.empresa_id,
            Existencia.sucursal_id.in_([branch.id for branch in branches]) if branches else False,
            Existencia.variante_id.in_([variant.id for variant in variants]) if variants else False,
        )).all()
    }
    return {
        "producto_id": product.id,
        "alcance": "STOCK_FISICO_REFERENCIAL",
        "consultado_en": utc_now().isoformat(),
        "items": [
            {
                "sucursal_id": branch.id,
                "sucursal": branch.nombre,
                "variante_id": variant.id,
                "talla": variant.talla,
                "color": variant.color,
                "hay_existencias_fisicas": quantities.get((branch.id, variant.id), 0) > 0,
                "saldo_registrado": (branch.id, variant.id) in quantities,
            }
            for branch in branches for variant in variants
        ],
    }


@router.get("/{slug}", response_model=ProductoResponse)
def public_detail(slug: str, db: Session = Depends(get_db)):
    product = db.scalar(
        select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
            Producto.slug == slug,
            Producto.activo.is_(True),
            Empresa.activo.is_(True),
        )
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    response = ProductoResponse.model_validate(product)
    promotion = active_promotions_for_products(db, [product]).get(product.id)
    if promotion is not None:
        response = response.model_copy(update={
            "precio_promocional": promotional_price(product.precio, promotion),
            "promocion_nombre": promotion.nombre,
        })
    return response
