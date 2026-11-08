"""CU19: preferencias de personalización y visitas consentidas por tienda.

Revision: c19c20c23demo
Revises: c192023a2026
"""
from alembic import op
import sqlalchemy as sa

revision = "c19c20c23demo"
down_revision = "c192023a2026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consentimientos_cu19",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "visitas_prendas_cu19",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("producto_id", sa.Integer(), primary_key=True),
        sa.Column("vistas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("vista_reciente_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"],
            name="fk_cu19_visita_producto_empresa",
        ),
        sa.CheckConstraint("vistas >= 1 AND vistas <= 50", name="ck_cu19_vistas"),
    )
    op.create_index("ix_visitas_cu19_empresa_cliente",
                    "visitas_prendas_cu19", ["empresa_id", "cliente_id"])


def downgrade():
    op.drop_index("ix_visitas_cu19_empresa_cliente", table_name="visitas_prendas_cu19")
    op.drop_table("visitas_prendas_cu19")
    op.drop_table("consentimientos_cu19")
