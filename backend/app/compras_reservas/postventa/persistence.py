"""Registros y snapshots de solicitudes de cambios y devoluciones."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.compras_reservas.compras.domain import Identifier
from app.db import Base
from app.models import utc_now


class SolicitudPostventa(Base):
    __tablename__ = "solicitudes_postventa"
    __table_args__ = (
        UniqueConstraint("empresa_clave", "id", name="uq_solicitudes_postventa_empresa_id"),
        ForeignKeyConstraint(
            ["empresa_clave", "compra_id"],
            ["compras_digitales.empresa_clave", "compras_digitales.id"],
            name="fk_postventa_compra_empresa",
        ),
        CheckConstraint("tipo IN ('CAMBIO', 'DEVOLUCION')", name="ck_postventa_tipo"),
        CheckConstraint("estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA', 'COMPLETADA')", name="ck_postventa_estado"),
        Index("ix_postventa_empresa_sucursal_estado_fecha", "empresa_id", "sucursal_id", "estado", "creado_en"),
        Index("ix_postventa_empresa_cliente_compra", "empresa_id", "cliente_id", "compra_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    compra_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDIENTE")
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    referencia_reposicion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resuelto_por_id: Mapped[int | None] = mapped_column(ForeignKey("administradores.id"), nullable=True)
    line_records: Mapped[list["LineaSolicitudPostventa"]] = relationship(
        back_populates="solicitud", cascade="all, delete-orphan", order_by="LineaSolicitudPostventa.compra_posicion",
    )


class LineaSolicitudPostventa(Base):
    __tablename__ = "solicitudes_postventa_lineas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_clave", "solicitud_id"],
            ["solicitudes_postventa.empresa_clave", "solicitudes_postventa.id"],
            name="fk_postventa_linea_solicitud_empresa",
            ondelete="CASCADE",
        ),
        CheckConstraint("compra_posicion >= 0", name="ck_postventa_linea_compra_posicion"),
        CheckConstraint("producto_id > 0", name="ck_postventa_linea_producto"),
        CheckConstraint("cantidad > 0", name="ck_postventa_linea_cantidad"),
        CheckConstraint("precio_unitario > 0 AND precio_unitario <= 99999999.99", name="ck_postventa_linea_precio"),
    )

    solicitud_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_clave: Mapped[str] = mapped_column(Text, nullable=False)
    compra_posicion: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    variante_ref: Mapped[Identifier] = mapped_column(JSON, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    solicitud: Mapped[SolicitudPostventa] = relationship(back_populates="line_records")
