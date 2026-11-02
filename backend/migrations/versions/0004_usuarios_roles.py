"""CU02: perfiles propios, permisos y nombre local sin alterar identidades globales."""
from alembic import op
import sqlalchemy as sa


revision = "0004_usuarios_roles"
down_revision = "0003_cuentas_clientes"
branch_labels = None
depends_on = None

# Instantánea de la política al crear esta revisión; no importar código mutable.
ALL = ("catalogo.consultar", "catalogo.gestionar", "sucursales.consultar", "sucursales.gestionar",
       "inventario.consultar", "inventario.registrar", "descarga.consultar", "empresa.editar",
       "usuarios.consultar", "usuarios.crear", "usuarios.editar", "roles.consultar", "roles.gestionar")
READ = ("catalogo.consultar", "sucursales.consultar", "inventario.consultar", "descarga.consultar")
PRESETS = (
    ("ADMINISTRADOR", "Administrador de empresa", "Administración completa de la empresa.", ALL),
    ("ENCARGADO_SUCURSAL", "Encargado de sucursal", "Consulta de información en sucursales asignadas.", READ),
    ("CAJERO", "Cajero", "Consulta de información en sucursales asignadas.", READ),
    ("OPERADOR", "Operador", "Perfil histórico de consulta en sucursales asignadas.", READ),
)


def upgrade() -> None:
    op.create_table("roles_empresa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nombre_clave", sa.String(360), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        sa.Column("codigo_sistema", sa.String(20), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("id", "empresa_id", name="uq_roles_id_empresa"),
        sa.UniqueConstraint("empresa_id", "codigo_sistema", name="uq_roles_empresa_sistema"),
        sa.UniqueConstraint("empresa_id", "nombre_clave", name="uq_roles_empresa_nombre"),
        sa.CheckConstraint("codigo_sistema IS NULL OR codigo_sistema IN ('ADMINISTRADOR', 'OPERADOR', 'ENCARGADO_SUCURSAL', 'CAJERO')", name="ck_roles_sistema"),
    )
    op.create_index("ix_roles_empresa_empresa_id", "roles_empresa", ["empresa_id"])
    op.create_table("permisos_rol",
        sa.Column("rol_empresa_id", sa.Integer(), sa.ForeignKey("roles_empresa.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("codigo", sa.String(60), primary_key=True),
    )
    with op.batch_alter_table("membresias_empresa") as batch:
        batch.add_column(sa.Column("nombre", sa.String(120), nullable=True))
        batch.add_column(sa.Column("rol_empresa_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_membresia_rol_empresa", "roles_empresa", ["rol_empresa_id", "empresa_id"], ["id", "empresa_id"])

    connection = op.get_bind()
    metadata = sa.MetaData()
    companies = sa.Table("empresas", metadata, autoload_with=connection)
    roles = sa.Table("roles_empresa", metadata, autoload_with=connection)
    permissions = sa.Table("permisos_rol", metadata, autoload_with=connection)
    members = sa.Table("membresias_empresa", metadata, autoload_with=connection)
    users = sa.Table("administradores", metadata, autoload_with=connection)
    for company_id in connection.scalars(sa.select(companies.c.id)):
        for code, name, description, codes in PRESETS:
            role_id = connection.execute(roles.insert().values(empresa_id=company_id, nombre=name,
                nombre_clave=name.casefold(), descripcion=description, codigo_sistema=code, activo=True)).inserted_primary_key[0]
            connection.execute(permissions.insert(), [{"rol_empresa_id": role_id, "codigo": permission} for permission in codes])
            connection.execute(members.update().where(members.c.empresa_id == company_id, members.c.rol == code).values(rol_empresa_id=role_id))
    connection.execute(members.update().values(nombre=sa.select(users.c.nombre).where(users.c.id == members.c.administrador_id).scalar_subquery()))


def downgrade() -> None:
    raise RuntimeError("No se eliminan perfiles ni pertenencias automáticamente. Restaura un respaldo explícito para retroceder.")
