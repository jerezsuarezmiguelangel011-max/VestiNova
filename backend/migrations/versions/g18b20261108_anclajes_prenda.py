"""Calibración opcional de puntos de la prenda; conserva recursos y configuraciones."""
from alembic import op
import sqlalchemy as sa

revision = "g18b20261108"
down_revision = "f08a20261108"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("configuraciones_vestidor", sa.Column("anclajes", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("La calibración publicada forma parte de los datos; no se elimina automáticamente.")
