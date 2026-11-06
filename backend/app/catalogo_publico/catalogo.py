"""CU08: consulta pública del catálogo, precios y existencias referenciales."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CategoriaProducto, Empresa, Existencia, PlanSaaS, Producto, Sucursal, SuscripcionEmpresa, VarianteProducto, utc_now
from app.organizacion_empresarial.plans import subscription_state
from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.schemas import ListaProductos, ProductoResponse


router = APIRouter(prefix="/api/catalogo/productos", tags=["CU08 · Catálogo de prendas"])
directory_router = APIRouter(prefix="/api/catalogo", tags=["CU08 · Tiendas y categorías"])


def selected_company(db: Session, tienda: str | None) -> int | None:
    if tienda is None:
        return None
    company_id = db.scalar(
        select(Empresa.id).where(Empresa.slug == tienda, Empresa.activo.is_(True))
    )
    if company_id is None:
        raise HTTPException(404, "Tienda no disponible.")
    return company_id


@directory_router.get("/tiendas")
def public_stores(db: Session = Depends(get_db)):
    """Identificadores y nombres de empresas visibles públicamente."""
    rows = db.execute(
        select(Empresa, SuscripcionEmpresa)
        .join(SuscripcionEmpresa, SuscripcionEmpresa.empresa_id == Empresa.id)
        .join(PlanSaaS, PlanSaaS.id == SuscripcionEmpresa.plan_id)
        .where(Empresa.activo.is_(True), PlanSaaS.activo.is_(True))
        .order_by(Empresa.nombre)
    ).all()
    return [
        {"slug": company.slug, "nombre": company.nombre}
        for company, subscription in rows
        if subscription_state(subscription) == "ACTIVA"
    ]


@directory_router.get("/categorias")
def public_categories(tienda: str = Query(min_length=1, max_length=100), db: Session = Depends(get_db)):
    company_id = selected_company(db, tienda)
    rows = db.scalars(
        select(CategoriaProducto).where(
            CategoriaProducto.empresa_id == company_id,
            CategoriaProducto.activo.is_(True),
            CategoriaProducto.id.in_(select(Producto.categoria_id).where(
                Producto.empresa_id == company_id, Producto.activo.is_(True)
            )),
        ).order_by(CategoriaProducto.nombre)
    ).all()
    return [{"id": row.id, "nombre": row.nombre} for row in rows]



@directory_router.get("/sucursales")
def public_branches(tienda: str = Query(min_length=1, max_length=100), db: Session = Depends(get_db)):
    """Solo identificadores de sucursales públicas ACTIVAS de la empresa seleccionada."""
    company_id = selected_company(db, tienda)
    rows = db.scalars(select(Sucursal).where(
        Sucursal.empresa_id == company_id, Sucursal.activo.is_(True),
    ).order_by(Sucursal.nombre, Sucursal.id)).all()
    return [{"id": row.id, "nombre": row.nombre} for row in rows]


@router.get("", response_model=ListaProductos)
def public_list(
    q: str | None = Query(default=None, max_length=120),
    tienda: str | None = Query(default=None, min_length=1, max_length=100),
    categoria_id: int | None = Query(default=None, gt=0),
    talla: str | None = Query(default=None, min_length=1, max_length=30),
    color: str | None = Query(default=None, min_length=1, max_length=60),
    temporada: str | None = Query(default=None, min_length=1, max_length=60),
    precio_min: Decimal | None = Query(default=None, ge=0),
    precio_max: Decimal | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    company_id = selected_company(db, tienda)
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise HTTPException(422, "El precio mínimo no puede superar el máximo.")
    filters = [
        Producto.activo.is_(True),
        Producto.empresa_id.in_(select(Empresa.id).where(Empresa.activo.is_(True))),
    ]
    if company_id is not None:
        filters.append(Producto.empresa_id == company_id)
    if categoria_id is not None:
        filters.append(Producto.categoria_id == categoria_id)
        filters.append(Producto.categoria_id.in_(
            select(CategoriaProducto.id).where(
                CategoriaProducto.activo.is_(True),
                CategoriaProducto.empresa_id == Producto.empresa_id,
            )
        ))
    if precio_min is not None:
        filters.append(Producto.precio >= precio_min)
    if precio_max is not None:
        filters.append(Producto.precio <= precio_max)
    if temporada and temporada.strip():
        filters.append(func.lower(Producto.temporada) == temporada.strip().lower())
    if talla or color:
        variant = select(VarianteProducto.id).where(
            VarianteProducto.empresa_id == Producto.empresa_id,
            VarianteProducto.producto_id == Producto.id,
            VarianteProducto.activo.is_(True),
        )
        if talla:
            variant = variant.where(func.lower(VarianteProducto.talla) == talla.strip().lower())
        if color:
            variant = variant.where(func.lower(VarianteProducto.color) == color.strip().lower())
        filters.append(variant.exists())
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
def public_availability(slug: str, response: Response, tienda: str | None = Query(default=None, min_length=1, max_length=100), sucursal_id: int | None = Query(default=None, gt=0), variante_id: int | None = Query(default=None, gt=0), db: Session = Depends(get_db)):
    """Consulta existencias físicas; no reserva ni promete disponibilidad de compra."""
    response.headers["Cache-Control"] = "no-store"
    company_id = selected_company(db, tienda)
    filters = [Producto.slug == slug]
    if company_id is not None:
        filters.append(Producto.empresa_id == company_id)
    product = db.scalar(
        select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
            *filters,
            Producto.activo.is_(True),
            Empresa.activo.is_(True),
        )
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")

    branches = db.scalars(
        select(Sucursal).where(Sucursal.empresa_id == product.empresa_id, Sucursal.activo.is_(True), *([Sucursal.id == sucursal_id] if sucursal_id is not None else []))
        .order_by(Sucursal.id)
    ).all()
    variants = db.scalars(
        select(VarianteProducto).where(
            VarianteProducto.empresa_id == product.empresa_id,
            VarianteProducto.producto_id == product.id,
            VarianteProducto.activo.is_(True),
            *([VarianteProducto.id == variante_id] if variante_id is not None else []),
        ).order_by(VarianteProducto.id)
    ).all()
    quantities = {
        (row.sucursal_id, row.variante_id): row
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
                "hay_existencias_fisicas": quantities[(branch.id, variant.id)].cantidad > 0 if (branch.id, variant.id) in quantities else False,
                "hay_disponibilidad": (
                    quantities[(branch.id, variant.id)].cantidad > quantities[(branch.id, variant.id)].cantidad_comprometida
                    if (branch.id, variant.id) in quantities else False
                ),
                "actualizado_en": quantities[(branch.id, variant.id)].actualizado_en.isoformat() if (branch.id, variant.id) in quantities else None,
                "saldo_registrado": (branch.id, variant.id) in quantities,
            }
            for branch in branches for variant in variants
        ],
    }


@router.get("/{slug}", response_model=ProductoResponse)
def public_detail(slug: str, tienda: str | None = Query(default=None, min_length=1, max_length=100), db: Session = Depends(get_db)):
    company_id = selected_company(db, tienda)
    filters = [Producto.slug == slug]
    if company_id is not None:
        filters.append(Producto.empresa_id == company_id)
    product = db.scalar(
        select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
            *filters,
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



@directory_router.get("/variantes")
def public_company_variants(
    tienda: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Lista acotada de variantes públicas para preparar copias offline por tenant."""
    company_id = selected_company(db, tienda)
    filters = [
        VarianteProducto.empresa_id == company_id,
        VarianteProducto.activo.is_(True),
        Producto.empresa_id == company_id,
        Producto.activo.is_(True),
    ]
    query = (
        select(VarianteProducto, Producto.slug)
        .join(Producto, (Producto.id == VarianteProducto.producto_id) &
              (Producto.empresa_id == VarianteProducto.empresa_id))
        .where(*filters)
    )
    total = db.scalar(
        select(func.count()).select_from(VarianteProducto)
        .join(Producto, (Producto.id == VarianteProducto.producto_id) &
              (Producto.empresa_id == VarianteProducto.empresa_id)).where(*filters)
    ) or 0
    rows = db.execute(query.order_by(VarianteProducto.id.desc()).offset(offset).limit(limit)).all()
    return {
        "items": [{"id": variant.id, "producto_slug": slug,
                   "talla": variant.talla, "color": variant.color}
                  for variant, slug in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/{slug}/variantes")
def public_variants(
    slug: str,
    tienda: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    """Variantes publicadas; consulta sin descuentos ni ajustes de stock."""
    company_id = selected_company(db, tienda)
    filters = [Producto.slug == slug, Producto.activo.is_(True), Empresa.activo.is_(True)]
    if company_id is not None:
        filters.append(Producto.empresa_id == company_id)
    product = db.scalar(select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(*filters))
    if product is None:
        raise HTTPException(404, "Producto no encontrado.")
    variants = db.scalars(
        select(VarianteProducto).where(
            VarianteProducto.empresa_id == product.empresa_id,
            VarianteProducto.producto_id == product.id,
            VarianteProducto.activo.is_(True),
        ).order_by(VarianteProducto.id)
    ).all()
    return [{"id": row.id, "talla": row.talla, "color": row.color} for row in variants]
