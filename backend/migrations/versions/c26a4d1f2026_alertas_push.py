"""CU26 alertas push y eventos de reposición."""
from alembic import op
import sqlalchemy as sa
revision = "c26a4d1f2026"
down_revision = "c25a4d1f2026"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("canales_push_cliente",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("endpoint_sha", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("clave_publica", sa.String(256), nullable=False),
        sa.Column("clave_auth", sa.String(256), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("empresa_id", "cliente_id", "endpoint_sha", name="uq_cu26_canal_cliente_endpoint"))
    op.create_table("alertas_reposicion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("variante_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_cu26_alerta_variante_tenant"),
        sa.ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_cu26_alerta_sucursal_tenant"),
        sa.UniqueConstraint("empresa_id", "cliente_id", "variante_id", "sucursal_id", name="uq_cu26_alerta_cliente_variante_sucursal"),
        sa.CheckConstraint("estado IN ('ACTIVA', 'CANCELADA')", name="ck_cu26_alerta_estado"))
    op.create_table("avisos_push_reposicion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("alerta_id", sa.Integer(), sa.ForeignKey("alertas_reposicion.id"), nullable=False),
        sa.Column("canal_id", sa.Integer(), sa.ForeignKey("canales_push_cliente.id"), nullable=False),
        sa.Column("movimiento_id", sa.String(36), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("alerta_id", "movimiento_id", "canal_id", name="uq_cu26_aviso_evento_canal"),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'ENVIADO', 'REVOCADO', 'ERROR', 'CANCELADO')", name="ck_cu26_aviso_estado"))
    op.create_index("ix_cu26_aviso_pendiente", "avisos_push_reposicion", ["estado", "id"])

def downgrade():
    op.drop_index("ix_cu26_aviso_pendiente", table_name="avisos_push_reposicion")
    op.drop_table("avisos_push_reposicion")
    op.drop_table("alertas_reposicion")
    op.drop_table("canales_push_cliente")
