"""Descarga operacional autorizada. No recibe ventas/reservas ni sincroniza."""
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, PositiveInt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.inventory_schemas import OperationalResponse, VarianteResponse
from app.models import Existencia, Producto, VarianteProducto, utc_now
from app.schemas import ProductoResponse
from app.security import bearer, get_current_session
from app.tenancy import TenantContext, authorized_branches_statement, require_tenant


router = APIRouter(prefix="/api/movil", tags=["Descarga móvil autorizada"])


class EmpresaDescarga(BaseModel):
    id: int
    slug: str
    nombre: str


class SucursalDescarga(OperationalResponse):
    id: int
    empresa_id: int
    codigo: str
    nombre: str
    activo: bool
    creado_en: datetime


class ExistenciaConocida(OperationalResponse):
    sucursal_id: int
    cantidad: int
    registrada: bool
    actualizado_en: datetime | None


class VarianteDescarga(VarianteResponse):
    existencias: list[ExistenciaConocida]


class ProductoDescarga(ProductoResponse):
    variantes: list[VarianteDescarga]


class DescargaResponse(OperationalResponse):
    version_contrato: Literal["1.0"] = "1.0"
    generado_en: datetime
    empresa: EmpresaDescarga
    moneda: Literal["BOB"] = "BOB"
    sucursales: list[SucursalDescarga]
    productos: list[ProductoDescarga]
    total: int
    limit: int
    offset: int


def download_db(request: Request) -> Iterator[Session]:
    # Autenticación, permisos y datos se leen en la misma vista de PostgreSQL.
    # No se promete congelar la información entre páginas de distintas requests.
    with request.app.state.engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)
        with Session(bind=connection, expire_on_commit=False) as session:
            yield session


def download_tenant(
    request: Request,
    empresa_id: Annotated[int | None, Header(alias="X-Empresa-Id", ge=1)] = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(download_db),
) -> TenantContext:
    usuario, _ = get_current_session(request, credentials, db)
    return require_tenant(empresa_id, usuario, db)


@router.get("/descarga", response_model=DescargaResponse)
def download(
    response: Response,
    sucursal_ids: Annotated[list[PositiveInt] | None, Query(max_length=100)] = None,
    producto_ids: Annotated[list[PositiveInt] | None, Query(max_length=100)] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(download_tenant),
    db: Session = Depends(download_db),
):
    response.headers["Cache-Control"] = "no-store"
    branches = db.scalars(authorized_branches_statement(context).order_by("id")).all()
    requested_branches = set(sucursal_ids or [])
    branch_ids = {branch.id for branch in branches}
    if requested_branches - branch_ids:
        raise HTTPException(404, "Alguna sucursal solicitada no está disponible para este usuario.")
    if requested_branches:
        branches = [branch for branch in branches if branch.id in requested_branches]
    if not branches:
        raise HTTPException(403, "No tienes sucursales activas autorizadas para descargar.")
    if len(branches) > 100:
        raise HTTPException(413, "Selecciona como máximo 100 sucursales por descarga.")
    branch_ids = [branch.id for branch in branches]
    filters = [Producto.empresa_id == context.empresa_id, Producto.activo.is_(True)]
    if producto_ids:
        requested = set(producto_ids)
        available = set(db.scalars(select(Producto.id).where(*filters, Producto.id.in_(requested))).all())
        if requested != available:
            raise HTTPException(404, "Algún producto solicitado no está disponible para esta empresa.")
        filters.append(Producto.id.in_(requested))
    total = db.scalar(select(func.count()).select_from(Producto).where(*filters)) or 0
    products = db.scalars(select(Producto).where(*filters).order_by(Producto.id).limit(limit).offset(offset)).all()
    product_ids = [product.id for product in products]
    variants = db.scalars(select(VarianteProducto).where(VarianteProducto.empresa_id == context.empresa_id, VarianteProducto.producto_id.in_(product_ids), VarianteProducto.activo.is_(True)).order_by(VarianteProducto.id).limit(2001)).all()
    if len(variants) > 2000:
        raise HTTPException(413, "Reduce la cantidad de productos: se permiten 2000 variantes por página.")
    variants_by_product = {product.id: [] for product in products}
    balances = db.scalars(select(Existencia).where(Existencia.empresa_id == context.empresa_id, Existencia.sucursal_id.in_(branch_ids), Existencia.variante_id.in_([variant.id for variant in variants]))).all()
    balances_by_key = {(balance.sucursal_id, balance.variante_id): balance for balance in balances}
    for variant in variants:
        known = []
        for branch in branches:
            balance = balances_by_key.get((branch.id, variant.id))
            known.append(ExistenciaConocida(sucursal_id=branch.id, cantidad=balance.cantidad if balance is not None else 0, registrada=balance is not None, actualizado_en=balance.actualizado_en if balance is not None else None))
        variants_by_product[variant.producto_id].append(VarianteDescarga(**VarianteResponse.model_validate(variant).model_dump(), existencias=known))
    return DescargaResponse(
        generado_en=utc_now(),
        empresa=EmpresaDescarga(id=context.empresa_id, slug=context.empresa.slug, nombre=context.empresa.nombre),
        sucursales=[SucursalDescarga.model_validate(branch) for branch in branches],
        productos=[ProductoDescarga(**ProductoResponse.model_validate(product).model_dump(), variantes=variants_by_product[product.id]) for product in products],
        total=total, limit=limit, offset=offset,
    )
