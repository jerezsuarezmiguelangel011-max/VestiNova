"""CU09: intentos Stripe persistentes y movimientos de venta por cliente."""
from alembic import op
import sqlalchemy as sa

revision = "c09a4d1f2026"
down_revision = "c08a4d1f2026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_stripe_intentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("datos", sa.JSON(), nullable=False),
        sa.Column("monto_centavos", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("stripe_session_id", sa.String(255), nullable=True),
        sa.Column("stripe_payment_id", sa.String(255), nullable=True),
        sa.Column("aviso", sa.String(350), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stripe_session_id", name="uq_checkout_stripe_session"),
        sa.CheckConstraint("monto_centavos > 0", name="ck_checkout_stripe_monto"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'PAGO_PENDIENTE', 'CONFIRMADA', 'INCIDENCIA', 'RECHAZADA', 'EXPIRADA')",
            name="ck_checkout_stripe_estado"),
    )
    op.create_index("ix_checkout_stripe_intentos_empresa_id", "checkout_stripe_intentos", ["empresa_id"])
    op.create_index("ix_checkout_stripe_intentos_cliente_id", "checkout_stripe_intentos", ["cliente_id"])

    with op.batch_alter_table("movimientos_inventario") as batch:
        batch.alter_column("usuario_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("cliente_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_movimientos_cliente", "clientes", ["cliente_id"], ["id"])
        batch.create_check_constraint(
            "ck_movimientos_actor_identificado",
            "(usuario_id IS NOT NULL AND cliente_id IS NULL) OR (usuario_id IS NULL AND cliente_id IS NOT NULL)",
        )


def downgrade() -> None:
    raise RuntimeError(
        "Existen intentos de pago y movimientos que podrían ser contables; "
        "realiza respaldo y compensación antes de cualquier eliminación de datos."
    )
