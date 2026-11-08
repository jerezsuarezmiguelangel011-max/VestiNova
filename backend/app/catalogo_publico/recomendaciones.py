"""CU19: recomendaciones explicables de prendas publicadas de la misma tienda.

Similitud de categoría, material, temporada, color, talla y rango de precio.
No usa servicios externos, no perfila al cliente ni modifica inventario.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo_publico.catalogo import selected_company
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.db import get_db
from app.models import Existencia, Producto, Sucursal, VarianteProducto, utc_now


router = APIRouter(prefix="/api/catalogo/recomendaciones",
                   tags=["CU19 · Recomendaciones de prendas"])


def _score(product: Producto, reference: Producto | None,
           variants: list[VarianteProducto], talla: str | None, color: str | None):
    points, reasons = 0, []
    if reference is not None:
        if reference.categoria_id and product.categoria_id == reference.categoria_id:
            points += 55
            reasons.append("Categoría similar")
        if reference.material and product.material and reference.material.casefold() == product.material.casefold():
            points += 20
            reasons.append("Mismo material")
        if reference.temporada and product.temporada and reference.temporada.casefold() == product.temporada.casefold():
            points += 15
            reasons.append("Misma temporada")
        if abs(product.precio - reference.precio) <= reference.precio * Decimal("0.25"):
            points += 10
            reasons.append("Precio parecido")
    if talla and any(v.talla.casefold() == talla.casefold() for v in variants):
        points += 20
        reasons.append("Talla preferida")
    if color and any(v.color.casefold() == color.casefold() for v in variants):
        points += 20
        reasons.append("Color preferido")
    if reference is None and not reasons:
        reasons.append("Prenda publicada de esta tienda")
    return points, reasons


@router.get("")
def recommended(
    response: Response,
    tienda: str = Query(min_length=1, max_length=100),
    producto_slug: str | None = Query(default=None, max_length=140),
    talla: str | None = Query(default=None, min_length=1, max_length=30),
    color: str | None = Query(default=None, min_length=1, max_length=60),
    sucursal_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    company_id = selected_company(db, tienda)
    if sucursal_id is not None and db.scalar(select(Sucursal.id).where(
        Sucursal.empresa_id == company_id, Sucursal.id == sucursal_id,
        Sucursal.activo.is_(True),
    )) is None:
        raise HTTPException(404, "Sucursal no disponible para esta tienda.")

    reference = None
    if producto_slug:
        reference = db.scalar(select(Producto).where(
            Producto.empresa_id == company_id, Producto.slug == producto_slug,
            Producto.activo.is_(True),
        ))
        if reference is None:
            raise HTTPException(404, "Prenda de referencia no disponible.")

    products = db.scalars(select(Producto).where(
        Producto.empresa_id == company_id, Producto.activo.is_(True),
        *([Producto.id != reference.id] if reference else [])
    ).order_by(Producto.id.desc()).limit(500)).all()
    ids = [p.id for p in products]
    variants = db.scalars(select(VarianteProducto).where(
        VarianteProducto.empresa_id == company_id,
        VarianteProducto.producto_id.in_(ids) if ids else False,
        VarianteProducto.activo.is_(True),
    )).all()
    by_product: dict[int, list[VarianteProducto]] = {}
    for variant in variants:
        by_product.setdefault(variant.producto_id, []).append(variant)
    balances = {}
    if sucursal_id is not None and variants:
        balances = {r.variante_id: r for r in db.scalars(select(Existencia).where(
            Existencia.empresa_id == company_id, Existencia.sucursal_id == sucursal_id,
            Existencia.variante_id.in_([v.id for v in variants]),
        )).all()}
    promos = active_promotions_for_products(db, products)
    ranked = []
    for product in products:
        own = by_product.get(product.id, [])
        if not own:
            continue
        score, reasons = _score(product, reference, own, talla, color)
        available = None if sucursal_id is None else any(
            balances[v.id].cantidad > balances[v.id].cantidad_comprometida
            for v in own if v.id in balances
        )
        # Orden estable, priorizando coincidencias; disponibilidad solo aporta señal referencial.
        ranked.append((score, int(available is True), product.id, product, reasons, available))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    items = []
    for _, _, _, product, reasons, available in ranked[:limit]:
        promo = promos.get(product.id)
        price = promotional_price(product.precio, promo) if promo else product.precio
        items.append({
            "producto_id": product.id,
            "slug": product.slug,
            "nombre": product.nombre,
            "categoria": product.categoria_nombre,
            "material": product.material,
            "temporada": product.temporada,
            "imagen_url": product.imagen_url,
            "precio": f"{price:.2f}",
            "moneda": "BOB",
            "disponibilidad": "NO_VERIFICADA" if available is None else
                "DISPONIBLE_REFERENCIAL" if available else "SIN_UNIDADES_CONOCIDAS",
            "motivos": reasons,
        })
    return {
        "tienda": tienda,
        "basado_en": producto_slug,
        "consultado_en": utc_now().isoformat(),
        "criterio": "REGLAS_SIMILITUD_CATALOGO",
        "items": items,
    }
