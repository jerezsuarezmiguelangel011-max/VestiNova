"""Recortes publicados de prendas; nunca recibe capturas de la cámara del Cliente."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import BACKEND_ROOT

STORAGE_ROOT = BACKEND_ROOT / "storage" / "vestidor"
MAX_BYTES = 6 * 1024 * 1024
UPLOADED_PATH = re.compile(r"^/api/vestidor/recursos/empresas/([1-9][0-9]*)/([a-f0-9]{64})\.png$")


def uploaded_reference(value: str):
    match = UPLOADED_PATH.fullmatch(value)
    return (int(match[1]), match[2]) if match else None


def resource_path(company: int, digest: str) -> Path:
    if company < 1 or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise HTTPException(404, "Recurso no disponible.")
    return STORAGE_ROOT / str(company) / (digest + ".png")


def validate_png(data: bytes) -> None:
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "La imagen puede ocupar como máximo 6 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG" or not (1 <= image.width <= 2048 and 1 <= image.height <= 2048):
                    raise ValueError()
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError()
                rgba = image.convert("RGBA")
                alpha = rgba.getchannel("A")
                histogram = alpha.histogram()
                transparent = sum(histogram[:16])
                if transparent < image.width * image.height * .02 or sum(histogram[16:]) == 0:
                    raise ValueError()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Usa un PNG estático de hasta 2048 × 2048, con la prenda visible y fondo transparente. Una foto JPG o con fondo no sirve para superponerla.") from None


def store_png(company: int, data: bytes) -> str:
    digest = sha256(data).hexdigest()
    target = resource_path(company, digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as output:
            output.write(data)
    except FileExistsError:
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise HTTPException(503, "El recurso guardado necesita revisión; no se sobrescribió.") from None
    return f"/api/vestidor/recursos/empresas/{company}/{digest}.png"
