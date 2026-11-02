"""Saldos y movimientos de existencias por sucursal."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.db import get_db
from app.inventario.esquemas import (
    ExistenciaResponse, ListaExistencias, ListaMovimientos, MovimientoCreate,
    MovimientoResponse,
)
from app.models import Existencia, MovimientoInventario, Producto, VarianteProducto, utc_now
from app.catalogo_abastecimiento.productos import get_product
from app.catalogo_abastecimiento.variantes import get_variant
from app.tenancy import TenantContext, authorized_branch, require_permission


router = APIRouter(prefix="/api/admin", tags=["Inventario"])



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
def register_movement(payload: MovimientoCreate, response: Response, context: TenantContext = Depends(require_permission("inventario.registrar", mutation=True)), db: Session = Depends(get_db)):
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
def list_balances(sucursal_id: int = Query(gt=0), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), context: TenantContext = Depends(require_permission("inventario.consultar")), db: Session = Depends(get_db)):
    authorized_branch(db, context, sucursal_id)
    filters = (Existencia.empresa_id == context.empresa_id, Existencia.sucursal_id == sucursal_id)
    count = db.scalar(select(func.count()).select_from(Existencia).where(*filters)) or 0
    rows = db.scalars(select(Existencia).where(*filters).order_by(Existencia.variante_id).limit(limit).offset(offset)).all()
    return ListaExistencias(items=[ExistenciaResponse.model_validate(row) for row in rows], total=count, limit=limit, offset=offset)


@router.get("/inventario/movimientos", response_model=ListaMovimientos)
def list_movements(sucursal_id: int = Query(gt=0), variante_id: int | None = Query(default=None, gt=0), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), context: TenantContext = Depends(require_permission("inventario.consultar")), db: Session = Depends(get_db)):
    authorized_branch(db, context, sucursal_id)
    filters = [MovimientoInventario.empresa_id == context.empresa_id, MovimientoInventario.sucursal_id == sucursal_id]
    if variante_id is not None:
        get_variant(db, context, variante_id)
        filters.append(MovimientoInventario.variante_id == variante_id)
    count = db.scalar(select(func.count()).select_from(MovimientoInventario).where(*filters)) or 0
    rows = db.scalars(select(MovimientoInventario).where(*filters).order_by(MovimientoInventario.creado_en.desc(), MovimientoInventario.id.desc()).limit(limit).offset(offset)).all()
    return ListaMovimientos(items=[MovimientoResponse.model_validate(row) for row in rows], total=count, limit=limit, offset=offset)
