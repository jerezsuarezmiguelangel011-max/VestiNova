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
    AjusteCreate, ExistenciaResponse, ListaExistencias, ListaMovimientos,
    MovimientoCreate, MovimientoResponse, ReingresoCreate,
)
from app.models import Existencia, MovimientoInventario, Producto, VarianteProducto, utc_now
from app.compras_reservas.postventa.persistence import SolicitudPostventa
from app.catalogo_abastecimiento.categories import get_category
from app.catalogo_abastecimiento.productos import get_product
from app.catalogo_abastecimiento.variantes import get_variant
from app.tenancy import TenantContext, authorized_branch, require_permission


router = APIRouter(prefix="/api/admin", tags=["Inventario"])



def replay(
    db: Session, context: TenantContext, payload: MovimientoCreate, *,
    clase: str = "MOVIMIENTO", origen_tipo: str | None = None,
    origen_id: str | None = None,
) -> MovimientoInventario | None:
    """Reenvíos con el mismo UUID solo se aceptan si todos los datos coinciden."""
    existing = db.get(MovimientoInventario, str(payload.id))
    if existing is None:
        return None
    delta = payload.cantidad if payload.tipo == "ENTRADA" else -payload.cantidad
    if (
        existing.empresa_id, existing.sucursal_id, existing.variante_id,
        existing.usuario_id, existing.tipo, existing.delta, existing.motivo,
        existing.clase, existing.origen_tipo, existing.origen_id,
    ) != (
        context.empresa_id, payload.sucursal_id, payload.variante_id,
        context.usuario.id, payload.tipo, delta, payload.motivo,
        clase, origen_tipo, origen_id,
    ):
        raise HTTPException(409, "El identificador de operación ya fue utilizado con otros datos.")
    return existing


def _apply_movement(
    payload: MovimientoCreate, response: Response, context: TenantContext,
    db: Session, *, clase: str, origen_tipo: str | None = None,
    origen_id: str | None = None,
) -> MovimientoInventario:
    """Transacción única; las salidas respetan el stock comprometido."""
    authorized_branch(db, context, payload.sucursal_id)
    variant = get_variant(db, context, payload.variante_id)
    previous = replay(
        db, context, payload, clase=clase, origen_tipo=origen_tipo, origen_id=origen_id
    )
    if previous is not None:
        response.status_code = 200
        return previous

    product = get_product(db, variant.producto_id, context.empresa_id)
    if not variant.activo or not product.activo:
        raise HTTPException(409, "Activa el producto y la variante antes de registrar movimientos nuevos.")

    key = {
        "empresa_id": context.empresa_id,
        "sucursal_id": payload.sucursal_id,
        "variante_id": payload.variante_id,
    }
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    # La fila existe aun cuando la variante no tenia saldo. El UPSERT resuelve
    # la primera operación concurrente; SELECT FOR UPDATE serializa los cambios.
    db.execute(
        insert(Existencia).values(
            **key, cantidad=0, cantidad_comprometida=0, actualizado_en=utc_now()
        ).on_conflict_do_nothing(index_elements=list(key))
    )
    balance = db.scalar(
        select(Existencia).where(
            *(getattr(Existencia, name) == value for name, value in key.items())
        ).with_for_update()
    )
    previous = replay(
        db, context, payload, clase=clase, origen_tipo=origen_tipo, origen_id=origen_id
    )
    if previous is not None:
        db.rollback()
        response.status_code = 200
        return previous

    if clase == "REINGRESO":
        other = db.scalar(
            select(MovimientoInventario.id).where(
                MovimientoInventario.empresa_id == context.empresa_id,
                MovimientoInventario.variante_id == payload.variante_id,
                MovimientoInventario.origen_tipo == origen_tipo,
                MovimientoInventario.origen_id == origen_id,
            ).limit(1)
        )
        if other is not None:
            db.rollback()
            raise HTTPException(409, "Este reingreso de postventa ya fue registrado para la variante.")

    delta = payload.cantidad if payload.tipo == "ENTRADA" else -payload.cantidad
    resulting = balance.cantidad + delta
    if resulting < balance.cantidad_comprometida or resulting > 2_000_000_000:
        db.rollback()
        raise HTTPException(
            409,
            "Stock insuficiente: el movimiento no puede consumir unidades comprometidas. "
            "Actualiza las existencias e intenta nuevamente.",
        )

    balance.cantidad = resulting
    balance.actualizado_en = utc_now()
    movement = MovimientoInventario(
        id=str(payload.id), **key, usuario_id=context.usuario.id,
        tipo=payload.tipo, clase=clase, origen_tipo=origen_tipo, origen_id=origen_id,
        delta=delta, saldo_resultante=resulting, motivo=payload.motivo,
    )
    db.add(movement)
    record_audit_event(
        db, context, accion=f"inventario.{clase.lower()}",
        entidad="inventario", entidad_id=str(payload.id),
        detalles={
            "sucursal_id": payload.sucursal_id, "variante_id": payload.variante_id,
            "delta": delta, "stock_fisico": resulting,
            "stock_comprometido": balance.cantidad_comprometida,
            "motivo": payload.motivo, "origen_id": origen_id,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = replay(
            db, context, payload, clase=clase, origen_tipo=origen_tipo, origen_id=origen_id
        )
        if previous is None:
            raise HTTPException(
                409, "La operación entró en conflicto; no se alteró el inventario."
            ) from None
        response.status_code = 200
        return previous
    return movement


@router.post("/inventario/movimientos", response_model=MovimientoResponse, status_code=201)
def register_movement(
    payload: MovimientoCreate, response: Response,
    context: TenantContext = Depends(require_permission("inventario.registrar", mutation=True)),
    db: Session = Depends(get_db),
):
    """Entradas/salidas operativas existentes; compatibilidad con CU06."""
    return _apply_movement(payload, response, context, db, clase="MOVIMIENTO")


@router.post("/inventario/ajustes", response_model=MovimientoResponse, status_code=201)
def register_adjustment(
    payload: AjusteCreate, response: Response,
    context: TenantContext = Depends(require_permission("inventario.ajustar", mutation=True)),
    db: Session = Depends(get_db),
):
    """Ajuste manual explícito, auditado e idempotente."""
    movement = MovimientoCreate(
        id=payload.id, sucursal_id=payload.sucursal_id,
        variante_id=payload.variante_id,
        tipo="ENTRADA" if payload.tipo == "INCREMENTO" else "SALIDA",
        cantidad=payload.cantidad, motivo=payload.motivo,
    )
    return _apply_movement(movement, response, context, db, clase="AJUSTE")


@router.post("/inventario/reingresos", response_model=MovimientoResponse, status_code=201)
def register_return_entry(
    payload: ReingresoCreate, response: Response,
    context: TenantContext = Depends(require_permission("inventario.ajustar", mutation=True)),
    db: Session = Depends(get_db),
):
    """Reingreso verificable de una solicitud de postventa completada.

    No es un ajuste manual arbitrario; requiere origen real de postventa,
    verificación expresa de aptitud y cantidad exacta de la línea.
    """
    if "postventa.consultar" not in context.permisos:
        raise HTTPException(403, "No tienes permiso para verificar solicitudes de postventa.")
    authorized_branch(db, context, payload.sucursal_id)
    request = db.scalar(
        select(SolicitudPostventa)
        .where(
            SolicitudPostventa.id == str(payload.solicitud_id),
            SolicitudPostventa.empresa_id == context.empresa_id,
            SolicitudPostventa.sucursal_id == payload.sucursal_id,
        )
        .with_for_update()
    )
    if request is None:
        raise HTTPException(404, "Solicitud de postventa no disponible para esta empresa y sucursal.")
    if request.estado != "COMPLETADA":
        raise HTTPException(409, "La solicitud de postventa debe estar completada antes del reingreso.")
    matching = [
        line for line in request.line_records
        if type(line.variante_ref) is int and line.variante_ref == payload.variante_id
    ]
    if len(matching) != 1 or matching[0].cantidad != payload.cantidad:
        raise HTTPException(
            422, "La variante y la cantidad deben coincidir con la prenda de la postventa."
        )
    movement = MovimientoCreate(
        id=payload.id, sucursal_id=payload.sucursal_id,
        variante_id=payload.variante_id, tipo="ENTRADA",
        cantidad=payload.cantidad, motivo=payload.motivo,
    )
    return _apply_movement(
        movement, response, context, db,
        clase="REINGRESO", origen_tipo="POSTVENTA",
        origen_id=str(payload.solicitud_id),
    )


@router.get("/inventario/existencias", response_model=ListaExistencias)
def list_balances(
    sucursal_id: int = Query(gt=0),
    producto_id: int | None = Query(default=None, gt=0),
    categoria_id: int | None = Query(default=None, gt=0),
    variante_id: int | None = Query(default=None, gt=0),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission("inventario.consultar")),
    db: Session = Depends(get_db),
):
    authorized_branch(db, context, sucursal_id)
    # Identificadores explícitos deben pertenecer al tenant. Una referencia
    # ajena no se presenta como un resultado vacío de la empresa actual.
    if producto_id is not None:
        get_product(db, producto_id, context.empresa_id)
    if categoria_id is not None:
        get_category(db, context, categoria_id)
    if variante_id is not None:
        get_variant(db, context, variante_id)
    filters = [
        Existencia.empresa_id == context.empresa_id,
        Existencia.sucursal_id == sucursal_id,
    ]
    if producto_id is not None:
        filters.append(Producto.id == producto_id)
    if categoria_id is not None:
        filters.append(Producto.categoria_id == categoria_id)
    if variante_id is not None:
        filters.append(VarianteProducto.id == variante_id)
    if q and q.strip():
        filters.append(func.lower(Producto.nombre).contains(q.strip().lower(), autoescape=True))

    # La unión conserva el ámbito empresarial y permite mostrar datos legibles
    # de cada variante sin aceptar información de otra empresa.
    query = (
        select(Existencia, Producto, VarianteProducto)
        .join(
            VarianteProducto,
            (VarianteProducto.id == Existencia.variante_id)
            & (VarianteProducto.empresa_id == Existencia.empresa_id),
        )
        .join(
            Producto,
            (Producto.id == VarianteProducto.producto_id)
            & (Producto.empresa_id == Existencia.empresa_id),
        )
        .where(*filters)
    )
    total = db.scalar(
        query.with_only_columns(func.count(), maintain_column_froms=True).order_by(None)
    ) or 0
    rows = db.execute(
        query.order_by(Existencia.variante_id).limit(limit).offset(offset)
    ).all()
    items = [
        ExistenciaResponse(
            empresa_id=balance.empresa_id,
            sucursal_id=balance.sucursal_id,
            variante_id=balance.variante_id,
            cantidad=balance.cantidad,
            cantidad_comprometida=balance.cantidad_comprometida,
            cantidad_disponible=balance.cantidad - balance.cantidad_comprometida,
            actualizado_en=balance.actualizado_en,
            producto_id=product.id,
            producto_nombre=product.nombre,
            categoria_id=product.categoria_id,
            talla=variant.talla,
            color=variant.color,
        )
        for balance, product, variant in rows
    ]
    return ListaExistencias(items=items, total=total, limit=limit, offset=offset)


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
