"""CU21/CU22: capacidades empresariales sin modificar registros comerciales."""
from alembic import op
import sqlalchemy as sa

revision = "d21e22a12026"
down_revision = "c09a4d1f2026"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    roles = sa.table("roles_empresa", sa.column("id", sa.Integer()), sa.column("codigo_sistema", sa.String(20)))
    permissions = sa.table("permisos_rol", sa.column("rol_empresa_id", sa.Integer()), sa.column("codigo", sa.String(60)))
    for code, presets in (("reportes.ia.consultar", ["ADMINISTRADOR", "ENCARGADO_SUCURSAL"]), ("analitica.consultar", ["ADMINISTRADOR"])):
        for identifier in connection.scalars(sa.select(roles.c.id).where(roles.c.codigo_sistema.in_(presets))):
            exists = connection.scalar(sa.select(permissions.c.codigo).where(permissions.c.rol_empresa_id == identifier, permissions.c.codigo == code))
            if exists is None:
                connection.execute(permissions.insert().values(rol_empresa_id=identifier, codigo=code))


def downgrade():
    raise RuntimeError("No se retiran permisos existentes automáticamente; prepara una revisión explícita.")
