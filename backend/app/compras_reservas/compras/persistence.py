"""Persistencia propia de CU09; las referencias maestras las valida el gateway autorizado."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, selectinload

from app.db import Base
from app.inventario.domain import Identifier, InventoryError, InventoryKey
from app.compras_reservas.compras.domain import (
    Purchase, PurchaseContext, PurchaseError, PurchaseInvalid, PurchaseLine,
    PurchaseUnavailable, identifier_token,
)


class PurchaseRecord(Base):
    __tablename__ = "compras_digitales"
    __table_args__ = (
        UniqueConstraint("empresa_clave", "id", name="uq_compras_digitales_empresa_id"),
        CheckConstraint("total > 0", name="ck_compras_digitales_total"),
        CheckConstraint("moneda = 'BOB'", name="ck_compras_digitales_moneda"),
        CheckConstraint("length(huella) = 64", name="ck_compras_digitales_huella"),
        Index("ix_compras_digitales_scope", "empresa_clave", "cliente_clave", "sucursal_clave"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    cliente_clave: Mapped[str] = mapped_column(Text, nullable=False)
    sucursal_clave: Mapped[str] = mapped_column(Text, nullable=False)
    contexto: Mapped[dict[str, Identifier]] = mapped_column(JSON, nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(38, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False)
    line_records: Mapped[list["PurchaseLineRecord"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", order_by="PurchaseLineRecord.posicion",
    )


class PurchaseLineRecord(Base):
    __tablename__ = "compras_digitales_lineas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_clave", "compra_id"], ["compras_digitales.empresa_clave", "compras_digitales.id"],
            name="fk_compras_lineas_empresa_compra", ondelete="CASCADE",
        ),
        CheckConstraint("posicion >= 0", name="ck_compras_lineas_posicion"),
        CheckConstraint("producto_id > 0", name="ck_compras_lineas_producto"),
        CheckConstraint("cantidad > 0 AND cantidad <= 2147483647", name="ck_compras_lineas_cantidad"),
        CheckConstraint("precio_unitario > 0 AND precio_unitario <= 99999999.99", name="ck_compras_lineas_precio"),
        CheckConstraint("length(trim(nombre)) > 0", name="ck_compras_lineas_nombre"),
    )

    compra_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    posicion: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    variante_ref: Mapped[Identifier] = mapped_column(JSON, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    purchase: Mapped[PurchaseRecord] = relationship(back_populates="line_records")


def add_purchase(session: Session, purchase: Purchase) -> None:
    """Preparar cabecera y snapshots; el servicio controla el único commit con inventario."""
    if not isinstance(purchase, Purchase):
        raise PurchaseInvalid("La compra no es válida.")
    context = purchase.context
    company = identifier_token(context.empresa_id)
    record = PurchaseRecord(
        id=str(purchase.id), empresa_clave=company,
        cliente_clave=identifier_token(context.cliente_id), sucursal_clave=identifier_token(context.sucursal_id),
        contexto={
            "actor_id": context.actor_id, "empresa_id": context.empresa_id,
            "cliente_id": context.cliente_id, "sucursal_id": context.sucursal_id,
        },
        huella=purchase.fingerprint, creado_en=purchase.creado_en, total=purchase.total, moneda="BOB",
    )
    record.line_records = [
        PurchaseLineRecord(
            compra_id=record.id, empresa_clave=company, posicion=position,
            producto_id=line.producto_id, variante_ref=line.key.variante_id,
            nombre=line.nombre, cantidad=line.cantidad, precio_unitario=line.precio_unitario,
        )
        for position, line in enumerate(purchase.lines)
    ]
    session.add(record)


def find_purchase(session: Session, context: PurchaseContext, id: UUID) -> Purchase | None:
    """Buscar en empresa, cliente y sucursal; conservar el actor original para la política del servicio."""
    if not isinstance(context, PurchaseContext) or not isinstance(id, UUID):
        raise PurchaseInvalid("El contexto o identificador de compra no es válido.")
    record = session.scalar(
        select(PurchaseRecord).where(
            PurchaseRecord.id == str(id),
            PurchaseRecord.empresa_clave == identifier_token(context.empresa_id),
            PurchaseRecord.cliente_clave == identifier_token(context.cliente_id),
            PurchaseRecord.sucursal_clave == identifier_token(context.sucursal_id),
        ).options(selectinload(PurchaseRecord.line_records)).execution_options(populate_existing=True)
    )
    return None if record is None else _hydrate(record)


def list_purchases_for_customer(
    session: Session, empresa_id: int, cliente_id: int, *, limit: int, offset: int,
) -> tuple[list[Purchase], int]:
    company = identifier_token(empresa_id)
    customer = identifier_token(cliente_id)
    filters = (
        PurchaseRecord.empresa_clave == company,
        PurchaseRecord.cliente_clave == customer,
    )
    total = session.scalar(select(func.count()).select_from(PurchaseRecord).where(*filters)) or 0
    records = session.scalars(
        select(PurchaseRecord)
        .where(*filters)
        .options(selectinload(PurchaseRecord.line_records))
        .order_by(PurchaseRecord.creado_en.desc(), PurchaseRecord.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_hydrate(record) for record in records], total


def find_purchase_for_customer(
    session: Session, empresa_id: int, cliente_id: int, purchase_id: UUID, *, lock: bool = False,
) -> Purchase | None:
    if not isinstance(purchase_id, UUID):
        raise PurchaseInvalid("El identificador de compra no es válido.")
    statement = (
        select(PurchaseRecord)
        .where(
            PurchaseRecord.id == str(purchase_id),
            PurchaseRecord.empresa_clave == identifier_token(empresa_id),
            PurchaseRecord.cliente_clave == identifier_token(cliente_id),
        )
        .options(selectinload(PurchaseRecord.line_records))
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement.execution_options(populate_existing=True))
    return None if record is None else _hydrate(record)


def _hydrate(record: PurchaseRecord) -> Purchase:
    try:
        raw = record.contexto
        context = PurchaseContext(
            actor_id=raw["actor_id"], empresa_id=raw["empresa_id"],
            cliente_id=raw["cliente_id"], sucursal_id=raw["sucursal_id"],
        )
        if (record.empresa_clave, record.cliente_clave, record.sucursal_clave) != (
            identifier_token(context.empresa_id), identifier_token(context.cliente_id), identifier_token(context.sucursal_id),
        ):
            raise ValueError("Contexto incoherente.")
        if record.moneda != "BOB" or [line.posicion for line in record.line_records] != list(range(len(record.line_records))):
            raise ValueError("Snapshot incoherente.")
        lines = []
        for line in record.line_records:
            if line.empresa_clave != record.empresa_clave or line.compra_id != record.id:
                raise ValueError("Línea fuera de su compra.")
            lines.append(PurchaseLine(
                key=InventoryKey(context.empresa_id, context.sucursal_id, line.variante_ref),
                producto_id=line.producto_id, nombre=line.nombre, cantidad=line.cantidad,
                precio_unitario=line.precio_unitario,
            ))
        created = record.creado_en
        if created.tzinfo is None:  # SQLite conserva la hora UTC sin su información de zona.
            created = created.replace(tzinfo=timezone.utc)
        purchase = Purchase(UUID(record.id), context, record.huella, tuple(lines), created)
        if record.total != purchase.total:
            raise ValueError("El total no coincide con sus líneas.")
        return purchase
    except (PurchaseError, InventoryError, ValueError, TypeError, KeyError, AttributeError, InvalidOperation):
        raise PurchaseUnavailable("No se pudo verificar la compra guardada.") from None
