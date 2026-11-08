from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReportType = Literal["ventas_diarias", "prendas_vendidas", "inventario", "abastecimiento"]


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desde: date | None = None
    hasta: date | None = None
    sucursal_id: int | None = Field(default=None, gt=0, strict=True)
    categoria_id: int | None = Field(default=None, gt=0, strict=True)
    producto_id: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def dates(self):
        if self.desde and self.hasta:
            if self.desde > self.hasta or (self.hasta - self.desde).days > 365:
                raise ValueError("El período debe ser coherente y no superar 366 días.")
        return self


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consulta: str = Field(min_length=5, max_length=800)
    filtros: Filters = Field(default_factory=Filters)


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: Literal["ventas_diarias", "prendas_vendidas", "inventario", "abastecimiento", "aclaracion", "no_admitido"]
    desde: date | None = None
    hasta: date | None = None
    sucursal: str | None = Field(default=None, max_length=120)
    categoria: str | None = Field(default=None, max_length=120)
    producto: str | None = Field(default=None, max_length=120)
    mensaje: str = Field(default="", max_length=300)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: ReportType
    filtros: Filters
    formato: Literal["html", "pdf", "xlsx"]


class DashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filtros: Filters = Field(default_factory=Filters)
    analisis: Literal["prediccion", "agrupaciones", "ambos"] = "ambos"
