"""CU06: proveedores, órdenes de abastecimiento y recepciones de inventario."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.db import get_db
from app.models import (
    AccesoSucursal, Existencia, LineaAbastecimiento, LineaRecepcionAbastecimiento, MovimientoInventario,
    OrdenAbastecimiento, Producto, Proveedor, RecepcionAbastecimiento, Sucursal,
    VarianteProducto, utc_now,
)
from app.tenancy import TenantContext, authorized_branch, require_permission


router = APIRouter(prefix="/api/admin/abastecimiento", tags=["CU06 Â· Abastecimiento y compras"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupplierCreate(Input):
    codigo: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    nombre: str = Field(min_length=2, max_length=120)
    contacto: str = Field(default="", max_length=120)
    correo: str = Field(default="", max_length=254)
    telefono: str = Field(default="", max_length=40)

    @field_validator("codigo")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("correo")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and ("@" not in normalized or any(char.isspace() for char in normalized)):
            raise ValueError("Introduce un correo vÃ¡lido.")
        return normalized


class SupplierPatch(Input):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    contacto: str | None = Field(default=None, max_length=120)
    correo: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def changes_required(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("EnvÃ­a al menos un cambio no nulo.")
        return self


class SupplierResponse(BaseModel):
    id: int
    empresa_id: int
    codigo: str
    nombre: str
    contacto: str
    correo: str
    telefono: str
    activo: bool


class VariantOptionResponse(BaseModel):
    id: int
    producto_id: int
    producto: str
    talla: str
    color: str
    precio: str


class OrderLineCreate(Input):
    variante_id: int = Field(gt=0, strict=True)
    cantidad: int = Field(gt=0, le=1_000_000, strict=True)
    costo_unitario: Decimal = Field(gt=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2, allow_inf_nan=False)


class OrderCreate(Input):
    proveedor_id: int = Field(gt=0, strict=True)
    sucursal_id: int = Field(gt=0, strict=True)
    observaciones: str = Field(default="", max_length=500)
    lineas: list[OrderLineCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_variants(self):
        ids = [line.variante_id for line in self.lineas]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada variante debe aparecer una sola vez en la orden.")
        return self


class ReceiveLine(Input):
    linea_id: int = Field(gt=0, strict=True)
    cantidad: int = Field(gt=0, le=1_000_000, strict=True)


class ReceiveCreate(Input):
    id: UUID
    lineas: list[ReceiveLine] = Field(min_length=1, max_length=200)

    @field_validator("lineas")
    @classmethod
    def unique_lines(cls, values: list[ReceiveLine]) -> list[ReceiveLine]:
        ids = [line.linea_id for line in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada lÃ­nea puede recibirse una sola vez por operaciÃ³n.")
        return values


class OrderLineResponse(BaseModel):
    id: int
    producto_id: int
    producto: str
    talla: str
    color: str
    cantidad_solicitada: int
    cantidad_recibida: int
    costo_unitario: str


class OrderResponse(BaseModel):
    id: int
    empresa_id: int
    sucursal_id: int
    sucursal: str
    proveedor_id: int
    proveedor: str
    usuario_id: int
    estado: str
    observaciones: str
    creado_en: datetime
    actualizado_en: datetime
    total: str
    lineas: list[OrderLineResponse]


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int


def _supplier(db: Session, empresa_id: int, proveedor_id: int, *, active: bool = False) -> Proveedor:
    statement = select(Proveedor).where(Proveedor.id == proveedor_id, Proveedor.empresa_id == empresa_id)
    if active:
        statement = statement.where(Proveedor.activo.is_(True))
    result = db.scalar(statement)
    if result is None:
        raise HTTPException(404, "Proveedor no disponible para esta empresa.")
    return result


def _order(db: Session, context: TenantContext, order_id: int, *, lock: bool = False) -> OrdenAbastecimiento:
    statement = select(OrdenAbastecimiento).where(
        OrdenAbastecimiento.id == order_id, OrdenAbastecimiento.empresa_id == context.empresa_id
    )
    if lock:
        statement = statement.with_for_update()
    result = db.scalar(statement)
    if result is None:
        raise HTTPException(404, "Orden de abastecimiento no encontrada.")
    return result


def _order_view(db: Session, order: OrdenAbastecimiento) -> OrderResponse:
    branch = db.get(Sucursal, order.sucursal_id)
    supplier = db.get(Proveedor, order.proveedor_id)
    lines = db.scalars(select(LineaAbastecimiento).where(
        LineaAbastecimiento.empresa_id == order.empresa_id,
        LineaAbastecimiento.orden_id == order.id,
    ).order_by(LineaAbastecimiento.id)).all()
    response_lines = []
    total = Decimal("0.00")
    for line in lines:
        variant = db.get(VarianteProducto, line.variante_id)
        product = db.get(Producto, variant.producto_id) if variant else None
        if variant is None or product is None:
            raise HTTPException(503, "No se pudo verificar una lÃ­nea de la orden.")
        total += line.costo_unitario * line.cantidad_solicitada
        response_lines.append(OrderLineResponse(
            id=line.id, producto_id=product.id, producto=product.nombre,
            talla=variant.talla, color=variant.color,
            cantidad_solicitada=line.cantidad_solicitada, cantidad_recibida=line.cantidad_recibida,
            costo_unitario=f"{line.costo_unitario:.2f}",
        ))
    if branch is None or supplier is None:
        raise HTTPException(503, "No se pudo verificar la sucursal o proveedor de la orden.")
    return OrderResponse(
        id=order.id, empresa_id=order.empresa_id, sucursal_id=order.sucursal_id, sucursal=branch.nombre,
        proveedor_id=order.proveedor_id, proveedor=supplier.nombre, usuario_id=order.usuario_id,
        estado=order.estado, observaciones=order.observaciones, creado_en=order.creado_en,
        actualizado_en=order.actualizado_en, total=f"{total:.2f}", lineas=response_lines,
    )


def _matching_receipt(db: Session, context: TenantContext, order: OrdenAbastecimiento, payload: ReceiveCreate) -> bool:
    receipt = db.get(RecepcionAbastecimiento, str(payload.id))
    if receipt is None:
        return False
    actual = {
        row.linea_id: row.cantidad
        for row in db.scalars(select(LineaRecepcionAbastecimiento).where(
            LineaRecepcionAbastecimiento.recepcion_id == receipt.id,
            LineaRecepcionAbastecimiento.empresa_id == context.empresa_id,
            LineaRecepcionAbastecimiento.orden_id == order.id,
        )).all()
    }
    expected = {line.linea_id: line.cantidad for line in payload.lineas}
    if (receipt.empresa_id, receipt.orden_id, receipt.usuario_id, actual) != (
        context.empresa_id, order.id, context.usuario.id, expected
    ):
        raise HTTPException(409, "El identificador de recepciÃ³n ya se usÃ³ con otros datos.")
    return True


@router.get("/proveedores", response_model=list[SupplierResponse])
def list_suppliers(
    estado: Literal["activos", "inactivos", "todos"] = "activos",
    q: str | None = Query(default=None, max_length=120),
    context: TenantContext = Depends(require_permission("abastecimiento.consultar")),
    db: Session = Depends(get_db),
):
    statement = select(Proveedor).where(Proveedor.empresa_id == context.empresa_id)
    if estado == "activos":
        statement = statement.where(Proveedor.activo.is_(True))
    elif estado == "inactivos":
        statement = statement.where(Proveedor.activo.is_(False))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(Proveedor.nombre.ilike(pattern) | Proveedor.codigo.ilike(pattern))
    return db.scalars(statement.order_by(Proveedor.nombre, Proveedor.id)).all()


@router.post("/proveedores", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreate,
    context: TenantContext = Depends(require_permission("abastecimiento.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    supplier = Proveedor(empresa_id=context.empresa_id, **payload.model_dump(), activo=True)
    db.add(supplier)
    try:
        db.flush()
        record_audit_event(db, context, accion="proveedor.creado", entidad="proveedor", entidad_id=supplier.id,
                           detalles={"codigo": supplier.codigo, "nombre": supplier.nombre})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un proveedor con ese cÃ³digo.") from None
    return supplier


@router.patch("/proveedores/{proveedor_id}", response_model=SupplierResponse)
def update_supplier(
    proveedor_id: int,
    payload: SupplierPatch,
    context: TenantContext = Depends(require_permission("abastecimiento.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    supplier = _supplier(db, context.empresa_id, proveedor_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(supplier, field, value)
    record_audit_event(db, context, accion="proveedor.actualizado", entidad="proveedor", entidad_id=supplier.id,
                       detalles={"campos": sorted(changes), "nombre": supplier.nombre})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar el proveedor.") from None
    return supplier


@router.get("/variantes", response_model=list[VariantOptionResponse])
def list_orderable_variants(
    q: str | None = Query(default=None, max_length=120),
    context: TenantContext = Depends(require_permission("abastecimiento.consultar")),
    db: Session = Depends(get_db),
):
    statement = select(VarianteProducto, Producto).join(
        Producto, (Producto.id == VarianteProducto.producto_id) & (Producto.empresa_id == VarianteProducto.empresa_id)
    ).where(
        VarianteProducto.empresa_id == context.empresa_id,
        VarianteProducto.activo.is_(True),
        Producto.activo.is_(True),
    )
    if q and q.strip():
        statement = statement.where(Producto.nombre.ilike(f"%{q.strip()}%"))
    rows = db.execute(statement.order_by(Producto.nombre, VarianteProducto.talla, VarianteProducto.color)).all()
    return [VariantOptionResponse(
        id=variant.id, producto_id=product.id, producto=product.nombre,
        talla=variant.talla, color=variant.color, precio=f"{product.precio:.2f}",
    ) for variant, product in rows]


@router.get("/ordenes", response_model=OrderListResponse)
def list_orders(
    estado: Literal["todas", "pendientes", "parciales", "recibidas", "canceladas"] = "todas",
    sucursal_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission("abastecimiento.consultar")),
    db: Session = Depends(get_db),
):
    statement = select(OrdenAbastecimiento).where(OrdenAbastecimiento.empresa_id == context.empresa_id)
    allowed = select(Sucursal.id).where(Sucursal.empresa_id == context.empresa_id, Sucursal.activo.is_(True))
    if not context.administrador_empresa:
        allowed = allowed.join(AccesoSucursal, (AccesoSucursal.sucursal_id == Sucursal.id) & (AccesoSucursal.empresa_id == Sucursal.empresa_id)).where(AccesoSucursal.administrador_id == context.usuario.id)
    statement = statement.where(OrdenAbastecimiento.sucursal_id.in_(allowed))
    selected_state = {"pendientes": "PENDIENTE", "parciales": "PARCIAL", "recibidas": "RECIBIDA", "canceladas": "CANCELADA"}.get(estado)
    if selected_state:
        statement = statement.where(OrdenAbastecimiento.estado == selected_state)
    if sucursal_id is not None:
        statement = statement.where(OrdenAbastecimiento.sucursal_id == sucursal_id)
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    orders = db.scalars(statement.order_by(OrdenAbastecimiento.creado_en.desc(), OrdenAbastecimiento.id.desc()).limit(limit).offset(offset)).all()
    return OrderListResponse(items=[_order_view(db, order) for order in orders], total=count, limit=limit, offset=offset)


@router.get("/ordenes/{orden_id}", response_model=OrderResponse)
def order_detail(
    orden_id: int,
    context: TenantContext = Depends(require_permission("abastecimiento.consultar")),
    db: Session = Depends(get_db),
):
    order = _order(db, context, orden_id)
    authorized_branch(db, context, order.sucursal_id)
    return _order_view(db, order)


@router.post("/ordenes", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    context: TenantContext = Depends(require_permission("abastecimiento.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    branch = authorized_branch(db, context, payload.sucursal_id)
    supplier = _supplier(db, context.empresa_id, payload.proveedor_id, active=True)
    variants = db.scalars(select(VarianteProducto).where(
        VarianteProducto.empresa_id == context.empresa_id,
        VarianteProducto.id.in_([line.variante_id for line in payload.lineas]),
        VarianteProducto.activo.is_(True),
    )).all()
    variant_by_id = {item.id: item for item in variants}
    products = db.scalars(select(Producto).where(
        Producto.empresa_id == context.empresa_id,
        Producto.id.in_({item.producto_id for item in variants}),
        Producto.activo.is_(True),
    )).all()
    if len(variant_by_id) != len(payload.lineas) or len(products) != len({item.producto_id for item in variants}):
        raise HTTPException(422, "Cada lÃ­nea debe apuntar a una variante activa del catÃ¡logo de esta empresa.")
    order = OrdenAbastecimiento(
        empresa_id=context.empresa_id, sucursal_id=branch.id, proveedor_id=supplier.id,
        usuario_id=context.usuario.id, estado="PENDIENTE", observaciones=payload.observaciones,
        creado_en=utc_now(), actualizado_en=utc_now(),
    )
    db.add(order)
    try:
        db.flush()
        db.add_all(LineaAbastecimiento(
            empresa_id=context.empresa_id, orden_id=order.id, variante_id=line.variante_id,
            cantidad_solicitada=line.cantidad, cantidad_recibida=0, costo_unitario=line.costo_unitario,
        ) for line in payload.lineas)
        record_audit_event(db, context, accion="abastecimiento.orden_creada", entidad="orden_abastecimiento", entidad_id=order.id,
                           detalles={"proveedor": supplier.nombre, "sucursal": branch.nombre, "lineas": len(payload.lineas)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo registrar la orden de abastecimiento.") from None
    return _order_view(db, order)


@router.post("/ordenes/{orden_id}/recepciones", response_model=OrderResponse)
def receive_order(
    orden_id: int,
    payload: ReceiveCreate,
    response: Response,
    context: TenantContext = Depends(require_permission("abastecimiento.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    order = _order(db, context, orden_id, lock=True)
    authorized_branch(db, context, order.sucursal_id)
    if _matching_receipt(db, context, order, payload):
        response.status_code = status.HTTP_200_OK
        return _order_view(db, order)
    if order.estado not in {"PENDIENTE", "PARCIAL"}:
        raise HTTPException(409, "Solo se reciben órdenes pendientes o parcialmente recibidas.")

    requested = {line.linea_id: line.cantidad for line in payload.lineas}
    order_lines = db.scalars(select(LineaAbastecimiento).where(
        LineaAbastecimiento.empresa_id == context.empresa_id,
        LineaAbastecimiento.orden_id == order.id,
        LineaAbastecimiento.id.in_(requested),
    ).with_for_update()).all()
    line_by_id = {line.id: line for line in order_lines}
    if set(line_by_id) != set(requested):
        raise HTTPException(422, "La recepciÃ³n contiene lÃ­neas que no pertenecen a esta orden.")
    variants = {item.id: item for item in db.scalars(select(VarianteProducto).where(
        VarianteProducto.empresa_id == context.empresa_id,
        VarianteProducto.id.in_({line.variante_id for line in order_lines}),
    )).all()}
    products = {item.id: item for item in db.scalars(select(Producto).where(
        Producto.empresa_id == context.empresa_id,
        Producto.id.in_({variant.producto_id for variant in variants.values()}),
    )).all()}

    prepared = []
    for line_id, quantity in requested.items():
        line = line_by_id[line_id]
        variant = variants.get(line.variante_id)
        product = products.get(variant.producto_id) if variant else None
        if variant is None or product is None or not variant.activo or not product.activo:
            raise HTTPException(409, "No se puede recibir una variante inactiva o ajena al catÃ¡logo.")
        if line.cantidad_recibida + quantity > line.cantidad_solicitada:
            raise HTTPException(409, "La cantidad recibida supera lo pendiente en la orden.")
        stock = db.scalar(select(Existencia).where(
            Existencia.empresa_id == context.empresa_id,
            Existencia.sucursal_id == order.sucursal_id,
            Existencia.variante_id == variant.id,
        ).with_for_update())
        current = stock.cantidad if stock else 0
        if current + quantity > 2_000_000_000:
            raise HTTPException(409, "La recepciÃ³n supera el lÃ­mite permitido de existencias.")
        prepared.append((line, variant, quantity, current))

    receipt_id = str(payload.id)
    receipt = RecepcionAbastecimiento(
        id=receipt_id, empresa_id=context.empresa_id, orden_id=order.id,
        usuario_id=context.usuario.id, recibido_en=utc_now(),
    )
    db.add(receipt)
    movement_insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    try:
        for line, variant, quantity, _current in prepared:
            key = {"empresa_id": context.empresa_id, "sucursal_id": order.sucursal_id, "variante_id": variant.id}
            db.execute(movement_insert(Existencia).values(
                **key, cantidad=0, actualizado_en=utc_now(),
            ).on_conflict_do_nothing(index_elements=list(key)))
            stock = db.scalar(select(Existencia).where(
                Existencia.empresa_id == context.empresa_id,
                Existencia.sucursal_id == order.sucursal_id,
                Existencia.variante_id == variant.id,
            ).with_for_update())
            if stock is None:
                raise HTTPException(503, "No se pudo reservar el saldo de inventario.")
            # El bloqueo de existencias protege las recepciones de CU06 y los ajustes de CU07.
            result = stock.cantidad + quantity
            if result > 2_000_000_000:
                raise HTTPException(409, "La recepciÃ³n supera el lÃ­mite permitido de existencias.")
            stock.cantidad = result
            stock.actualizado_en = utc_now()
            line.cantidad_recibida += quantity
            db.add(MovimientoInventario(
                id=str(uuid4()), empresa_id=context.empresa_id, sucursal_id=order.sucursal_id,
                variante_id=variant.id, usuario_id=context.usuario.id, tipo="ENTRADA",
                motivo=f"RecepciÃ³n de orden {order.id}", delta=quantity, saldo_resultante=result,
            ))
            db.add(LineaRecepcionAbastecimiento(
                recepcion_id=receipt_id, linea_id=line.id, empresa_id=context.empresa_id,
                orden_id=order.id, cantidad=quantity,
            ))
        order.estado = "RECIBIDA" if all(
            line.cantidad_recibida == line.cantidad_solicitada for line in db.scalars(select(LineaAbastecimiento).where(
                LineaAbastecimiento.empresa_id == context.empresa_id,
                LineaAbastecimiento.orden_id == order.id,
            )).all()
        ) else "PARCIAL"
        order.actualizado_en = utc_now()
        record_audit_event(db, context, accion="abastecimiento.recepcion_registrada", entidad="orden_abastecimiento", entidad_id=order.id,
                           detalles={"recepcion_id": receipt_id, "lineas": len(prepared)})
        db.commit()
    except IntegrityError:
        db.rollback()
        retry_order = _order(db, context, orden_id)
        if _matching_receipt(db, context, retry_order, payload):
            response.status_code = status.HTTP_200_OK
            return _order_view(db, retry_order)
        raise HTTPException(409, "No se pudo confirmar la recepciÃ³n; el inventario no fue modificado.") from None
    except HTTPException:
        db.rollback()
        raise
    return _order_view(db, order)


@router.post("/ordenes/{orden_id}/cancelar", response_model=OrderResponse)
def cancel_order(
    orden_id: int,
    context: TenantContext = Depends(require_permission("abastecimiento.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    order = _order(db, context, orden_id, lock=True)
    authorized_branch(db, context, order.sucursal_id)
    if order.estado != "PENDIENTE":
        raise HTTPException(409, "Solo se cancelan órdenes pendientes que no tengan recepciones.")
    order.estado = "CANCELADA"
    order.actualizado_en = utc_now()
    record_audit_event(db, context, accion="abastecimiento.orden_cancelada", entidad="orden_abastecimiento", entidad_id=order.id,
                       detalles={"proveedor_id": order.proveedor_id})
    db.commit()
    return _order_view(db, order)
