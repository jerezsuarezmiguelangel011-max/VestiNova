"""CU19: reglas explicables por prenda, preferencias expresas e historial consentido.

No se atribuyen preferencias a clientes anónimos. El usuario puede consultar
sugerencias generales sin habilitar el seguimiento de visitas.
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
           variants: list[VarianteProducto], talla: str | None, color: str | None,
           history: list[tuple[Producto, int]] | None = None):
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
    if history:
        similar_categories = 0
        for visited, count in history:
            weight = min(count, 5)
            if product.categoria_id and product.categoria_id == visited.categoria_id:
                points += 16 * weight
                similar_categories += weight
            if product.material and visited.material and product.material.casefold() == visited.material.casefold():
                points += 5 * weight
            if product.temporada and visited.temporada and product.temporada.casefold() == visited.temporada.casefold():
                points += 3 * weight
        if similar_categories:
            reasons.append("Se parece a las categorías que has consultado")
        elif points:
            reasons.append("Relacionada con prendas que has visto")
    if talla and any(v.talla.casefold() == talla.casefold() for v in variants):
        points += 20
        reasons.append("Talla elegida")
    if color and any(v.color.casefold() == color.casefold() for v in variants):
        points += 20
        reasons.append("Color elegido")
    if not reasons:
        reasons.append("Prenda publicada de esta tienda")
    return points, reasons


def build_recommendations(
    db: Session, company_id: int, tienda: str,
    producto_slug: str | None, talla: str | None, color: str | None,
    sucursal_id: int | None, limit: int,
    history: list[tuple[Producto, int]] | None = None,
) -> dict:
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

    excluded = {product.id for product, _ in (history or [])}
    products = db.scalars(select(Producto).where(
        Producto.empresa_id == company_id, Producto.activo.is_(True),
        *([Producto.id != reference.id] if reference else []),
        *([Producto.id.not_in(excluded)] if excluded else []),
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
        if talla and not any(v.talla.casefold() == talla.casefold() for v in own):
            continue
        if color and not any(v.color.casefold() == color.casefold() for v in own):
            continue
        # Se admiten filtros independientes. El producto debe tener una variante
        # que coincida con ambas selecciones si el usuario rellenó ambas.
        if talla and color and not any(
            v.talla.casefold() == talla.casefold() and
            v.color.casefold() == color.casefold() for v in own
        ):
            continue
        score, reasons = _score(product, reference, own, talla, color, history)
        available = None if sucursal_id is None else any(
            balances[v.id].cantidad > balances[v.id].cantidad_comprometida
            for v in own if v.id in balances
        )
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
        "criterio": "REGLAS_HISTORIAL_CONSENTIDO" if history else "REGLAS_SIMILITUD_CATALOGO",
        "items": items,
    }


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
    return build_recommendations(db, company_id, tienda,
                                 producto_slug, talla, color, sucursal_id, limit)
