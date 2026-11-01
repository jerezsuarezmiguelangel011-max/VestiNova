"""Variantes e inventario: saldo + movimientos atómicos, sin edición de stock."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.inventory_schemas import (
    ExistenciaResponse, ListaExistencias, ListaMovimientos, MovimientoCreate,
    MovimientoResponse, VarianteCreate, VariantePatch, VarianteResponse,
)
from app.models import Existencia, MovimientoInventario, Producto, VarianteProducto, utc_now
from app.products import get_product
from app.tenancy import TenantContext, authorized_branch, require_tenant, require_tenant_admin


router = APIRouter(prefix="/api/admin", tags=["Variantes e inventario"])


def get_variant(db: Session, context: TenantContext, variant_id: int) -> VarianteProducto:
    variant = db.scalar(select(VarianteProducto).where(VarianteProducto.id == variant_id, VarianteProducto.empresa_id == context.empresa_id))
    if variant is None:
        raise HTTPException(404, "Variante no disponible para esta empresa.")
    return variant


@router.get("/productos/{producto_id}/variantes", response_model=list[VarianteResponse])
def list_variants(producto_id: int, context: TenantContext = Depends(require_tenant), db: Session = Depends(get_db)):
    get_product(db, producto_id, context.empresa_id)
    return db.scalars(select(VarianteProducto).where(VarianteProducto.empresa_id == context.empresa_id, VarianteProducto.producto_id == producto_id).order_by(VarianteProducto.id)).all()


@router.post("/productos/{producto_id}/variantes", response_model=VarianteResponse, status_code=201)
def create_variant(producto_id: int, payload: VarianteCreate, context: TenantContext = Depends(require_tenant_admin), db: Session = Depends(get_db)):
    get_product(db, producto_id, context.empresa_id)
    variant = VarianteProducto(empresa_id=context.empresa_id, producto_id=producto_id, **payload.model_dump())
    db.add(variant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe esa combinación de talla y color para el producto.") from None
    return variant


@router.patch("/variantes/{variante_id}", response_model=VarianteResponse)
def update_variant(variante_id: int, payload: VariantePatch, context: TenantContext = Depends(require_tenant_admin), db: Session = Depends(get_db)):
    # El bloqueo serializa correcciones de identidad con referencias de inventario.
    # Nunca se cambia el producto ni la empresa propietaria de una variante.
    variant = db.scalar(select(VarianteProducto).where(VarianteProducto.id == variante_id, VarianteProducto.empresa_id == context.empresa_id).with_for_update())
    if variant is None:
        raise HTTPException(404, "Variante no disponible para esta empresa.")
    changes = payload.model_dump(exclude_unset=True)
    identity_changed = any(name in changes and changes[name] != getattr(variant, name) for name in ("talla", "color"))
    if identity_changed:
        has_balance = db.scalar(select(Existencia.variante_id).where(Existencia.empresa_id == context.empresa_id, Existencia.variante_id == variant.id).limit(1)) is not None
        has_history = db.scalar(select(MovimientoInventario.id).where(MovimientoInventario.empresa_id == context.empresa_id, MovimientoInventario.variante_id == variant.id).limit(1)) is not None
        if has_balance or has_history:
            raise HTTPException(409, "No se puede cambiar la talla o el color de una variante con existencias o movimientos registrados. Desactívala y crea otra variante.")
    for name, value in changes.items():
        setattr(variant, name, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe esa combinación de talla y color para el producto.") from None
    return variant


def replay(db: Session, context: TenantContext, payload: MovimientoCreate) -> MovimientoInventario | None:
    existing = db.get(MovimientoInventario, str(payload.id))
    if existing is None:
        return None
    delta = payload.cantidad if payload.tipo == "ENTRADA" else -payload.cantidad
    if (existing.empresa_id, existing.sucursal_id, existing.variante_id, existing.usuario_id, existing.tipo, existing.delta, existing.motivo) != (
        context.empresa_id, payload.sucursal_id, payload.variante_id, context.usuario.id, payload.tipo, delta, payload.motivo
    ):
        raise HTTPException(409, "El identificador de movimiento ya fue utilizado con otros datos.")
    return existing


@router.post("/inventario/movimientos", response_model=MovimientoResponse, status_code=201)
def register_movement(payload: MovimientoCreate, response: Response, context: TenantContext = Depends(require_tenant_admin), db: Session = Depends(get_db)):
    authorized_branch(db, context, payload.sucursal_id)
    variant = get_variant(db, context, payload.variante_id)
    previous = replay(db, context, payload)
    if previous is not None:
        response.status_code = 200
        return previous
    product = get_product(db, variant.producto_id, context.empresa_id)
    if not variant.activo or not product.activo:
        raise HTTPException(409, "Activa el producto y la variante antes de registrar movimientos nuevos.")
    key = {"empresa_id": context.empresa_id, "sucursal_id": payload.sucursal_id, "variante_id": payload.variante_id}
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    # El UPSERT protege también el primer movimiento concurrente sobre una clave
    # todavía sin saldo. El bloqueo de fila se conserva hasta commit/rollback.
    db.execute(insert(Existencia).values(**key, cantidad=0, actualizado_en=utc_now()).on_conflict_do_nothing(index_elements=list(key)))
    balance = db.scalar(select(Existencia).where(*(getattr(Existencia, k) == v for k, v in key.items())).with_for_update())
    # Otro request puede haber confirmado el mismo id mientras esperábamos el lock.
    previous = replay(db, context, payload)
    if previous is not None:
        db.rollback()
        response.status_code = 200
        return previous
    delta = payload.cantidad if payload.tipo == "ENTRADA" else -payload.cantidad
    resulting = balance.cantidad + delta
    if resulting < 0 or resulting > 2_000_000_000:
        db.rollback()
        raise HTTPException(409, "El movimiento deja existencias insuficientes o supera el límite de inventario.")
    balance.cantidad = resulting
    balance.actualizado_en = utc_now()
    movement = MovimientoInventario(id=str(payload.id), **key, usuario_id=context.usuario.id, tipo=payload.tipo, delta=delta, saldo_resultante=resulting, motivo=payload.motivo)
    db.add(movement)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = replay(db, context, payload)
        if previous is None:
            raise HTTPException(409, "No se pudo registrar el movimiento; no se modificó el inventario.") from None
        response.status_code = 200
        return previous
    return movement


@router.get("/inventario/existencias", response_model=ListaExistencias)
def list_balances(sucursal_id: int = Query(gt=0), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), context: TenantContext = Depends(require_tenant), db: Session = Depends(get_db)):
    authorized_branch(db, context, sucursal_id)
    filters = (Existencia.empresa_id == context.empresa_id, Existencia.sucursal_id == sucursal_id)
    count = db.scalar(select(func.count()).select_from(Existencia).where(*filters)) or 0
    rows = db.scalars(select(Existencia).where(*filters).order_by(Existencia.variante_id).limit(limit).offset(offset)).all()
    return ListaExistencias(items=[ExistenciaResponse.model_validate(row) for row in rows], total=count, limit=limit, offset=offset)


@router.get("/inventario/movimientos", response_model=ListaMovimientos)
def list_movements(sucursal_id: int = Query(gt=0), variante_id: int | None = Query(default=None, gt=0), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), context: TenantContext = Depends(require_tenant), db: Session = Depends(get_db)):
    authorized_branch(db, context, sucursal_id)
    filters = [MovimientoInventario.empresa_id == context.empresa_id, MovimientoInventario.sucursal_id == sucursal_id]
    if variante_id is not None:
        get_variant(db, context, variante_id)
        filters.append(MovimientoInventario.variante_id == variante_id)
    count = db.scalar(select(func.count()).select_from(MovimientoInventario).where(*filters)) or 0
    rows = db.scalars(select(MovimientoInventario).where(*filters).order_by(MovimientoInventario.creado_en.desc(), MovimientoInventario.id.desc()).limit(limit).offset(offset)).all()
    return ListaMovimientos(items=[MovimientoResponse.model_validate(row) for row in rows], total=count, limit=limit, offset=offset)
