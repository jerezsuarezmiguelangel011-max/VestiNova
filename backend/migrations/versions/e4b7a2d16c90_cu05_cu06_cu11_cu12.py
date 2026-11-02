"""CU05-CU06-CU11-CU12: promociones, abastecimiento, empresas y planes."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "e4b7a2d16c90"
down_revision = "d91ac3b48f20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        batch.add_column(sa.Column("nit", sa.String(30), nullable=True))
        batch.add_column(sa.Column("correo_contacto", sa.String(254), nullable=True))
        batch.add_column(sa.Column("telefono_contacto", sa.String(40), nullable=True))

    op.create_table(
        "promociones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", name="uq_promociones_id_empresa"),
        sa.CheckConstraint("tipo IN ('PORCENTAJE', 'PRECIO_FIJO')", name="ck_promociones_tipo"),
        sa.CheckConstraint("valor > 0", name="ck_promociones_valor_positivo"),
        sa.CheckConstraint("tipo != 'PORCENTAJE' OR valor < 100", name="ck_promociones_porcentaje_menor_100"),
        sa.CheckConstraint("fin > inicio", name="ck_promociones_vigencia"),
    )
    op.create_index("ix_promociones_empresa_id", "promociones", ["empresa_id"])
    op.create_index("ix_promociones_empresa_vigencia", "promociones", ["empresa_id", "activo", "inicio", "fin"])
    op.create_table(
        "promociones_productos",
        sa.Column("empresa_id", sa.Integer(), primary_key=True),
        sa.Column("promocion_id", sa.Integer(), primary_key=True),
        sa.Column("producto_id", sa.Integer(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["promocion_id", "empresa_id"], ["promociones.id", "promociones.empresa_id"],
            name="fk_promocion_producto_promocion_empresa", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["producto_id", "empresa_id"], ["productos.id", "productos.empresa_id"],
            name="fk_promocion_producto_producto_empresa",
        ),
    )
    op.create_index("ix_promociones_productos_empresa_producto", "promociones_productos", ["empresa_id", "producto_id"])

    op.create_table(
        "proveedores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("contacto", sa.String(120), nullable=False, server_default=""),
        sa.Column("correo", sa.String(254), nullable=False, server_default=""),
        sa.Column("telefono", sa.String(40), nullable=False, server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", name="uq_proveedores_id_empresa"),
        sa.UniqueConstraint("empresa_id", "codigo", name="uq_proveedores_empresa_codigo"),
    )
    op.create_index("ix_proveedores_empresa_id", "proveedores", ["empresa_id"])
    op.create_index("ix_proveedores_empresa_activo", "proveedores", ["empresa_id", "activo"])
    op.create_table(
        "ordenes_abastecimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("proveedor_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, server_default="PENDIENTE"),
        sa.Column("observaciones", sa.String(500), nullable=False, server_default=""),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", name="uq_ordenes_abastecimiento_id_empresa"),
        sa.ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursales.id", "sucursales.empresa_id"], name="fk_orden_abastecimiento_sucursal_empresa"),
        sa.ForeignKeyConstraint(["proveedor_id", "empresa_id"], ["proveedores.id", "proveedores.empresa_id"], name="fk_orden_abastecimiento_proveedor_empresa"),
        sa.ForeignKeyConstraint(["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_orden_abastecimiento_usuario_empresa"),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'PARCIAL', 'RECIBIDA', 'CANCELADA')", name="ck_orden_abastecimiento_estado"),
    )
    op.create_index("ix_ordenes_abastecimiento_empresa_fecha", "ordenes_abastecimiento", ["empresa_id", "creado_en"])
    op.create_table(
        "lineas_abastecimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("variante_id", sa.Integer(), nullable=False),
        sa.Column("cantidad_solicitada", sa.Integer(), nullable=False),
        sa.Column("cantidad_recibida", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", "orden_id", name="uq_lineas_abastecimiento_id_scope"),
        sa.ForeignKeyConstraint(["orden_id", "empresa_id"], ["ordenes_abastecimiento.id", "ordenes_abastecimiento.empresa_id"], name="fk_linea_abastecimiento_orden_empresa", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_linea_abastecimiento_variante_empresa"),
        sa.CheckConstraint("cantidad_solicitada > 0", name="ck_linea_abastecimiento_cantidad_solicitada"),
        sa.CheckConstraint("cantidad_recibida >= 0 AND cantidad_recibida <= cantidad_solicitada", name="ck_linea_abastecimiento_cantidad_recibida"),
        sa.CheckConstraint("costo_unitario > 0 AND costo_unitario <= 99999999.99", name="ck_linea_abastecimiento_costo"),
    )
    op.create_table(
        "recepciones_abastecimiento",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "empresa_id", "orden_id", name="uq_recepciones_abastecimiento_id_scope"),
        sa.ForeignKeyConstraint(["orden_id", "empresa_id"], ["ordenes_abastecimiento.id", "ordenes_abastecimiento.empresa_id"], name="fk_recepcion_abastecimiento_orden_empresa"),
        sa.ForeignKeyConstraint(["usuario_id", "empresa_id"], ["membresias_empresa.administrador_id", "membresias_empresa.empresa_id"], name="fk_recepcion_abastecimiento_usuario_empresa"),
    )
    op.create_table(
        "lineas_recepcion_abastecimiento",
        sa.Column("recepcion_id", sa.String(36), primary_key=True),
        sa.Column("linea_id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recepcion_id", "empresa_id", "orden_id"],
            ["recepciones_abastecimiento.id", "recepciones_abastecimiento.empresa_id", "recepciones_abastecimiento.orden_id"],
            name="fk_linea_recepcion_recepcion_scope", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linea_id", "empresa_id", "orden_id"],
            ["lineas_abastecimiento.id", "lineas_abastecimiento.empresa_id", "lineas_abastecimiento.orden_id"],
            name="fk_linea_recepcion_linea_scope",
        ),
        sa.CheckConstraint("cantidad > 0", name="ck_linea_recepcion_cantidad"),
    )

    op.create_table(
        "planes_saas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        sa.Column("precio_mensual", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_sucursales", sa.Integer(), nullable=False),
        sa.Column("max_productos", sa.Integer(), nullable=True),
        sa.Column("max_usuarios", sa.Integer(), nullable=True),
        sa.Column("prestaciones", sa.JSON(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("codigo", name="uq_planes_saas_codigo"),
        sa.CheckConstraint("precio_mensual IS NULL OR precio_mensual >= 0", name="ck_planes_saas_precio"),
        sa.CheckConstraint("max_sucursales > 0", name="ck_planes_saas_sucursales"),
        sa.CheckConstraint("max_productos IS NULL OR max_productos > 0", name="ck_planes_saas_productos"),
        sa.CheckConstraint("max_usuarios IS NULL OR max_usuarios > 0", name="ck_planes_saas_usuarios"),
    )
    op.create_index("ix_planes_saas_activo", "planes_saas", ["activo"])
    op.create_table(
        "suscripciones_empresa",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, server_default="ACTIVA"),
        sa.Column("inicia_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renueva_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["planes_saas.id"], name="fk_suscripciones_empresa_plan"),
        sa.CheckConstraint("estado IN ('ACTIVA', 'SUSPENDIDA', 'VENCIDA', 'CANCELADA')", name="ck_suscripciones_empresa_estado"),
        sa.CheckConstraint("renueva_en IS NULL OR renueva_en >= inicia_en", name="ck_suscripciones_empresa_fechas"),
    )

    connection = op.get_bind()
    metadata = sa.MetaData()
    plans = sa.Table("planes_saas", metadata, autoload_with=connection)
    subscriptions = sa.Table("suscripciones_empresa", metadata, autoload_with=connection)
    now = datetime.now(timezone.utc)
    connection.execute(plans.insert(), [
        {"codigo": "BASICO", "nombre": "BÃ¡sico", "descripcion": "Plan inicial; permite hasta dos sucursales activas.",
         "precio_mensual": None, "max_sucursales": 2, "max_productos": None, "max_usuarios": None,
         "prestaciones": [], "activo": True, "creado_en": now, "actualizado_en": now},
        {"codigo": "PROFESIONAL", "nombre": "Profesional", "descripcion": "Plan para empresas con hasta diez sucursales activas.",
         "precio_mensual": None, "max_sucursales": 10, "max_productos": None, "max_usuarios": None,
         "prestaciones": [], "activo": True, "creado_en": now, "actualizado_en": now},
    ])
    basic_id = connection.scalar(sa.select(plans.c.id).where(plans.c.codigo == "BASICO"))
    companies = sa.Table("empresas", metadata, autoload_with=connection)
    connection.execute(subscriptions.insert(), [
        {"empresa_id": company_id, "plan_id": basic_id, "estado": "ACTIVA", "inicia_en": now, "renueva_en": None, "actualizado_en": now}
        for company_id in connection.scalars(sa.select(companies.c.id)).all()
    ])

    permissions = sa.Table("permisos_rol", metadata, autoload_with=connection)
    roles = sa.Table("roles_empresa", metadata, autoload_with=connection)
    new_permissions = {
        "ADMINISTRADOR": ["abastecimiento.consultar", "abastecimiento.gestionar", "promociones.consultar", "promociones.gestionar", "plan.consultar"],
        "ENCARGADO_SUCURSAL": ["abastecimiento.consultar", "abastecimiento.gestionar", "promociones.consultar"],
    }
    role_rows = connection.execute(sa.select(roles.c.id, roles.c.codigo_sistema).where(roles.c.codigo_sistema.in_(new_permissions))).all()
    permissions_to_insert = []
    for role_id, system_code in role_rows:
        existing = set(connection.scalars(sa.select(permissions.c.codigo).where(permissions.c.rol_empresa_id == role_id)).all())
        permissions_to_insert.extend(
            {"rol_empresa_id": role_id, "codigo": code}
            for code in new_permissions[system_code] if code not in existing
        )
    if permissions_to_insert:
        connection.execute(permissions.insert(), permissions_to_insert)


def downgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    permissions = sa.Table("permisos_rol", metadata, autoload_with=connection)
    connection.execute(permissions.delete().where(permissions.c.codigo.in_([
        "abastecimiento.consultar", "abastecimiento.gestionar", "promociones.consultar",
        "promociones.gestionar", "plan.consultar",
    ])))
    op.drop_table("suscripciones_empresa")
    op.drop_index("ix_planes_saas_activo", table_name="planes_saas")
    op.drop_table("planes_saas")
    op.drop_table("lineas_recepcion_abastecimiento")
    op.drop_table("recepciones_abastecimiento")
    op.drop_table("lineas_abastecimiento")
    op.drop_index("ix_ordenes_abastecimiento_empresa_fecha", table_name="ordenes_abastecimiento")
    op.drop_table("ordenes_abastecimiento")
    op.drop_index("ix_proveedores_empresa_activo", table_name="proveedores")
    op.drop_index("ix_proveedores_empresa_id", table_name="proveedores")
    op.drop_table("proveedores")
    op.drop_index("ix_promociones_productos_empresa_producto", table_name="promociones_productos")
    op.drop_table("promociones_productos")
    op.drop_index("ix_promociones_empresa_vigencia", table_name="promociones")
    op.drop_index("ix_promociones_empresa_id", table_name="promociones")
    op.drop_table("promociones")
    with op.batch_alter_table("empresas") as batch:
        batch.drop_column("telefono_contacto")
        batch.drop_column("correo_contacto")
        batch.drop_column("nit")
