"""Administración de variantes del catálogo empresarial."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogo_abastecimiento.esquemas import VarianteCreate, VariantePatch, VarianteResponse
from app.catalogo_abastecimiento.productos import get_product
from app.db import get_db
from app.models import Existencia, MovimientoInventario, VarianteProducto
from app.organizacion_empresarial.audit import record_audit_event
from app.tenancy import TenantContext, require_permission


router = APIRouter(prefix="/api/admin", tags=["Variantes de producto"])


def get_variant(db: Session, context: TenantContext, variant_id: int) -> VarianteProducto:
    variant = db.scalar(
        select(VarianteProducto).where(
            VarianteProducto.id == variant_id,
            VarianteProducto.empresa_id == context.empresa_id,
        )
    )
    if variant is None:
        raise HTTPException(404, "Variante no disponible para esta empresa.")
    return variant


@router.get("/productos/{producto_id}/variantes", response_model=list[VarianteResponse], tags=["Variantes de producto"])
def list_variants(
    producto_id: int,
    context: TenantContext = Depends(require_permission("catalogo.consultar")),
    db: Session = Depends(get_db),
):
    get_product(db, producto_id, context.empresa_id)
    return db.scalars(
        select(VarianteProducto)
        .where(VarianteProducto.empresa_id == context.empresa_id, VarianteProducto.producto_id == producto_id)
        .order_by(VarianteProducto.id)
    ).all()


@router.post("/productos/{producto_id}/variantes", response_model=VarianteResponse, status_code=201, tags=["Variantes de producto"])
def create_variant(
    producto_id: int,
    payload: VarianteCreate,
    context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    get_product(db, producto_id, context.empresa_id)
    variant = VarianteProducto(empresa_id=context.empresa_id, producto_id=producto_id, **payload.model_dump())
    db.add(variant)
    try:
        db.flush()
        record_audit_event(
            db,
            context,
            accion="variante.creada",
            entidad="variante",
            entidad_id=variant.id,
            detalles={"producto_id": producto_id, "talla": variant.talla, "color": variant.color},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe esa combinación de talla y color para el producto.") from None
    return variant


@router.patch("/variantes/{variante_id}", response_model=VarianteResponse, tags=["Variantes de producto"])
def update_variant(
    variante_id: int,
    payload: VariantePatch,
    context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    # El bloqueo serializa los cambios de identidad con referencias de inventario.
    variant = db.scalar(
        select(VarianteProducto)
        .where(VarianteProducto.id == variante_id, VarianteProducto.empresa_id == context.empresa_id)
        .with_for_update()
    )
    if variant is None:
        raise HTTPException(404, "Variante no disponible para esta empresa.")
    changes = payload.model_dump(exclude_unset=True)
    identity_changed = any(name in changes and changes[name] != getattr(variant, name) for name in ("talla", "color"))
    if identity_changed:
        has_balance = db.scalar(
            select(Existencia.variante_id)
            .where(Existencia.empresa_id == context.empresa_id, Existencia.variante_id == variant.id)
            .limit(1)
        ) is not None
        has_history = db.scalar(
            select(MovimientoInventario.id)
            .where(MovimientoInventario.empresa_id == context.empresa_id, MovimientoInventario.variante_id == variant.id)
            .limit(1)
        ) is not None
        if has_balance or has_history:
            raise HTTPException(
                409,
                "No se puede cambiar la talla o el color de una variante con existencias o movimientos registrados. "
                "Desactívala y crea otra variante.",
            )
    for name, value in changes.items():
        setattr(variant, name, value)
    try:
        record_audit_event(
            db,
            context,
            accion="variante.actualizada",
            entidad="variante",
            entidad_id=variant.id,
            detalles={"campos": sorted(changes), "producto_id": variant.producto_id},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe esa combinación de talla y color para el producto.") from None
    return variant
