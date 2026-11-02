"""CU05: promociones y descuentos comerciales asociados a prendas."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.db import get_db
from app.models import Producto, Promocion, PromocionProducto, utc_now
from app.tenancy import TenantContext, require_permission


router = APIRouter(prefix="/api/admin/promociones", tags=["CU05 Â· Promociones comerciales"])


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PromotionCreate(Input):
    nombre: str = Field(min_length=3, max_length=120)
    tipo: Literal["PORCENTAJE", "PRECIO_FIJO"]
    valor: Decimal = Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    inicio: datetime
    fin: datetime
    producto_ids: list[int] = Field(min_length=1, max_length=1000)
    activo: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def validate_campaign(self):
        if self.inicio.utcoffset() is None or self.fin.utcoffset() is None:
            raise ValueError("Las fechas de vigencia deben incluir zona horaria.")
        if self.fin <= self.inicio:
            raise ValueError("La fecha final debe ser posterior a la inicial.")
        if self.tipo == "PORCENTAJE" and self.valor >= 100:
            raise ValueError("El descuento porcentual debe ser menor al 100 %.")
        if any(type(item) is not int or item <= 0 for item in self.producto_ids) or len(set(self.producto_ids)) != len(self.producto_ids):
            raise ValueError("Selecciona productos vÃ¡lidos sin repetir.")
        return self


class PromotionPatch(Input):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    tipo: Literal["PORCENTAJE", "PRECIO_FIJO"] | None = None
    valor: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    inicio: datetime | None = None
    fin: datetime | None = None
    producto_ids: list[int] | None = Field(default=None, min_length=1, max_length=1000)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def changes_required(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("EnvÃ­a al menos un cambio no nulo.")
        if self.inicio is not None and self.inicio.utcoffset() is None:
            raise ValueError("La fecha inicial debe incluir zona horaria.")
        if self.fin is not None and self.fin.utcoffset() is None:
            raise ValueError("La fecha final debe incluir zona horaria.")
        if self.producto_ids is not None and (
            any(type(item) is not int or item <= 0 for item in self.producto_ids)
            or len(set(self.producto_ids)) != len(self.producto_ids)
        ):
            raise ValueError("Selecciona productos vÃ¡lidos sin repetir.")
        return self


class PromotionResponse(BaseModel):
    id: int
    empresa_id: int
    nombre: str
    tipo: str
    valor: str
    inicio: datetime
    fin: datetime
    activo: bool
    estado: str
    producto_ids: list[int]
    creado_en: datetime
    actualizado_en: datetime


def promotion_state(promotion: Promocion, *, now: datetime | None = None) -> str:
    if not promotion.activo:
        return "INACTIVA"
    current = _utc(now or datetime.now(timezone.utc))
    if _utc(promotion.inicio) > current:
        return "PROGRAMADA"
    if _utc(promotion.fin) <= current:
        return "FINALIZADA"
    return "ACTIVA"


def promotion_response(db: Session, promotion: Promocion) -> PromotionResponse:
    product_ids = db.scalars(select(PromocionProducto.producto_id).where(
        PromocionProducto.empresa_id == promotion.empresa_id,
        PromocionProducto.promocion_id == promotion.id,
    ).order_by(PromocionProducto.producto_id)).all()
    return PromotionResponse(
        id=promotion.id, empresa_id=promotion.empresa_id, nombre=promotion.nombre,
        tipo=promotion.tipo, valor=f"{promotion.valor:.2f}", inicio=promotion.inicio, fin=promotion.fin,
        activo=promotion.activo, estado=promotion_state(promotion), producto_ids=list(product_ids),
        creado_en=promotion.creado_en, actualizado_en=promotion.actualizado_en,
    )


def _validate_products(db: Session, context: TenantContext, product_ids: list[int]) -> list[Producto]:
    products = db.scalars(select(Producto).where(
        Producto.empresa_id == context.empresa_id,
        Producto.id.in_(product_ids),
        Producto.activo.is_(True),
    )).all()
    if {product.id for product in products} != set(product_ids):
        raise HTTPException(422, "La promociÃ³n solo puede incluir productos activos del catÃ¡logo de esta empresa.")
    return products


def _load_products(db: Session, context: TenantContext, product_ids: list[int]) -> list[Producto]:
    products = db.scalars(select(Producto).where(
        Producto.empresa_id == context.empresa_id,
        Producto.id.in_(product_ids),
    )).all()
    if {product.id for product in products} != set(product_ids):
        raise HTTPException(422, "La promociÃƒÂ³n solo puede incluir productos del catÃƒÂ¡logo de esta empresa.")
    return products


def _validate_price(tipo: str, valor: Decimal, products: list[Producto]) -> None:
    if tipo == "PORCENTAJE" and valor >= Decimal("100"):
        raise HTTPException(422, "El descuento porcentual debe ser menor al 100 %.")
    if tipo == "PRECIO_FIJO" and any(valor >= product.precio for product in products):
        raise HTTPException(422, "El precio promocional debe ser menor al precio regular de cada producto.")


def _validate_overlap(
    db: Session,
    empresa_id: int,
    product_ids: list[int],
    inicio: datetime,
    fin: datetime,
    *,
    exclude_id: int | None = None,
) -> None:
    if not product_ids:
        return
    statement = select(Promocion.id).join(
        PromocionProducto,
        (PromocionProducto.promocion_id == Promocion.id) & (PromocionProducto.empresa_id == Promocion.empresa_id),
    ).where(
        Promocion.empresa_id == empresa_id,
        Promocion.activo.is_(True),
        PromocionProducto.producto_id.in_(product_ids),
        Promocion.inicio < fin,
        Promocion.fin > inicio,
    )
    if exclude_id is not None:
        statement = statement.where(Promocion.id != exclude_id)
    if db.scalar(statement.limit(1)) is not None:
        raise HTTPException(409, "Uno o mÃ¡s productos ya tienen otra promociÃ³n activa en ese periodo.")


@router.get("", response_model=list[PromotionResponse])
def list_promotions(
    q: str | None = Query(default=None, max_length=120),
    estado: Literal["todas", "activas", "programadas", "finalizadas", "inactivas"] = "todas",
    context: TenantContext = Depends(require_permission("promociones.consultar")),
    db: Session = Depends(get_db),
):
    statement = select(Promocion).where(Promocion.empresa_id == context.empresa_id)
    if q and q.strip():
        statement = statement.where(Promocion.nombre.ilike(f"%{q.strip()}%"))
    rows = db.scalars(statement.order_by(Promocion.inicio.desc(), Promocion.id.desc())).all()
    expected = {"activas": "ACTIVA", "programadas": "PROGRAMADA", "finalizadas": "FINALIZADA", "inactivas": "INACTIVA"}.get(estado)
    return [promotion_response(db, row) for row in rows if expected is None or promotion_state(row) == expected]


@router.post("", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
def create_promotion(
    payload: PromotionCreate,
    context: TenantContext = Depends(require_permission("promociones.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    products = _validate_products(db, context, payload.producto_ids)
    _validate_price(payload.tipo, payload.valor, products)
    if payload.activo:
        _validate_overlap(db, context.empresa_id, payload.producto_ids, payload.inicio, payload.fin)
    promotion = Promocion(
        empresa_id=context.empresa_id, nombre=payload.nombre, tipo=payload.tipo,
        valor=payload.valor, inicio=payload.inicio.astimezone(timezone.utc),
        fin=payload.fin.astimezone(timezone.utc), activo=payload.activo,
    )
    db.add(promotion)
    try:
        db.flush()
        db.add_all(PromocionProducto(empresa_id=context.empresa_id, promocion_id=promotion.id, producto_id=product_id)
                   for product_id in payload.producto_ids)
        record_audit_event(db, context, accion="promocion.creada", entidad="promocion", entidad_id=promotion.id,
                           detalles={"nombre": promotion.nombre, "productos": len(payload.producto_ids), "tipo": promotion.tipo})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo guardar la promociÃ³n por un conflicto con el catÃ¡logo.") from None
    return promotion_response(db, promotion)


@router.patch("/{promocion_id}", response_model=PromotionResponse)
def update_promotion(
    promocion_id: int,
    payload: PromotionPatch,
    context: TenantContext = Depends(require_permission("promociones.gestionar", mutation=True)),
    db: Session = Depends(get_db),
):
    promotion = db.scalar(select(Promocion).where(
        Promocion.id == promocion_id, Promocion.empresa_id == context.empresa_id
    ).with_for_update())
    if promotion is None:
        raise HTTPException(404, "PromociÃ³n no encontrada.")
    changes = payload.model_dump(exclude_unset=True)
    product_ids = changes.pop("producto_ids", None)
    selected_ids = product_ids if product_ids is not None else db.scalars(select(PromocionProducto.producto_id).where(
            PromocionProducto.empresa_id == context.empresa_id,
            PromocionProducto.promocion_id == promotion.id,
        )).all()
    tipo = changes.get("tipo", promotion.tipo)
    valor = changes.get("valor", promotion.valor)
    inicio = changes.get("inicio", promotion.inicio)
    fin = changes.get("fin", promotion.fin)
    activo = changes.get("activo", promotion.activo)
    products = _validate_products(db, context, selected_ids) if activo else _load_products(db, context, selected_ids)
    if fin <= inicio:
        raise HTTPException(422, "La fecha final debe ser posterior a la inicial.")
    _validate_price(tipo, valor, products)
    if activo:
        _validate_overlap(db, context.empresa_id, [product.id for product in products], inicio, fin, exclude_id=promotion.id)
    for field, value in changes.items():
        if field in {"inicio", "fin"}:
            value = value.astimezone(timezone.utc)
        setattr(promotion, field, value)
    if product_ids is not None:
        db.query(PromocionProducto).filter_by(empresa_id=context.empresa_id, promocion_id=promotion.id).delete(synchronize_session=False)
        db.add_all(PromocionProducto(empresa_id=context.empresa_id, promocion_id=promotion.id, producto_id=product_id)
                   for product_id in product_ids)
    promotion.actualizado_en = utc_now()
    record_audit_event(db, context, accion="promocion.actualizada", entidad="promocion", entidad_id=promotion.id,
                       detalles={"campos": sorted(payload.model_fields_set), "nombre": promotion.nombre})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar la promociÃ³n.") from None
    return promotion_response(db, promotion)


def active_promotions_for_products(db: Session, products: list[Producto]) -> dict[int, Promocion]:
    if not products:
        return {}
    now = utc_now()
    rows = db.execute(
        select(Promocion, PromocionProducto.producto_id)
        .join(PromocionProducto,
              (PromocionProducto.promocion_id == Promocion.id) & (PromocionProducto.empresa_id == Promocion.empresa_id))
        .where(
            Promocion.empresa_id.in_({product.empresa_id for product in products}),
            Promocion.activo.is_(True),
            Promocion.inicio <= now,
            Promocion.fin > now,
            PromocionProducto.producto_id.in_({product.id for product in products}),
        )
    ).all()
    return {product_id: promotion for promotion, product_id in rows}


def promotional_price(precio: Decimal, promotion: Promocion) -> Decimal:
    if promotion.tipo == "PRECIO_FIJO":
        return promotion.valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    factor = Decimal("1") - (promotion.valor / Decimal("100"))
    return (precio * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
