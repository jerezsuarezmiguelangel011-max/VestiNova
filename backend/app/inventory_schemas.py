"""Contratos operacionales; no alteran la respuesta pública de Producto."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class OperationalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("creado_en", "actualizado_en", "generado_en", check_fields=False)
    def utc_date(self, value: datetime | None):
        if value is None:
            return None
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


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


class MovimientoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    sucursal_id: int = Field(gt=0, strict=True)
    variante_id: int = Field(gt=0, strict=True)
    tipo: Literal["ENTRADA", "SALIDA"]
    cantidad: int = Field(gt=0, le=1_000_000_000, strict=True)
    motivo: str = Field(min_length=3, max_length=300)


class MovimientoResponse(OperationalResponse):
    id: str
    empresa_id: int
    sucursal_id: int
    variante_id: int
    usuario_id: int
    tipo: Literal["ENTRADA", "SALIDA"]
    delta: int
    saldo_resultante: int
    motivo: str
    creado_en: datetime


class ExistenciaResponse(OperationalResponse):
    empresa_id: int
    sucursal_id: int
    variante_id: int
    cantidad: int
    actualizado_en: datetime


class ListaExistencias(BaseModel):
    items: list[ExistenciaResponse]
    total: int
    limit: int
    offset: int


class ListaMovimientos(BaseModel):
    items: list[MovimientoResponse]
    total: int
    limit: int
    offset: int
