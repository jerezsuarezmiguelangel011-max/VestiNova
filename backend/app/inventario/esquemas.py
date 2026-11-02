"""Contratos de entrada y salida para inventario."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.esquemas_operacionales import OperationalResponse


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
