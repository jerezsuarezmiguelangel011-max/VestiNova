"""CU07: saldos comprometidos, ajustes diferenciados y reingresos trazables.

Las filas existentes conservan su stock físico; no se inventan reservas.
Las nuevas columnas se crean con valores por defecto compatibles con los
movimientos previos a esta versión.
"""
from alembic import op
import sqlalchemy as sa


revision = "a07f311c2d26"
down_revision = "f27c9a4d1b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("existencias") as batch:
        batch.add_column(sa.Column("cantidad_comprometida", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint(
            "ck_existencias_comprometido_valido",
            "cantidad_comprometida >= 0 AND cantidad_comprometida <= cantidad",
        )
    with op.batch_alter_table("movimientos_inventario") as batch:
        batch.add_column(sa.Column("clase", sa.String(12), nullable=False, server_default="MOVIMIENTO"))
        batch.add_column(sa.Column("origen_tipo", sa.String(20), nullable=True))
        batch.add_column(sa.Column("origen_id", sa.String(36), nullable=True))
        batch.create_check_constraint(
            "ck_movimientos_clase", "clase IN ('MOVIMIENTO', 'AJUSTE', 'REINGRESO')"
        )
        batch.create_check_constraint(
            "ck_movimientos_reingreso_origen",
            "(clase = 'REINGRESO' AND tipo = 'ENTRADA' AND origen_tipo = 'POSTVENTA' "
            "AND origen_id IS NOT NULL) OR "
            "(clase != 'REINGRESO' AND origen_tipo IS NULL AND origen_id IS NULL)",
        )
        batch.create_unique_constraint(
            "uq_movimientos_reingreso_origen",
            ["empresa_id", "origen_tipo", "origen_id", "variante_id"],
        )

    # Habilitar el permiso explícito en roles de sistema ya existentes.
    # Los roles personalizados conservan sus permisos actuales.
    connection = op.get_bind()
    roles = sa.table(
        "roles_empresa", sa.column("id", sa.Integer()),
        sa.column("codigo_sistema", sa.String(20)),
    )
    grants = sa.table(
        "permisos_rol", sa.column("rol_empresa_id", sa.Integer()),
        sa.column("codigo", sa.String(60)),
    )
    role_rows = connection.execute(
        sa.select(roles.c.id).where(
            roles.c.codigo_sistema.in_(("ADMINISTRADOR", "ENCARGADO_SUCURSAL"))
        )
    ).scalars().all()
    for role_id in role_rows:
        exists = connection.execute(
            sa.select(grants.c.codigo).where(
                grants.c.rol_empresa_id == role_id,
                grants.c.codigo == "inventario.ajustar",
            )
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(
                grants.insert().values(
                    rol_empresa_id=role_id, codigo="inventario.ajustar"
                )
            )


def downgrade() -> None:
    raise RuntimeError(
        "CU07 conserva movimientos de inventario y posibles compromisos activos. "
        "Restaura un respaldo explícito en vez de eliminar información mediante downgrade."
    )
