"""CU09 móvil: asociación de cliente Stripe y tarjeta autorizada para cargo futuro TEST."""
from alembic import op
import sqlalchemy as sa

revision = "b209a4d1f2026"
down_revision = "801efc9ff398"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cu09_metodos_diferidos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=False),
        sa.Column("setup_session_id", sa.String(255), nullable=True),
        sa.Column("payment_method_id", sa.String(255), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("empresa_id", "cliente_id", name="uq_cu09_metodo_empresa_cliente"),
    )


def downgrade():
    raise RuntimeError("Requiere revocar métodos guardados de Stripe y respaldar los datos antes de eliminar.")
