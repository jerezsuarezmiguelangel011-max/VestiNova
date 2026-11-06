"""CU08: atributos opcionales para búsqueda y detalle de prendas.

Todos los productos existentes conservan sus datos: los nuevos atributos
se crean vacíos y solo se publican cuando el administrador los registra.
"""
from alembic import op
import sqlalchemy as sa

revision = "c08a4d1f2026"
down_revision = "a07f311c2d26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("productos") as batch:
        batch.add_column(sa.Column("material", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("medidas", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("temporada", sa.String(60), nullable=False, server_default=""))


def downgrade() -> None:
    raise RuntimeError(
        "Los atributos comerciales pueden contener datos publicados. "
        "Realiza un respaldo antes de plantear una reversión destructiva."
    )
