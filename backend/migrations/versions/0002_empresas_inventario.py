"""Empresas, pertenencias, sucursales, variantes e inventario trazable.

Conserva productos, cuentas, hashes y sesiones de 0001. La empresa/sucursal
iniciales son un contexto técnico de migración, no datos comerciales inventados.
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_empresas_inventario"
down_revision = "0001_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("empresas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_empresas_slug"),
    )
    op.create_table("sucursales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "empresa_id", name="uq_sucursales_id_empresa"),
        sa.UniqueConstraint("empresa_id", "codigo", name="uq_sucursales_empresa_codigo"),
    )
    op.create_index("ix_sucursales_empresa_id", "sucursales", ["empresa_id"])
    op.add_column("administradores", sa.Column("es_superadministrador", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("membresias_empresa",
        sa.Column("administrador_id", sa.Integer(), sa.ForeignKey("administradores.id"), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), primary_key=True),
        sa.Column("rol", sa.String(20), nullable=False, server_default="ADMINISTRADOR"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("rol IN ('ADMINISTRADOR', 'OPERADOR')", name="ck_membresias_rol"),
    )
    op.create_table("accesos_sucursal",
        sa.Column("administrador_id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), primary_key=True),
        sa.Column("sucursal_id", sa.Integer(), primary_key=True),
        sa.ForeignKeyConstraint(["administrador_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_acceso_membresia"),
        sa.ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_acceso_sucursal_empresa"),
    )

    connection = op.get_bind()
    companies = sa.table("empresas", sa.column("id", sa.Integer()), sa.column("slug", sa.String()), sa.column("nombre", sa.String()))
    initial_company = connection.execute(companies.insert().values(slug="vestinova-inicial", nombre="VestiNova (entorno inicial)").returning(companies.c.id)).scalar_one()
    branches = sa.table("sucursales", sa.column("empresa_id", sa.Integer()), sa.column("codigo", sa.String()), sa.column("nombre", sa.String()))
    connection.execute(branches.insert().values(empresa_id=initial_company, codigo="PRINCIPAL", nombre="Sucursal inicial"))
    users = sa.table("administradores", sa.column("id", sa.Integer()), sa.column("es_superadministrador", sa.Boolean()))
    memberships = sa.table("membresias_empresa", sa.column("administrador_id", sa.Integer()), sa.column("empresa_id", sa.Integer()), sa.column("rol", sa.String()), sa.column("activo", sa.Boolean()))
    connection.execute(memberships.insert().from_select(["administrador_id", "empresa_id", "rol", "activo"], sa.select(users.c.id, sa.literal(initial_company), sa.literal("ADMINISTRADOR"), sa.true())))
    first_user = connection.scalar(sa.select(sa.func.min(users.c.id)))
    if first_user is not None:
        connection.execute(users.update().where(users.c.id == first_user).values(es_superadministrador=True))

    op.add_column("productos", sa.Column("empresa_id", sa.Integer(), nullable=True))
    products = sa.table("productos", sa.column("empresa_id", sa.Integer()))
    connection.execute(products.update().values(empresa_id=initial_company))
    op.alter_column("productos", "empresa_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("fk_productos_empresa", "productos", "empresas", ["empresa_id"], ["id"])
    op.create_unique_constraint("uq_productos_id_empresa", "productos", ["id", "empresa_id"])
    op.create_index("ix_productos_empresa_id", "productos", ["empresa_id"])

    op.create_table("variantes_producto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("talla", sa.String(30), nullable=False),
        sa.Column("color", sa.String(60), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "empresa_id", name="uq_variantes_id_empresa"),
        sa.UniqueConstraint("empresa_id", "producto_id", "talla", "color", name="uq_variantes_producto_talla_color"),
        sa.ForeignKeyConstraint(["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"], name="fk_variantes_producto_empresa"),
    )
    op.create_index("ix_variantes_producto_empresa_id", "variantes_producto", ["empresa_id"])
    op.create_table("existencias",
        sa.Column("empresa_id", sa.Integer(), primary_key=True),
        sa.Column("sucursal_id", sa.Integer(), primary_key=True),
        sa.Column("variante_id", sa.Integer(), primary_key=True),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_existencias_sucursal_empresa"),
        sa.ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_existencias_variante_empresa"),
        sa.CheckConstraint("cantidad >= 0", name="ck_existencias_no_negativas"),
    )
    op.create_table("movimientos_inventario",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("variante_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("administradores.id"), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("motivo", sa.String(300), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("saldo_resultante", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_movimientos_usuario_empresa"),
        sa.ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_movimientos_sucursal_empresa"),
        sa.ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_movimientos_variante_empresa"),
        sa.CheckConstraint("(tipo = 'ENTRADA' AND delta > 0) OR (tipo = 'SALIDA' AND delta < 0)", name="ck_movimientos_tipo_delta"),
        sa.CheckConstraint("saldo_resultante >= 0", name="ck_movimientos_saldo"),
    )
    op.create_index("ix_movimientos_empresa_sucursal_variante", "movimientos_inventario", ["empresa_id", "sucursal_id", "variante_id"])


def downgrade() -> None:
    raise RuntimeError("Esta migración conserva trazabilidad y pertenencias. No hay downgrade destructivo automático; restaura un respaldo explícito si necesitas volver atrás.")
