"""CU15/CU13: comprobantes de contado e incidencias de sincronización."""
from alembic import op
import sqlalchemy as sa

revision = "c15a4d1f2026"
down_revision = "c10a4d1f2026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ventas_contado_cu15",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("administradores.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id")),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("lineas", sa.JSON(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("efectivo", sa.Numeric(12, 2), nullable=False),
        sa.Column("cambio", sa.Numeric(12, 2), nullable=False),
        sa.Column("codigo", sa.String(40), unique=True, nullable=False),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.Column("creada_local_en", sa.DateTime(timezone=True)),
        sa.Column("entrega_local", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmada_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total > 0 AND efectivo >= total AND cambio = efectivo - total", name="ck_cu15_efectivo"),
    )
    op.create_index("ix_ventas_contado_cu15_empresa_id", "ventas_contado_cu15", ["empresa_id"])
    op.create_table(
        "conflictos_cu13",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("administradores.id"), nullable=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("operacion_id", sa.String(36), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("datos_originales", sa.JSON(), nullable=False),
        sa.Column("motivo", sa.String(350), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(60)),
        sa.Column("observacion", sa.String(500)),
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("administradores.id")),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resuelta_en", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("empresa_id", "tipo", "operacion_id", name="uq_cu13_tipo_operacion_empresa"),
    )
    op.create_index("ix_conflictos_cu13_empresa_id", "conflictos_cu13", ["empresa_id"])


def downgrade():
    raise RuntimeError(
        "Las ventas y conflictos son evidencia comercial. Respaldar y conciliar "
        "los datos antes de eliminar estas tablas."
    )
