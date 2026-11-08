"""Unir la cadena CU25/CU26 con la cadena de caja y reservas ya existente.

No altera tablas ni datos: confirma que ambas ramas de migraciones están aplicadas.
"""
from alembic import op

revision = "c26merge2026"
down_revision = ("c26a4d1f2026", "c15b4d1f2026")
branch_labels = None
depends_on = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
