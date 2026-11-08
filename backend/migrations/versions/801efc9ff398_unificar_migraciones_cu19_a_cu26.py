"""unificar migraciones CU19 a CU26

Revision: 801efc9ff398
Revises: c19c20c23demo, c26merge2026
"""
from alembic import op
import sqlalchemy as sa


revision = '801efc9ff398'
down_revision = ('c19c20c23demo', 'c26merge2026')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
