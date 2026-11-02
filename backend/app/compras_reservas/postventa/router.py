"""Solicitudes de devolución y cambio, con autorización por cliente y sucursal."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.compras_reservas.compras.domain import Purchase, PurchaseUnavailable, identifier_token
from app.compras_reservas.compras.persistence import find_purchase_for_customer
from app.compras_reservas.postventa.persistence import LineaSolicitudPostventa, SolicitudPostventa
from app.db import get_db
from app.models import Cliente, Empresa, SesionCliente, Sucursal, utc_now
from app.organizacion_empresarial.audit import record_audit_event
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, require_permission


customer_router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/postventa", tags=["CU17 · Cambios y devoluciones"])
staff_router = APIRouter(prefix="/api/admin/postventa/solicitudes", tags=["CU17 · Gestión de postventa"])


class ItemSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producto_id: StrictInt = Field(gt=0)
    cantidad: StrictInt = Field(gt=0, le=2_147_483_647)


class CrearSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    compra_id: UUID
    tipo: Literal["CAMBIO", "DEVOLUCION"]
    motivo: str = Field(min_length=3, max_length=1000)
    items: list[ItemSolicitud] = Field(min_length=1, max_length=30)

    @field_validator("motivo")
    @classmethod
    def nonempty_reason(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Explica el motivo con al menos 3 caracteres.")
        return value.strip()

    @model_validator(mode="after")
    def unique_products(self):
        product_ids = [item.producto_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Indica cada prenda una sola vez por solicitud.")
        return self


class DecisionSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    estado: Literal["APROBADA", "RECHAZADA"]
    respuesta: str | None = Field(default=None, max_length=1000)

    @field_validator("respuesta")
    @classmethod
    def clean_response(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


def solicitud_response(request: SolicitudPostventa) -> dict:
    return {
        "id": request.id,
        "compra_id": request.compra_id,
        "tipo": request.tipo,
        "estado": request.estado,
        "motivo": request.motivo,
        "respuesta": request.respuesta,
        "referencia_reposicion": request.referencia_reposicion,
        "creado_en": request.creado_en.isoformat(),
        "actualizado_en": request.actualizado_en.isoformat(),
        "resuelto_en": request.resuelto_en.isoformat() if request.resuelto_en else None,
        "completado_en": request.completado_en.isoformat() if request.completado_en else None,
        "items": [
            {
                "producto_id": line.producto_id,
                "nombre": line.nombre,
                "variante_id": line.variante_ref,
                "cantidad": line.cantidad,
                "precio_unitario": f"{line.precio_unitario:.2f}",
            }
            for line in request.line_records
        ],
    }


def _purchase_for_request(db: Session, company: Empresa, customer: Cliente, payload: CrearSolicitud) -> Purchase:
    try:
        purchase = find_purchase_for_customer(db, company.id, customer.id, payload.compra_id, lock=True)
    except PurchaseUnavailable:
        raise HTTPException(503, "No se pudo verificar la compra guardada.") from None
    if purchase is None:
        raise HTTPException(404, "La compra no está disponible en esta cuenta.")
    if type(purchase.context.sucursal_id) is not int or purchase.context.sucursal_id < 1:
        raise HTTPException(409, "La compra no tiene una sucursal válida para tramitar la solicitud.")
    return purchase


@customer_router.get("")
def customer_requests(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    filters = (SolicitudPostventa.empresa_id == company.id, SolicitudPostventa.cliente_id == customer.id)
    total = db.scalar(select(func.count()).select_from(SolicitudPostventa).where(*filters)) or 0
    rows = db.scalars(
        select(SolicitudPostventa)
        .where(*filters)
        .options(selectinload(SolicitudPostventa.line_records))
        .order_by(SolicitudPostventa.creado_en.desc(), SolicitudPostventa.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": [solicitud_response(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@customer_router.post("", status_code=201)
def create_customer_request(
    payload: CrearSolicitud,
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    purchase = _purchase_for_request(db, company, customer, payload)
    existing = db.get(SolicitudPostventa, str(payload.id))
    if existing is not None:
        same_items = sorted((line.producto_id, line.cantidad) for line in existing.line_records) == sorted(
            (item.producto_id, item.cantidad) for item in payload.items
        )
        if (existing.empresa_id == company.id and existing.cliente_id == customer.id
                and existing.compra_id == str(payload.compra_id) and existing.tipo == payload.tipo
                and existing.motivo == payload.motivo and same_items):
            return solicitud_response(existing)
        raise HTTPException(409, "El identificador de solicitud ya fue utilizado.")

    purchase_lines = {line.producto_id: (position, line) for position, line in enumerate(purchase.lines)}
    active_quantities = db.execute(
        select(
            LineaSolicitudPostventa.producto_id,
            func.sum(LineaSolicitudPostventa.cantidad),
        )
        .join(SolicitudPostventa, SolicitudPostventa.id == LineaSolicitudPostventa.solicitud_id)
        .where(
            SolicitudPostventa.empresa_id == company.id,
            SolicitudPostventa.cliente_id == customer.id,
            SolicitudPostventa.compra_id == str(payload.compra_id),
            SolicitudPostventa.estado.in_(("PENDIENTE", "APROBADA", "COMPLETADA")),
        )
        .group_by(LineaSolicitudPostventa.producto_id)
    ).all()
    already_requested = {product_id: int(quantity or 0) for product_id, quantity in active_quantities}
    lines = []
    for item in payload.items:
        source = purchase_lines.get(item.producto_id)
        if source is None:
            raise HTTPException(422, "La solicitud incluye una prenda que no pertenece a esta compra.")
        position, purchase_line = source
        if already_requested.get(item.producto_id, 0) + item.cantidad > purchase_line.cantidad:
            raise HTTPException(409, "La cantidad supera las unidades de esta prenda que aún pueden tramitarse.")
        lines.append(
            LineaSolicitudPostventa(
                producto_id=purchase_line.producto_id,
                empresa_clave=identifier_token(company.id),
                compra_posicion=position,
                nombre=purchase_line.nombre,
                variante_ref=purchase_line.key.variante_id,
                cantidad=item.cantidad,
                precio_unitario=purchase_line.precio_unitario,
            )
        )
    branch = purchase.context.sucursal_id
    request = SolicitudPostventa(
        id=str(payload.id),
        empresa_id=company.id,
        empresa_clave=identifier_token(company.id),
        cliente_id=customer.id,
        compra_id=str(payload.compra_id),
        sucursal_id=branch,
        tipo=payload.tipo,
        estado="PENDIENTE",
        motivo=payload.motivo,
        actualizado_en=utc_now(),
        line_records=lines,
    )
    db.add(request)
    try:
        db.commit()
        db.refresh(request)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La solicitud entró en conflicto con otra operación. Actualiza la página.") from None
    return solicitud_response(request)


def _staff_request(db: Session, context: TenantContext, request_id: UUID) -> SolicitudPostventa:
    request = db.scalar(
        select(SolicitudPostventa)
        .where(SolicitudPostventa.id == str(request_id), SolicitudPostventa.empresa_id == context.empresa_id)
        .options(selectinload(SolicitudPostventa.line_records))
        .with_for_update()
    )
    if request is None:
        raise HTTPException(404, "La solicitud no está disponible para esta empresa.")
    authorized_branch(db, context, request.sucursal_id)
    return request


@staff_router.get("")
def list_staff_requests(
    response: Response,
    estado: Literal["PENDIENTE", "APROBADA", "RECHAZADA", "COMPLETADA"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission("postventa.consultar")),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    branch_ids = db.scalars(authorized_branches_statement(context).with_only_columns(Sucursal.id)).all()
    filters = [SolicitudPostventa.empresa_id == context.empresa_id, SolicitudPostventa.sucursal_id.in_(branch_ids)]
    if estado is not None:
        filters.append(SolicitudPostventa.estado == estado)
    total = db.scalar(select(func.count()).select_from(SolicitudPostventa).where(*filters)) or 0
    rows = db.scalars(
        select(SolicitudPostventa)
        .where(*filters)
        .options(selectinload(SolicitudPostventa.line_records))
        .order_by(SolicitudPostventa.creado_en.desc(), SolicitudPostventa.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for row in rows:
        customer = db.get(Cliente, row.cliente_id)
        item = solicitud_response(row)
        item["cliente"] = {"nombre": customer.nombre, "correo": customer.correo} if customer else None
        item["sucursal_id"] = row.sucursal_id
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@staff_router.patch("/{request_id}/decision")
def decide_request(
    request_id: UUID,
    payload: DecisionSolicitud,
    response: Response,
    context: TenantContext = Depends(require_permission("postventa.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    request = _staff_request(db, context, request_id)
    if request.estado != "PENDIENTE":
        raise HTTPException(409, "Solo se pueden revisar solicitudes pendientes.")
    now = utc_now()
    request.estado = payload.estado
    request.respuesta = payload.respuesta or None
    request.resuelto_por_id = context.usuario.id
    request.resuelto_en = now
    request.actualizado_en = now
    if payload.estado == "APROBADA" and request.tipo == "CAMBIO":
        request.referencia_reposicion = f"REP-{uuid4().hex[:10].upper()}"
    record_audit_event(
        db,
        context,
        accion=f"postventa.{payload.estado.lower()}",
        entidad="solicitud_postventa",
        entidad_id=request.id,
        detalles={"tipo": request.tipo, "compra_id": request.compra_id},
    )
    db.commit()
    db.refresh(request)
    return solicitud_response(request)


@staff_router.post("/{request_id}/completar")
def complete_request(
    request_id: UUID,
    response: Response,
    context: TenantContext = Depends(require_permission("postventa.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    request = _staff_request(db, context, request_id)
    if request.estado != "APROBADA":
        raise HTTPException(409, "Solo se pueden completar solicitudes aprobadas.")
    now = utc_now()
    request.estado = "COMPLETADA"
    request.actualizado_en = now
    request.completado_en = now
    record_audit_event(
        db,
        context,
        accion="postventa.completada",
        entidad="solicitud_postventa",
        entidad_id=request.id,
        detalles={"tipo": request.tipo, "compra_id": request.compra_id},
    )
    db.commit()
    db.refresh(request)
    return solicitud_response(request)
