"""CU18: configuración por variante y empresa, sin alterar catálogo ni inventario."""
from alembic import op
import sqlalchemy as sa

revision = "e18a182026"
down_revision = "d21e22a12026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("configuraciones_vestidor",
        sa.Column("variante_id",sa.Integer(),primary_key=True), sa.Column("empresa_id",sa.Integer(),nullable=False),
        sa.Column("recurso_url",sa.String(2048),nullable=False), sa.Column("tipo_prenda",sa.String(12),nullable=False),
        sa.Column("factor_ancho",sa.Float(),nullable=False),sa.Column("factor_alto",sa.Float(),nullable=False),
        sa.Column("offset_x",sa.Float(),nullable=False),sa.Column("offset_y",sa.Float(),nullable=False),
        sa.Column("activo",sa.Boolean(),nullable=False),sa.Column("actualizado_en",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["variante_id","empresa_id"],["variantes_producto.id","variantes_producto.empresa_id"],name="fk_vestidor_variante_empresa"),
        sa.CheckConstraint("tipo_prenda IN ('POLERA', 'CAMISA')",name="ck_vestidor_tipo"),
        sa.CheckConstraint("factor_ancho BETWEEN 0.5 AND 2.5 AND factor_alto BETWEEN 0.5 AND 2.5",name="ck_vestidor_escala"),
        sa.CheckConstraint("offset_x BETWEEN -0.5 AND 0.5 AND offset_y BETWEEN -0.5 AND 0.5",name="ck_vestidor_offset"))
    op.create_index("ix_configuraciones_vestidor_empresa_id","configuraciones_vestidor",["empresa_id"])


def downgrade():
    raise RuntimeError("No se eliminan configuraciones existentes automáticamente; prepara una revisión explícita.")
