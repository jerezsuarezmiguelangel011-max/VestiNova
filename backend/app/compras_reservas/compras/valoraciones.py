"""CU25: publicación y edición de opiniones de compras verificadas y entregadas."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseRecord, find_purchase_for_customer
from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt
from app.db import Base, get_db
from app.models import Cliente, Empresa, Producto, SesionCliente, utc_now
from app.organizacion_empresarial.audit import record_audit_event
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, lock_tenant_mutation, require_tenant


class EntregaCompra(Base):
    __tablename__ = "compras_digitales_entregas"
    __table_args__ = (
        ForeignKeyConstraint(["empresa_clave", "compra_id"],
                             ["compras_digitales.empresa_clave", "compras_digitales.id"],
                             name="fk_cu25_entrega_compra_tenant"),
    )
    compra_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    entregada_por_id: Mapped[int] = mapped_column(ForeignKey("administradores.id"), nullable=False)
    comprobacion: Mapped[str] = mapped_column(String(200), nullable=False)
    entregada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ValoracionCompra(Base):
    __tablename__ = "valoraciones_compra"
    __table_args__ = (
        ForeignKeyConstraint(["empresa_clave", "compra_id"],
                             ["compras_digitales.empresa_clave", "compras_digitales.id"],
                             name="fk_cu25_valoracion_compra_tenant"),
        ForeignKeyConstraint(["producto_id", "empresa_id"],
                             ["productos.id", "productos.empresa_id"],
                             name="fk_cu25_valoracion_producto_tenant"),
        UniqueConstraint("empresa_id", "compra_id", "producto_id", name="uq_cu25_valoracion_por_compra_producto"),
        CheckConstraint("puntuacion BETWEEN 1 AND 5", name="ck_cu25_puntuacion"),
        Index("ix_cu25_valoracion_producto", "empresa_id", "producto_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    compra_id: Mapped[str] = mapped_column(String(36), nullable=False)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    puntuacion: Mapped[int] = mapped_column(Integer, nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


staff_router = APIRouter(prefix="/api/admin/entregas-compras", tags=["CU25 · Entregas de compras digitales"])
customer_router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/valoraciones", tags=["CU25 · Valoraciones"])
public_router = APIRouter(prefix="/api/catalogo/productos", tags=["CU25 · Valoraciones públicas"])


class EntregaInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    identidad_verificada: bool
    comprobacion: str = Field(min_length=3, max_length=200)

    @field_validator("comprobacion")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Indica cómo se verificó la entrega.")
        return value.strip()


class ReviewContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    puntuacion: StrictInt = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)

    @field_validator("comentario")
    @classmethod
    def clean_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ReviewCreate(ReviewContent):
    compra_id: UUID
    producto_id: StrictInt = Field(gt=0)


def review_json(row: ValoracionCompra) -> dict:
    return {
        "id": row.id, "compra_id": row.compra_id, "producto_id": row.producto_id,
        "puntuacion": row.puntuacion, "comentario": row.comentario, "compra_verificada": True,
        "creado_en": row.creado_en.isoformat(), "actualizado_en": row.actualizado_en.isoformat(),
    }


def delivery_json(row: PurchaseRecord, delivery: EntregaCompra | None) -> dict:
    return {
        "id": row.id, "cliente_id": row.contexto["cliente_id"],
        "sucursal_id": row.contexto["sucursal_id"],
        "importe_total": f"{row.total:.2f}", "entrega": "ENTREGADA" if delivery else "PENDIENTE",
        "entregada_en": delivery.entregada_en.isoformat() if delivery else None,
        "items": [{"producto_id": line.producto_id, "nombre": line.nombre, "cantidad": line.cantidad}
                  for line in row.line_records],
    }


def staff_access(context: TenantContext) -> None:
    if context.acceso is None or context.acceso.codigo_sistema not in ("ADMINISTRADOR", "ENCARGADO_SUCURSAL", "CAJERO"):
        raise HTTPException(403, "La gestión de entregas requiere personal autorizado.")


@staff_router.get("")
def list_deliveries(
    response: Response,
    limit: int = Query(default=30, ge=1, le=100),
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    staff_access(context)
    allowed = select(authorized_branches_statement(context).subquery().c.id)
    rows = db.execute(
        select(PurchaseRecord, EntregaCompra)
        .join(CheckoutAttempt, CheckoutAttempt.id == PurchaseRecord.id)
        .outerjoin(EntregaCompra, EntregaCompra.compra_id == PurchaseRecord.id)
        .where(
            PurchaseRecord.empresa_clave == identifier_token(context.empresa_id),
            CheckoutAttempt.empresa_id == context.empresa_id,
            CheckoutAttempt.estado == "CONFIRMADA",
            CheckoutAttempt.sucursal_id.in_(allowed),
        ).order_by(PurchaseRecord.creado_en.desc()).limit(limit)
    ).all()
    return {"items": [delivery_json(row, delivery) for row, delivery in rows]}


@staff_router.post("/{compra_id}/confirmar")
def confirm_delivery(
    compra_id: UUID, payload: EntregaInput, response: Response,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    staff_access(context)
    if not payload.identidad_verificada:
        raise HTTPException(422, "Verifica la identidad antes de entregar la compra.")
    context = lock_tenant_mutation(db, context)
    row = db.scalar(select(PurchaseRecord).where(
        PurchaseRecord.id == str(compra_id),
        PurchaseRecord.empresa_clave == identifier_token(context.empresa_id),
    ).with_for_update())
    payment = db.scalar(select(CheckoutAttempt).where(
        CheckoutAttempt.id == str(compra_id), CheckoutAttempt.empresa_id == context.empresa_id,
        CheckoutAttempt.estado == "CONFIRMADA",
    ))
    if row is None or payment is None:
        raise HTTPException(404, "Compra confirmada no encontrada.")
    branch_id = row.contexto.get("sucursal_id")
    customer_id = row.contexto.get("cliente_id")
    if type(branch_id) is not int or type(customer_id) is not int:
        raise HTTPException(409, "Compra sin contexto verificable de cliente o sucursal.")
    authorized_branch(db, context, branch_id)
    delivery = db.get(EntregaCompra, str(compra_id))
    if delivery:
        response.status_code = 200
        return delivery_json(row, delivery)
    delivery = EntregaCompra(
        compra_id=str(compra_id), empresa_id=context.empresa_id,
        empresa_clave=identifier_token(context.empresa_id),
        cliente_id=customer_id, sucursal_id=branch_id,
        entregada_por_id=context.usuario.id, comprobacion=payload.comprobacion,
    )
    db.add(delivery)
    record_audit_event(db, context, accion="compra.entrega_confirmada", entidad="compra_digital",
                       entidad_id=str(compra_id), detalles={"sucursal_id": branch_id, "cliente_id": customer_id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La entrega ya fue procesada; actualiza la pantalla.") from None
    return delivery_json(row, delivery)


@customer_router.get("")
def my_reviews(
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    rows = db.scalars(select(ValoracionCompra).where(
        ValoracionCompra.empresa_id == company.id,
        ValoracionCompra.cliente_id == customer.id,
    ).order_by(ValoracionCompra.creado_en.desc()).limit(200)).all()
    return {"items": [review_json(item) for item in rows]}


@customer_router.post("", status_code=201)
def create_review(
    payload: ReviewCreate, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    purchase = find_purchase_for_customer(db, company.id, customer.id, payload.compra_id, lock=True)
    delivery = db.scalar(select(EntregaCompra).where(
        EntregaCompra.compra_id == str(payload.compra_id),
        EntregaCompra.empresa_id == company.id, EntregaCompra.cliente_id == customer.id,
    ))
    paid = db.scalar(select(CheckoutAttempt.id).where(
        CheckoutAttempt.id == str(payload.compra_id),
        CheckoutAttempt.empresa_id == company.id, CheckoutAttempt.cliente_id == customer.id,
        CheckoutAttempt.estado == "CONFIRMADA",
    ))
    if purchase is None or delivery is None or paid is None or payload.producto_id not in {line.producto_id for line in purchase.lines}:
        raise HTTPException(409, "Solo puedes valorar prendas de compras confirmadas y entregadas de tu cuenta.")
    existing = db.scalar(select(ValoracionCompra).where(
        ValoracionCompra.empresa_id == company.id,
        ValoracionCompra.compra_id == str(payload.compra_id),
        ValoracionCompra.producto_id == payload.producto_id,
    ))
    if existing:
        raise HTTPException(409, "Ya tienes una valoración para esta compra y producto; puedes editarla.")
    review = ValoracionCompra(
        empresa_id=company.id, empresa_clave=identifier_token(company.id),
        cliente_id=customer.id, compra_id=str(payload.compra_id),
        producto_id=payload.producto_id, puntuacion=payload.puntuacion,
        comentario=payload.comentario,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una valoración de esta compra y prenda.") from None
    return review_json(review)


@customer_router.patch("/{review_id}")
def edit_review(
    review_id: int, payload: ReviewContent, response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    review = db.scalar(select(ValoracionCompra).where(
        ValoracionCompra.id == review_id, ValoracionCompra.empresa_id == company.id,
        ValoracionCompra.cliente_id == customer.id,
    ).with_for_update())
    if review is None:
        raise HTTPException(404, "Valoración no encontrada en esta cuenta.")
    review.puntuacion = payload.puntuacion
    review.comentario = payload.comentario
    review.actualizado_en = utc_now()
    db.commit()
    return review_json(review)


@public_router.get("/{slug}/valoraciones")
def public_reviews(
    slug: str, tienda: str, response: Response,
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    product = db.scalar(select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
        Producto.slug == slug, Producto.activo.is_(True), Empresa.slug == tienda, Empresa.activo.is_(True),
    ))
    if product is None:
        raise HTTPException(404, "Prenda no publicada en esta tienda.")
    filters = [ValoracionCompra.empresa_id == product.empresa_id, ValoracionCompra.producto_id == product.id]
    reviews = db.scalars(select(ValoracionCompra).where(*filters).order_by(
        ValoracionCompra.creado_en.desc()).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(ValoracionCompra).where(*filters)) or 0
    return {"producto_id": product.id, "total": total, "items": [
        {"puntuacion": r.puntuacion, "comentario": r.comentario,
         "compra_verificada": True, "creado_en": r.creado_en.isoformat()} for r in reviews
    ]}
