"""CU19/CU20/CU23: lista de deseos y acceso a reportes comerciales."""
from alembic import op
import sqlalchemy as sa

revision = "c192023a2026"
down_revision = "c15b4d1f2026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deseos_cu23",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("variante_id", sa.Integer(), primary_key=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["variante_id", "empresa_id"],
            ["variantes_producto.id", "variantes_producto.empresa_id"],
            name="fk_deseos_variante_empresa",
        ),
    )
    op.create_index("ix_deseos_cu23_empresa_cliente", "deseos_cu23", ["empresa_id", "cliente_id"])

    # Sincronizar perfiles del sistema existentes (los perfiles personalizados
    # no reciben permisos nuevos automáticamente).
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, codigo_sistema FROM roles_empresa "
        "WHERE codigo_sistema IN ('ADMINISTRADOR', 'ENCARGADO_SUCURSAL')"
    )).fetchall()
    for role_id, _ in rows:
        connection.execute(sa.text(
            "INSERT INTO permisos_rol (rol_empresa_id, codigo) "
            "SELECT :role, 'reportes.consultar' "
            "WHERE NOT EXISTS (SELECT 1 FROM permisos_rol "
            "WHERE rol_empresa_id = :role AND codigo = 'reportes.consultar')"
        ), {"role": role_id})


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text(
        "DELETE FROM permisos_rol WHERE codigo = 'reportes.consultar'"
    ))
    op.drop_index("ix_deseos_cu23_empresa_cliente", table_name="deseos_cu23")
    op.drop_table("deseos_cu23")
