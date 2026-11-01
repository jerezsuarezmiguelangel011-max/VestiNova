"""Política compartida con frontend/src/app/products/image-url.ts.

La URL se valida sin descargar imágenes ni cambiar su representación almacenada.
Los casos comunes de contrato están en docs/contracts/image-url-cases.json.
"""
import re

from pydantic import HttpUrl, TypeAdapter, ValidationError

IMAGE_URL_ERROR = "Introduce una URL http o https completa, con host y puerto válidos, sin espacios ni credenciales."
_http_url = TypeAdapter(HttpUrl)


def validate_image_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    # Ambos analizadores aceptan algunas formas abreviadas o normalizan espacios
    # y barras invertidas: el contrato las rechaza explícitamente.
    authority = re.match(r"^https?://([^/?#]+)", value, re.IGNORECASE)
    if (
        len(value) > 2048
        or re.search(r"[\s\\\x00-\x1f\x7f]", value)
        or authority is None
        or "@" in authority[1]
        or authority[1].endswith(":")
    ):
        raise ValueError(IMAGE_URL_ERROR)
    try:
        parsed = _http_url.validate_python(value)
    except ValidationError:
        raise ValueError(IMAGE_URL_ERROR) from None
    if not parsed.host or parsed.username is not None or parsed.password is not None:
        raise ValueError(IMAGE_URL_ERROR)
    return value
