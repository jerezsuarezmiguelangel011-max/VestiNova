from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class CategoriaProducto(Base):
    __tablename__ = "categorias_producto"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_categorias_producto_id_empresa"),
        UniqueConstraint("empresa_id", "nombre_clave", name="uq_categorias_producto_empresa_nombre"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    nombre_clave: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_productos_slug"),
        UniqueConstraint("id", "empresa_id", name="uq_productos_id_empresa"),
        ForeignKeyConstraint(["categoria_id", "empresa_id"], ["categorias_producto.id", "categorias_producto.empresa_id"], name="fk_productos_categoria_empresa"),
        CheckConstraint("precio > 0 AND precio <= 99999999.99", name="ck_productos_precio"),
        CheckConstraint("moneda = 'BOB'", name="ck_productos_moneda"),
        Index("ix_productos_activo_id", "activo", "id"),
        Index("ix_productos_empresa_categoria", "empresa_id", "categoria_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    categoria_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="BOB")
    imagen_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    categoria: Mapped[CategoriaProducto | None] = relationship()

    @property
    def categoria_nombre(self) -> str:
        return self.categoria.nombre if self.categoria is not None else "General"


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (UniqueConstraint("slug", name="uq_empresas_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    correo_contacto: Mapped[str | None] = mapped_column(String(254), nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column(String(40), nullable=True)
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
    ciudad: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    ubicacion: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    contacto: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MembresiaEmpresa(Base):
    __tablename__ = "membresias_empresa"
    __table_args__ = (
        CheckConstraint("rol IN ('ADMINISTRADOR', 'OPERADOR', 'ENCARGADO_SUCURSAL', 'CAJERO')", name="ck_membresias_rol"),
        ForeignKeyConstraint(["rol_empresa_id", "empresa_id"], ["roles_empresa.id", "roles_empresa.empresa_id"], name="fk_membresia_rol_empresa"),
    )

    administrador_id: Mapped[int] = mapped_column(ForeignKey("administradores.id"), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="ADMINISTRADOR")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rol_empresa_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RolEmpresa(Base):
    __tablename__ = "roles_empresa"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_roles_id_empresa"),
        UniqueConstraint("empresa_id", "codigo_sistema", name="uq_roles_empresa_sistema"),
        UniqueConstraint("empresa_id", "nombre_clave", name="uq_roles_empresa_nombre"),
        CheckConstraint("codigo_sistema IS NULL OR codigo_sistema IN ('ADMINISTRADOR', 'OPERADOR', 'ENCARGADO_SUCURSAL', 'CAJERO')", name="ck_roles_sistema"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    nombre_clave: Mapped[str] = mapped_column(String(360), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    codigo_sistema: Mapped[str | None] = mapped_column(String(20), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PermisoRol(Base):
    __tablename__ = "permisos_rol"
    rol_empresa_id: Mapped[int] = mapped_column(ForeignKey("roles_empresa.id", ondelete="CASCADE"), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), primary_key=True)


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


class EventoAuditoria(Base):
    """Evento empresarial de solo anexado; nunca contiene credenciales ni secretos."""
    __tablename__ = "eventos_auditoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id", "empresa_id"],
            ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"],
            name="fk_auditoria_actor_empresa",
        ),
        Index("ix_auditoria_empresa_fecha_id", "empresa_id", "creado_en", "id"),
        Index("ix_auditoria_empresa_actor_fecha", "empresa_id", "actor_id", "creado_en"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_correo: Mapped[str] = mapped_column(String(254), nullable=False)
    accion: Mapped[str] = mapped_column(String(80), nullable=False)
    entidad: Mapped[str] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(80), nullable=False)
    detalles: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Promocion(Base):
    __tablename__ = "promociones"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_promociones_id_empresa"),
        CheckConstraint("tipo IN ('PORCENTAJE', 'PRECIO_FIJO')", name="ck_promociones_tipo"),
        CheckConstraint("valor > 0", name="ck_promociones_valor_positivo"),
        CheckConstraint("tipo != 'PORCENTAJE' OR valor < 100", name="ck_promociones_porcentaje_menor_100"),
        CheckConstraint("fin > inicio", name="ck_promociones_vigencia"),
        Index("ix_promociones_empresa_vigencia", "empresa_id", "activo", "inicio", "fin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PromocionProducto(Base):
    __tablename__ = "promociones_productos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["promocion_id", "empresa_id"], ["promociones.id", "promociones.empresa_id"],
            name="fk_promocion_producto_promocion_empresa", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"],
            name="fk_promocion_producto_producto_empresa",
        ),
        Index("ix_promociones_productos_empresa_producto", "empresa_id", "producto_id"),
    )

    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promocion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class Proveedor(Base):
    __tablename__ = "proveedores"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_proveedores_id_empresa"),
        UniqueConstraint("empresa_id", "codigo", name="uq_proveedores_empresa_codigo"),
        Index("ix_proveedores_empresa_activo", "empresa_id", "activo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    contacto: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    correo: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    telefono: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OrdenAbastecimiento(Base):
    __tablename__ = "ordenes_abastecimiento"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_ordenes_abastecimiento_id_empresa"),
        ForeignKeyConstraint(
            ["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"],
            name="fk_orden_abastecimiento_sucursal_empresa",
        ),
        ForeignKeyConstraint(
            ["proveedor_id", "empresa_id"], ["proveedores.id", "proveedores.empresa_id"],
            name="fk_orden_abastecimiento_proveedor_empresa",
        ),
        ForeignKeyConstraint(
            ["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"],
            name="fk_orden_abastecimiento_usuario_empresa",
        ),
        CheckConstraint("estado IN ('PENDIENTE', 'PARCIAL', 'RECIBIDA', 'CANCELADA')", name="ck_orden_abastecimiento_estado"),
        Index("ix_ordenes_abastecimiento_empresa_fecha", "empresa_id", "creado_en"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proveedor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDIENTE")
    observaciones: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class LineaAbastecimiento(Base):
    __tablename__ = "lineas_abastecimiento"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", "orden_id", name="uq_lineas_abastecimiento_id_scope"),
        ForeignKeyConstraint(
            ["orden_id", "empresa_id"], ["ordenes_abastecimiento.id", "ordenes_abastecimiento.empresa_id"],
            name="fk_linea_abastecimiento_orden_empresa", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"],
            name="fk_linea_abastecimiento_variante_empresa",
        ),
        CheckConstraint("cantidad_solicitada > 0", name="ck_linea_abastecimiento_cantidad_solicitada"),
        CheckConstraint("cantidad_recibida >= 0 AND cantidad_recibida <= cantidad_solicitada", name="ck_linea_abastecimiento_cantidad_recibida"),
        CheckConstraint("costo_unitario > 0 AND costo_unitario <= 99999999.99", name="ck_linea_abastecimiento_costo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    orden_id: Mapped[int] = mapped_column(Integer, nullable=False)
    variante_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_solicitada: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_recibida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class RecepcionAbastecimiento(Base):
    __tablename__ = "recepciones_abastecimiento"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", "orden_id", name="uq_recepciones_abastecimiento_id_scope"),
        ForeignKeyConstraint(
            ["orden_id", "empresa_id"], ["ordenes_abastecimiento.id", "ordenes_abastecimiento.empresa_id"],
            name="fk_recepcion_abastecimiento_orden_empresa",
        ),
        ForeignKeyConstraint(
            ["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"],
            name="fk_recepcion_abastecimiento_usuario_empresa",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    orden_id: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class LineaRecepcionAbastecimiento(Base):
    __tablename__ = "lineas_recepcion_abastecimiento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["recepcion_id", "empresa_id", "orden_id"],
            ["recepciones_abastecimiento.id", "recepciones_abastecimiento.empresa_id", "recepciones_abastecimiento.orden_id"],
            name="fk_linea_recepcion_recepcion_scope", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["linea_id", "empresa_id", "orden_id"],
            ["lineas_abastecimiento.id", "lineas_abastecimiento.empresa_id", "lineas_abastecimiento.orden_id"],
            name="fk_linea_recepcion_linea_scope",
        ),
        CheckConstraint("cantidad > 0", name="ck_linea_recepcion_cantidad"),
    )

    recepcion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    linea_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
    orden_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)


class PlanSaaS(Base):
    __tablename__ = "planes_saas"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_planes_saas_codigo"),
        CheckConstraint("precio_mensual IS NULL OR precio_mensual >= 0", name="ck_planes_saas_precio"),
        CheckConstraint("max_sucursales > 0", name="ck_planes_saas_sucursales"),
        CheckConstraint("max_productos IS NULL OR max_productos > 0", name="ck_planes_saas_productos"),
        CheckConstraint("max_usuarios IS NULL OR max_usuarios > 0", name="ck_planes_saas_usuarios"),
        Index("ix_planes_saas_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    precio_mensual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_sucursales: Mapped[int] = mapped_column(Integer, nullable=False)
    max_productos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_usuarios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prestaciones: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SuscripcionEmpresa(Base):
    __tablename__ = "suscripciones_empresa"
    __table_args__ = (
        ForeignKeyConstraint(["plan_id"], ["planes_saas.id"], name="fk_suscripciones_empresa_plan"),
        CheckConstraint("estado IN ('ACTIVA', 'SUSPENDIDA', 'VENCIDA', 'CANCELADA')", name="ck_suscripciones_empresa_estado"),
        CheckConstraint("renueva_en IS NULL OR renueva_en >= inicia_en", name="ck_suscripciones_empresa_fechas"),
    )

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="ACTIVA")
    inicia_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    renueva_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
