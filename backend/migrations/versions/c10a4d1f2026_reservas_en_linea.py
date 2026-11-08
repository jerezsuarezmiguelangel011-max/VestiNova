"""CU10: reservas persistentes, estado e historial de transiciones."""
from alembic import op
import sqlalchemy as sa

revision = "c10a4d1f2026"
down_revision = "c09a4d1f2026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservas_cu10",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("codigo", sa.String(36), nullable=False, unique=True),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("lineas", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(15), nullable=False),
        sa.Column("eventos", sa.JSON(), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('CONFIRMADA','CANCELADA','VENCIDA','ATENDIDA')",
            name="ck_reservas_cu10_estado"
        ),
    )
    op.create_index("ix_reservas_cu10_empresa_id", "reservas_cu10", ["empresa_id"])
    op.create_index("ix_reservas_cu10_cliente_id", "reservas_cu10", ["cliente_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Las reservas pueden mantener stock comprometido: respaldar y liberar "
        "los compromisos antes de eliminar registros."
    )
