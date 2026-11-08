"""CU25 - compras entregadas y valoraciones verificadas."""
from alembic import op
import sqlalchemy as sa

revision = "c25a4d1f2026"
down_revision = "f27c9a4d1b02"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "compras_digitales_entregas",
        sa.Column("compra_id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("entregada_por_id", sa.Integer(), sa.ForeignKey("administradores.id"), nullable=False),
        sa.Column("comprobacion", sa.String(200), nullable=False),
        sa.Column("entregada_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empresa_clave", "compra_id"],
                                ["compras_digitales.empresa_clave", "compras_digitales.id"],
                                name="fk_cu25_entrega_compra_tenant"),
    )
    op.create_table(
        "valoraciones_compra",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("compra_id", sa.String(36), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("puntuacion", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empresa_clave", "compra_id"],
                                ["compras_digitales.empresa_clave", "compras_digitales.id"],
                                name="fk_cu25_valoracion_compra_tenant"),
        sa.ForeignKeyConstraint(["producto_id", "empresa_id"],
                                ["productos.id", "productos.empresa_id"],
                                name="fk_cu25_valoracion_producto_tenant"),
        sa.UniqueConstraint("empresa_id", "compra_id", "producto_id",
                            name="uq_cu25_valoracion_por_compra_producto"),
        sa.CheckConstraint("puntuacion BETWEEN 1 AND 5", name="ck_cu25_puntuacion"),
    )
    op.create_index("ix_cu25_valoracion_producto", "valoraciones_compra", ["empresa_id", "producto_id"])

def downgrade() -> None:
    op.drop_index("ix_cu25_valoracion_producto", table_name="valoraciones_compra")
    op.drop_table("valoraciones_compra")
    op.drop_table("compras_digitales_entregas")
