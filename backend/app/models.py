from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Administrador(Base):
    __tablename__ = "administradores"
    __table_args__ = (UniqueConstraint("correo", name="uq_administradores_correo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    correo: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    es_superadministrador: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SesionAdministrador(Base):
    __tablename__ = "sesiones_administrador"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    administrador_id: Mapped[int] = mapped_column(ForeignKey("administradores.id", ondelete="CASCADE"), nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_productos_slug"),
        UniqueConstraint("id", "empresa_id", name="uq_productos_id_empresa"),
        CheckConstraint("precio > 0 AND precio <= 99999999.99", name="ck_productos_precio"),
        CheckConstraint("moneda = 'BOB'", name="ck_productos_moneda"),
        Index("ix_productos_activo_id", "activo", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="BOB")
    imagen_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (UniqueConstraint("slug", name="uq_empresas_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Sucursal(Base):
    __tablename__ = "sucursales"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_sucursales_id_empresa"),
        UniqueConstraint("empresa_id", "codigo", name="uq_sucursales_empresa_codigo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MembresiaEmpresa(Base):
    __tablename__ = "membresias_empresa"
    __table_args__ = (CheckConstraint("rol IN ('ADMINISTRADOR', 'OPERADOR', 'ENCARGADO_SUCURSAL', 'CAJERO')", name="ck_membresias_rol"),)

    administrador_id: Mapped[int] = mapped_column(ForeignKey("administradores.id"), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="ADMINISTRADOR")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AccesoSucursal(Base):
    __tablename__ = "accesos_sucursal"
    __table_args__ = (
        ForeignKeyConstraint(["administrador_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_acceso_membresia"),
        ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_acceso_sucursal_empresa"),
    )

    administrador_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class VarianteProducto(Base):
    __tablename__ = "variantes_producto"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_variantes_id_empresa"),
        UniqueConstraint("empresa_id", "producto_id", "talla", "color", name="uq_variantes_producto_talla_color"),
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"], name="fk_variantes_producto_empresa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    talla: Mapped[str] = mapped_column(String(30), nullable=False)
    color: Mapped[str] = mapped_column(String(60), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Existencia(Base):
    __tablename__ = "existencias"
    __table_args__ = (
        ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_existencias_sucursal_empresa"),
        ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_existencias_variante_empresa"),
        CheckConstraint("cantidad >= 0", name="ck_existencias_no_negativas"),
    )

    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variante_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        ForeignKeyConstraint(["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_movimientos_usuario_empresa"),
        ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_movimientos_sucursal_empresa"),
        ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_movimientos_variante_empresa"),
        CheckConstraint("(tipo = 'ENTRADA' AND delta > 0) OR (tipo = 'SALIDA' AND delta < 0)", name="ck_movimientos_tipo_delta"),
        CheckConstraint("saldo_resultante >= 0", name="ck_movimientos_saldo"),
        Index("ix_movimientos_empresa_sucursal_variante", "empresa_id", "sucursal_id", "variante_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    variante_id: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("administradores.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_resultante: Mapped[int] = mapped_column(Integer, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Cliente(Base):
    """Una identidad de cliente independiente por tienda, nunca una cuenta de personal."""
    __tablename__ = "clientes"
    __table_args__ = (UniqueConstraint("empresa_id", "correo", name="uq_clientes_empresa_correo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    correo: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SesionCliente(Base):
    __tablename__ = "sesiones_cliente"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
