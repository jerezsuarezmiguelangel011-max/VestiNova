"""Contratos de entrada y salida para las variantes del catálogo."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.esquemas_operacionales import OperationalResponse


class CamposVariante(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("talla", "color", mode="before", check_fields=False)
    @classmethod
    def normalize(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class VarianteCreate(CamposVariante):
    talla: str = Field(min_length=1, max_length=30)
    color: str = Field(min_length=1, max_length=60)
    activo: bool = Field(default=True, strict=True)


class VariantePatch(CamposVariante):
    talla: str | None = Field(default=None, min_length=1, max_length=30)
    color: str | None = Field(default=None, min_length=1, max_length=60)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def nonempty_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Envía al menos un cambio no nulo de talla, color o estado.")
        return self


class VarianteResponse(OperationalResponse):
    id: int
    producto_id: int
    talla: str
    color: str
    activo: bool
    creado_en: datetime
