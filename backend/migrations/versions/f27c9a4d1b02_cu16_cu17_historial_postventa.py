"""CU16 historial de compras y CU17 solicitudes de postventa."""

from alembic import op
import sqlalchemy as sa


revision = "f27c9a4d1b02"
down_revision = "e4b7a2d16c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solicitudes_postventa",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("compra_id", sa.String(36), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("respuesta", sa.Text(), nullable=True),
        sa.Column("referencia_reposicion", sa.String(40), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resuelto_por_id", sa.Integer(), sa.ForeignKey("administradores.id"), nullable=True),
        sa.UniqueConstraint("empresa_clave", "id", name="uq_solicitudes_postventa_empresa_id"),
        sa.ForeignKeyConstraint(
            ["empresa_clave", "compra_id"],
            ["compras_digitales.empresa_clave", "compras_digitales.id"],
            name="fk_postventa_compra_empresa",
        ),
        sa.CheckConstraint("tipo IN ('CAMBIO', 'DEVOLUCION')", name="ck_postventa_tipo"),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA', 'COMPLETADA')", name="ck_postventa_estado"),
    )
    op.create_index(
        "ix_postventa_empresa_sucursal_estado_fecha",
        "solicitudes_postventa",
        ["empresa_id", "sucursal_id", "estado", "creado_en"],
    )
    op.create_index(
        "ix_postventa_empresa_cliente_compra",
        "solicitudes_postventa",
        ["empresa_id", "cliente_id", "compra_id"],
    )
    op.create_table(
        "solicitudes_postventa_lineas",
        sa.Column("solicitud_id", sa.String(36), primary_key=True),
        sa.Column("producto_id", sa.Integer(), primary_key=True),
        sa.Column("empresa_clave", sa.Text(), nullable=False),
        sa.Column("compra_posicion", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("variante_ref", sa.JSON(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["empresa_clave", "solicitud_id"],
            ["solicitudes_postventa.empresa_clave", "solicitudes_postventa.id"],
            name="fk_postventa_linea_solicitud_empresa",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("compra_posicion >= 0", name="ck_postventa_linea_compra_posicion"),
        sa.CheckConstraint("producto_id > 0", name="ck_postventa_linea_producto"),
        sa.CheckConstraint("cantidad > 0", name="ck_postventa_linea_cantidad"),
        sa.CheckConstraint("precio_unitario > 0 AND precio_unitario <= 99999999.99", name="ck_postventa_linea_precio"),
    )

    connection = op.get_bind()
    roles = sa.table(
        "roles_empresa",
        sa.column("id", sa.Integer()),
        sa.column("codigo_sistema", sa.String(40)),
    )
    role_permissions = sa.table(
        "permisos_rol",
        sa.column("rol_empresa_id", sa.Integer()),
        sa.column("codigo", sa.String(60)),
    )
    permissions_by_role = {
        "ADMINISTRADOR": ("postventa.consultar", "postventa.gestionar"),
        "ENCARGADO_SUCURSAL": ("postventa.consultar", "postventa.gestionar"),
        "CAJERO": ("postventa.consultar", "postventa.gestionar"),
        "OPERADOR": ("postventa.consultar",),
    }
    role_rows = connection.execute(
        sa.select(roles.c.id, roles.c.codigo_sistema).where(roles.c.codigo_sistema.in_(permissions_by_role))
    ).all()
    for role_id, role_code in role_rows:
        existing = set(connection.execute(
            sa.select(role_permissions.c.codigo).where(role_permissions.c.rol_empresa_id == role_id)
        ).scalars())
        for permission in permissions_by_role[role_code]:
            if permission not in existing:
                connection.execute(role_permissions.insert().values(rol_empresa_id=role_id, codigo=permission))


def downgrade() -> None:
    connection = op.get_bind()
    roles = sa.table("roles_empresa", sa.column("id", sa.Integer()))
    role_permissions = sa.table(
        "permisos_rol",
        sa.column("rol_empresa_id", sa.Integer()),
        sa.column("codigo", sa.String(60)),
    )
    role_ids = sa.select(roles.c.id)
    connection.execute(role_permissions.delete().where(
        role_permissions.c.rol_empresa_id.in_(role_ids),
        role_permissions.c.codigo.in_(("postventa.consultar", "postventa.gestionar")),
    ))
    op.drop_table("solicitudes_postventa_lineas")
    op.drop_index("ix_postventa_empresa_cliente_compra", table_name="solicitudes_postventa")
    op.drop_index("ix_postventa_empresa_sucursal_estado_fecha", table_name="solicitudes_postventa")
    op.drop_table("solicitudes_postventa")
