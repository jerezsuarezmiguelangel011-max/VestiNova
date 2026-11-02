"""Tipos de respuesta compartidos por las operaciones de la aplicación."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_serializer


class OperationalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("creado_en", "actualizado_en", "generado_en", check_fields=False)
    def utc_date(self, value: datetime | None):
        if value is None:
            return None
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
