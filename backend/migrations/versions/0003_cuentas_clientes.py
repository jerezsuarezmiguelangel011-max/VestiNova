"""Cuentas de cliente por tienda y actores de personal; conserva los datos previos."""
from alembic import op
import sqlalchemy as sa


revision = "0003_cuentas_clientes"
down_revision = "0002_empresas_inventario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_membresias_rol", "membresias_empresa", type_="check")
    op.create_check_constraint("ck_membresias_rol", "membresias_empresa", "rol IN ('ADMINISTRADOR', 'OPERADOR', 'ENCARGADO_SUCURSAL', 'CAJERO')")
    op.create_table("clientes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("correo", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("empresa_id", "correo", name="uq_clientes_empresa_correo"),
    )
    op.create_index("ix_clientes_empresa_id", "clientes", ["empresa_id"])
    op.create_table("sesiones_cliente",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_sesiones_cliente_cliente_id", "sesiones_cliente", ["cliente_id"])


def downgrade() -> None:
    raise RuntimeError("No se eliminan cuentas ni sesiones automáticamente. Restaura un respaldo explícito para retroceder.")
