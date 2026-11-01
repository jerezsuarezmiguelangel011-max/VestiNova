from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.image_url import validate_image_url


def normalizar_correo(value: str) -> str:
    result = value.strip().lower()
    if len(result) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", result):
        raise ValueError("Introduce un correo electrónico válido.")
    return result


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    _correo = field_validator("correo")(normalizar_correo)


class AdministradorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    correo: str
    rol: Literal["ADMINISTRADOR"] = "ADMINISTRADOR"
    activo: bool
    es_superadministrador: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    administrador: AdministradorResponse


Precio = Annotated[Decimal, Field(gt=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2, allow_inf_nan=False)]


class CamposProducto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("nombre", check_fields=False)
    @classmethod
    def nombre_valido(cls, value: str | None):
        if value is not None and len(value.strip()) < 3:
            raise ValueError("El nombre debe tener al menos 3 caracteres.")
        return value

    @field_validator("slug", check_fields=False)
    @classmethod
    def slug_valido(cls, value: str | None):
        if value is not None and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError("El slug admite letras minúsculas, números y guiones simples.")
        return value

    @field_validator("imagen_url", check_fields=False)
    @classmethod
    def imagen_valida(cls, value: str | None):
        return validate_image_url(value)


class ProductoCreate(CamposProducto):
    nombre: str = Field(min_length=3, max_length=120)
    slug: str | None = Field(default=None, min_length=3, max_length=140)
    descripcion: str = Field(default="", max_length=3000)
    precio: Precio
    imagen_url: str | None = Field(default=None, max_length=2048)
    activo: bool = True


class ProductoPatch(CamposProducto):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    slug: str | None = Field(default=None, min_length=3, max_length=140)
    descripcion: str | None = Field(default=None, max_length=3000)
    precio: Precio | None = None
    imagen_url: str | None = Field(default=None, max_length=2048)
    activo: bool | None = None

    @model_validator(mode="after")
    def no_vacios(self):
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo para actualizar.")
        for field in self.model_fields_set - {"imagen_url"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no admite null.")
        return self


class ProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    nombre: str
    descripcion: str
    precio: Decimal
    moneda: Literal["BOB"]
    imagen_url: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    @field_serializer("precio")
    def serializar_precio(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("creado_en", "actualizado_en")
    def serializar_fecha(self, value: datetime) -> str:
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


class ListaProductos(BaseModel):
    items: list[ProductoResponse]
    total: int
    limit: int
    offset: int
