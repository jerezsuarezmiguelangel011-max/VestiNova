from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKeyConstraint, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utc_now


class ConfiguracionVestidor(Base):
    __tablename__ = "configuraciones_vestidor"
    __table_args__ = (
        ForeignKeyConstraint(["variante_id", "empresa_id"], ["variantes_producto.id", "variantes_producto.empresa_id"], name="fk_vestidor_variante_empresa"),
        CheckConstraint("tipo_prenda IN ('POLERA', 'CAMISA')", name="ck_vestidor_tipo"),
        CheckConstraint("factor_ancho BETWEEN 0.5 AND 2.5 AND factor_alto BETWEEN 0.5 AND 2.5", name="ck_vestidor_escala"),
        CheckConstraint("offset_x BETWEEN -0.5 AND 0.5 AND offset_y BETWEEN -0.5 AND 0.5", name="ck_vestidor_offset"),
    )
    variante_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recurso_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    tipo_prenda: Mapped[str] = mapped_column(String(12), nullable=False)
    factor_ancho: Mapped[float] = mapped_column(Float, nullable=False, default=1.9)
    factor_alto: Mapped[float] = mapped_column(Float, nullable=False, default=1.2)
    offset_x: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    offset_y: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    anclajes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
