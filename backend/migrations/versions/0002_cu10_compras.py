"""Snapshots de compras CU10 sin crear ni sustituir maestros de otros módulos."""
from alembic import op
import sqlalchemy as sa


revision = "cu10_01_compras"
down_revision = "0001_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compras_digitales",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("cliente_clave", sa.Text(), nullable=False),
        sa.Column("sucursal_clave", sa.Text(), nullable=False),
        sa.Column("contexto", sa.JSON(), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Numeric(38, 2), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=False),
        sa.UniqueConstraint("empresa_clave", "id", name="uq_compras_digitales_empresa_id"),
        sa.CheckConstraint("total > 0", name="ck_compras_digitales_total"),
        sa.CheckConstraint("moneda = 'BOB'", name="ck_compras_digitales_moneda"),
        sa.CheckConstraint("length(huella) = 64", name="ck_compras_digitales_huella"),
    )
    op.create_index("ix_compras_digitales_scope", "compras_digitales", ["empresa_clave", "cliente_clave", "sucursal_clave"])
    op.create_table(
        "compras_digitales_lineas",
        sa.Column("compra_id", sa.String(36), primary_key=True),
        sa.Column("posicion", sa.Integer(), primary_key=True),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("variante_ref", sa.JSON(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["empresa_clave", "compra_id"], ["compras_digitales.empresa_clave", "compras_digitales.id"],
            name="fk_compras_lineas_empresa_compra", ondelete="CASCADE",
        ),
        sa.CheckConstraint("posicion >= 0", name="ck_compras_lineas_posicion"),
        sa.CheckConstraint("producto_id > 0", name="ck_compras_lineas_producto"),
        sa.CheckConstraint("cantidad > 0 AND cantidad <= 2147483647", name="ck_compras_lineas_cantidad"),
        sa.CheckConstraint("precio_unitario > 0 AND precio_unitario <= 99999999.99", name="ck_compras_lineas_precio"),
        sa.CheckConstraint("length(trim(nombre)) > 0", name="ck_compras_lineas_nombre"),
    )


def downgrade() -> None:
    # Solo una reversión explícita elimina los snapshots de compras de esta revisión.
    op.drop_table("compras_digitales_lineas")
    op.drop_index("ix_compras_digitales_scope", table_name="compras_digitales")
    op.drop_table("compras_digitales")
