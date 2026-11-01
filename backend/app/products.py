import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Empresa, Producto, utc_now
from app.schemas import ListaProductos, ProductoCreate, ProductoPatch, ProductoResponse
from app.tenancy import TenantContext, require_tenant, require_tenant_admin


admin_router = APIRouter(prefix="/api/admin/productos", tags=["Administración de productos"])
catalog_router = APIRouter(prefix="/api/catalogo/productos", tags=["Contrato público de catálogo"])


def generate_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:140].rstrip("-")
    if len(result) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Introduce un slug de al menos 3 caracteres para este nombre.")
    return result


def list_products(db: Session, q: str | None, active: bool | None, limit: int, offset: int, empresa_id: int | None = None) -> ListaProductos:
    filters = []
    if empresa_id is not None:
        filters.append(Producto.empresa_id == empresa_id)
    else:
        # Publicación deliberada: solo datos de catálogo de empresas activas.
        # Ningún dato operacional (stock/clientes/pertenencias) se publica aquí.
        filters.append(Producto.empresa_id.in_(select(Empresa.id).where(Empresa.activo.is_(True))))
    if active is not None:
        filters.append(Producto.activo.is_(active))
    if q and q.strip():
        # autoescape conserva % y _ como texto de búsqueda, sin SQL construido a mano.
        filters.append(func.lower(Producto.nombre).contains(q.strip().lower(), autoescape=True))
    count = db.scalar(select(func.count()).select_from(Producto).where(*filters)) or 0
    products = db.scalars(select(Producto).where(*filters).order_by(Producto.id.desc()).offset(offset).limit(limit)).all()
    return ListaProductos(items=[ProductoResponse.model_validate(product) for product in products], total=count, limit=limit, offset=offset)


@admin_router.get("", response_model=ListaProductos)
def admin_list(q: str | None = Query(default=None, max_length=120), activo: bool | None = None, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db), context: TenantContext = Depends(require_tenant)):
    return list_products(db, q, activo, limit, offset, context.empresa_id)


@admin_router.post("", response_model=ProductoResponse, status_code=201)
def create_product(payload: ProductoCreate, db: Session = Depends(get_db), context: TenantContext = Depends(require_tenant_admin)):
    data = payload.model_dump(exclude={"slug"})
    product = Producto(**data, empresa_id=context.empresa_id, slug=payload.slug or generate_slug(payload.nombre), moneda="BOB")
    db.add(product)
    commit_product(db)
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
def admin_detail(producto_id: int, db: Session = Depends(get_db), context: TenantContext = Depends(require_tenant)):
    return get_product(db, producto_id, context.empresa_id)


@admin_router.patch("/{producto_id}", response_model=ProductoResponse)
def update_product(producto_id: int, payload: ProductoPatch, db: Session = Depends(get_db), context: TenantContext = Depends(require_tenant_admin)):
    product = get_product(db, producto_id, context.empresa_id)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, name, value)
    product.actualizado_en = utc_now()
    commit_product(db)
    db.refresh(product)
    return product


@catalog_router.get("", response_model=ListaProductos)
def public_list(q: str | None = Query(default=None, max_length=120), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    return list_products(db, q, True, limit, offset)


@catalog_router.get("/{slug}", response_model=ProductoResponse)
def public_detail(slug: str, db: Session = Depends(get_db)):
    product = db.scalar(select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(Producto.slug == slug, Producto.activo.is_(True), Empresa.activo.is_(True)))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    return product
