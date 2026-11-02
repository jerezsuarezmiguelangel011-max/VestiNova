import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.catalogo_abastecimiento.categories import get_category
from app.db import get_db
from app.models import CategoriaProducto, Producto, Promocion, PromocionProducto, utc_now
from app.organizacion_empresarial.plans import ensure_resource_capacity
from app.schemas import ListaProductos, ProductoCreate, ProductoPatch, ProductoResponse
from app.tenancy import TenantContext, require_permission


admin_router = APIRouter(prefix="/api/admin/productos", tags=["CU04 · Catálogo de prendas"])


def generate_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:140].rstrip("-")
    if len(result) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Introduce un slug de al menos 3 caracteres para este nombre.")
    return result


def list_products(db: Session, q: str | None, active: bool | None, limit: int, offset: int, empresa_id: int) -> ListaProductos:
    filters = [Producto.empresa_id == empresa_id]
    if active is not None:
        filters.append(Producto.activo.is_(active))
    if q and q.strip():
        filters.append(func.lower(Producto.nombre).contains(q.strip().lower(), autoescape=True))
    count = db.scalar(select(func.count()).select_from(Producto).where(*filters)) or 0
    products = db.scalars(select(Producto).where(*filters).order_by(Producto.id.desc()).offset(offset).limit(limit)).all()
    return ListaProductos(items=[ProductoResponse.model_validate(product) for product in products], total=count, limit=limit, offset=offset)

@admin_router.get("", response_model=ListaProductos)
def admin_list(q: str | None = Query(default=None, max_length=120), activo: bool | None = None, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.consultar"))):
    return list_products(db, q, activo, limit, offset, context.empresa_id)


@admin_router.post("", response_model=ProductoResponse, status_code=201)
def create_product(payload: ProductoCreate, db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True))):
    if payload.activo:
        ensure_resource_capacity(db, context.empresa_id, "productos")
    data = payload.model_dump(exclude={"slug"})
    if payload.categoria_id is None:
        category = db.scalar(select(CategoriaProducto).where(
            CategoriaProducto.empresa_id == context.empresa_id,
            CategoriaProducto.nombre_clave == "general",
        ))
        if category is None:
            category = CategoriaProducto(empresa_id=context.empresa_id, nombre="General", nombre_clave="general", descripcion="Categoría general de prendas.", activo=True)
            db.add(category)
            db.flush()
        elif not category.activo:
            category.activo = True
        categoria_id = category.id
    else:
        categoria_id = get_category(db, context, payload.categoria_id, active=True).id
    data["categoria_id"] = categoria_id
    product = Producto(**data, empresa_id=context.empresa_id, slug=payload.slug or generate_slug(payload.nombre), moneda="BOB")
    db.add(product)
    try:
        db.flush()
        record_audit_event(db, context, accion="producto.creado", entidad="producto", entidad_id=product.id,
                           detalles={"nombre": product.nombre, "categoria_id": categoria_id})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un producto con ese slug. Utiliza otro identificador.") from None
    db.refresh(product)
    return product


def commit_product(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un producto con ese slug. Utiliza otro identificador.") from None


def get_product(db: Session, product_id: int, empresa_id: int) -> Producto:
    product = db.scalar(select(Producto).where(Producto.id == product_id, Producto.empresa_id == empresa_id))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    return product


@admin_router.get("/{producto_id}", response_model=ProductoResponse)
def admin_detail(producto_id: int, db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.consultar"))):
    return get_product(db, producto_id, context.empresa_id)


@admin_router.patch("/{producto_id}", response_model=ProductoResponse)
def update_product(producto_id: int, payload: ProductoPatch, db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True))):
    product = get_product(db, producto_id, context.empresa_id)
    changes = payload.model_dump(exclude_unset=True)
    if "categoria_id" in changes:
        get_category(db, context, changes["categoria_id"], active=True)
    if changes.get("activo") is True and not product.activo:
        ensure_resource_capacity(db, context.empresa_id, "productos")
    if "precio" in changes:
        fixed_promotion = db.scalar(select(Promocion.id).join(
            PromocionProducto,
            (PromocionProducto.promocion_id == Promocion.id) & (PromocionProducto.empresa_id == Promocion.empresa_id),
        ).where(
            Promocion.empresa_id == context.empresa_id,
            PromocionProducto.producto_id == product.id,
            Promocion.activo.is_(True),
            Promocion.tipo == "PRECIO_FIJO",
            Promocion.fin > utc_now(),
            Promocion.valor >= changes["precio"],
        ).limit(1))
        if fixed_promotion is not None:
            raise HTTPException(409, "El precio regular debe superar el precio fijo de todas las promociones vigentes o programadas.")
    for name, value in changes.items():
        setattr(product, name, value)
    product.actualizado_en = utc_now()
    record_audit_event(db, context, accion="producto.actualizado", entidad="producto", entidad_id=product.id,
                       detalles={"campos": sorted(changes), "nombre": product.nombre})
    commit_product(db)
    db.refresh(product)
    return product
