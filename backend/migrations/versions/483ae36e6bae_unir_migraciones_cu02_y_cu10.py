"""Unir migraciones CU02 y CU10

Revision: 483ae36e6bae
Revises: fc6ee96d81da, 0004_usuarios_roles
"""
from alembic import op
import sqlalchemy as sa


revision = '483ae36e6bae'
down_revision = ('fc6ee96d81da', '0004_usuarios_roles')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
