"""CU01-CU04: bitácora, datos de sucursal y categorías de prendas."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "d91ac3b48f20"
down_revision = "483ae36e6bae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorias_producto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("nombre_clave", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", name="uq_categorias_producto_id_empresa"),
        sa.UniqueConstraint("empresa_id", "nombre_clave", name="uq_categorias_producto_empresa_nombre"),
    )
    op.create_index("ix_categorias_producto_empresa_id", "categorias_producto", ["empresa_id"])

    with op.batch_alter_table("productos") as batch:
        batch.add_column(sa.Column("categoria_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_productos_categoria_empresa",
            "categorias_producto",
            ["categoria_id", "empresa_id"],
            ["id", "empresa_id"],
        )
        batch.create_index("ix_productos_empresa_categoria", ["empresa_id", "categoria_id"])

    connection = op.get_bind()
    metadata = sa.MetaData()
    products = sa.Table("productos", metadata, autoload_with=connection)
    categories = sa.Table("categorias_producto", metadata, autoload_with=connection)
    company_ids = connection.scalars(sa.select(products.c.empresa_id).distinct()).all()
    for company_id in company_ids:
        result = connection.execute(categories.insert().values(
            empresa_id=company_id,
            nombre="General",
            nombre_clave="general",
            descripcion="Categoría inicial para prendas existentes.",
            activo=True,
            creado_en=datetime.now(timezone.utc),
        ))
        category_id = result.inserted_primary_key[0]
        connection.execute(products.update().where(
            products.c.empresa_id == company_id,
            products.c.categoria_id.is_(None),
        ).values(categoria_id=category_id))

    with op.batch_alter_table("sucursales") as batch:
        batch.add_column(sa.Column("ciudad", sa.String(100), nullable=False, server_default=""))
        batch.add_column(sa.Column("ubicacion", sa.String(240), nullable=False, server_default=""))
        batch.add_column(sa.Column("contacto", sa.String(120), nullable=False, server_default=""))

    op.create_table(
        "eventos_auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("actor_nombre", sa.String(120), nullable=False),
        sa.Column("actor_correo", sa.String(254), nullable=False),
        sa.Column("accion", sa.String(80), nullable=False),
        sa.Column("entidad", sa.String(40), nullable=False),
        sa.Column("entidad_id", sa.String(80), nullable=False),
        sa.Column("detalles", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id", "empresa_id"],
            ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"],
            name="fk_auditoria_actor_empresa",
        ),
    )
    op.create_index("ix_auditoria_empresa_fecha_id", "eventos_auditoria", ["empresa_id", "creado_en", "id"])
    op.create_index("ix_auditoria_empresa_actor_fecha", "eventos_auditoria", ["empresa_id", "actor_id", "creado_en"])

    permissions = sa.Table("permisos_rol", metadata, autoload_with=connection)
    roles = sa.Table("roles_empresa", metadata, autoload_with=connection)
    admin_role_ids = connection.scalars(sa.select(roles.c.id).where(roles.c.codigo_sistema == "ADMINISTRADOR")).all()
    new_permissions = [
        {"rol_empresa_id": role_id, "codigo": "auditoria.consultar"}
        for role_id in admin_role_ids
        if connection.scalar(sa.select(sa.func.count()).select_from(permissions).where(
            permissions.c.rol_empresa_id == role_id,
            permissions.c.codigo == "auditoria.consultar",
        )) == 0
    ]
    if new_permissions:
        connection.execute(permissions.insert(), new_permissions)


def downgrade() -> None:
    raise RuntimeError("La bitácora no se elimina automáticamente; restaura un respaldo explícito para retroceder.")
