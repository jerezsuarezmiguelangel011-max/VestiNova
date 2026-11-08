"""CU15: comparación monetaria a centavos, compatible con SQLite y PostgreSQL.

La revisión anterior verificaba "cambio = efectivo - total" sin redondear;
SQLite usa REAL para Numeric y rechaza 200.00 - 160.20 = 39.80 por error
binario de representación. La aplicación calcula con Decimal.
"""
from alembic import op

revision = "c15b4d1f2026"
down_revision = "c15a4d1f2026"
branch_labels = None
depends_on = None


def upgrade():
    # La base de demo y despliegue es PostgreSQL. Se usa batch para que la
    # misma migración pueda funcionar sobre SQLite de desarrollo.
    with op.batch_alter_table("ventas_contado_cu15") as batch:
        batch.drop_constraint("ck_cu15_efectivo", type_="check")
        batch.create_check_constraint(
            "ck_cu15_efectivo",
            "total > 0 AND efectivo >= total AND ROUND(efectivo - total, 2) = cambio",
        )


def downgrade():
    # No restablecer una validación defectuosa en SQLite.
    raise RuntimeError("No se admite retroceder a la restricción que rechaza centavos válidos.")
