"""unificar empresas clientes y compras

Revision: fc6ee96d81da
Revises: 0003_cuentas_clientes, cu10_01_compras
"""
from alembic import op
import sqlalchemy as sa


revision = 'fc6ee96d81da'
down_revision = ('0003_cuentas_clientes', 'cu10_01_compras')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
