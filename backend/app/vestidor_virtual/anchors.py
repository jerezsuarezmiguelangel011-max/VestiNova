"""Calibración visual de la fotografía, no medidas corporales ni tallaje físico."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImagePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class GarmentAnchors(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    manga: Literal["CORTA", "LARGA"]
    hombro_izq: ImagePoint
    hombro_der: ImagePoint
    cintura_izq: ImagePoint
    cintura_der: ImagePoint
    manga_izq_media: ImagePoint
    manga_izq_fin: ImagePoint
    manga_der_media: ImagePoint
    manga_der_fin: ImagePoint

    @model_validator(mode="after")
    def usable_geometry(self):
        if (self.hombro_der.x - self.hombro_izq.x < .15
                or self.cintura_der.x - self.cintura_izq.x < .1
                or min(self.cintura_izq.y, self.cintura_der.y) - max(self.hombro_izq.y, self.hombro_der.y) < .2):
            raise ValueError("Marca los hombros separados y la cintura debajo, sin cruzar izquierda y derecha de la foto.")
        for shoulder, middle, end in ((self.hombro_izq, self.manga_izq_media, self.manga_izq_fin),
                                      (self.hombro_der, self.manga_der_media, self.manga_der_fin)):
            if (middle.x-shoulder.x)**2 + (middle.y-shoulder.y)**2 < .0025 or (end.x-middle.x)**2 + (end.y-middle.y)**2 < .0025:
                raise ValueError("Separa el hombro, la mitad y el extremo de cada manga.")
        if (self.manga_izq_media.x > self.hombro_izq.x + .04 or self.manga_izq_fin.x > self.hombro_izq.x + .04
                or self.manga_der_media.x < self.hombro_der.x - .04 or self.manga_der_fin.x < self.hombro_der.x - .04):
            raise ValueError("Utiliza una foto frontal con las mangas a los lados del cuerpo de la prenda.")
        return self
