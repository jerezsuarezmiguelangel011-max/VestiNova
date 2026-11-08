"""CU24: comparación pública, actual y aislada por tienda; solo lectura."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo_abastecimiento.promotions import active_promotions_for_products, promotional_price
from app.catalogo_publico.catalogo import selected_company
from app.db import get_db
from app.models import Empresa, Existencia, Producto, Sucursal, VarianteProducto, utc_now
from app.schemas import ProductoResponse


router = APIRouter(prefix="/api/catalogo", tags=["CU24 · Comparar prendas"])


class ComparacionSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tienda: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    producto_ids: list[StrictInt] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def validar_ids(self):
        if any(item <= 0 for item in self.producto_ids) or len(set(self.producto_ids)) != len(self.producto_ids):
            raise ValueError("Selecciona entre dos y cuatro prendas diferentes.")
        return self


@router.post("/comparar")
def comparar_prendas(
    solicitud: ComparacionSolicitud,
    response: Response,
    db: Session = Depends(get_db),
):
    """El servidor revalida publicación, precios y existencias; la selección no reserva stock."""
    response.headers["Cache-Control"] = "no-store"
    empresa_id = selected_company(db, solicitud.tienda)
    if empresa_id is None:
        raise HTTPException(404, "Tienda no disponible.")
    productos = db.scalars(
        select(Producto).join(Empresa, Empresa.id == Producto.empresa_id).where(
            Producto.empresa_id == empresa_id,
            Producto.id.in_(solicitud.producto_ids),
            Producto.activo.is_(True),
            Empresa.activo.is_(True),
        )
    ).all()
    if len(productos) != len(solicitud.producto_ids):
        # No identificar cuál de los IDs pertenece a otra empresa o no está publicado.
        raise HTTPException(409, "La selección contiene prendas no disponibles en esta tienda.")
    por_id = {item.id: item for item in productos}
    variantes = db.scalars(
        select(VarianteProducto).where(
            VarianteProducto.empresa_id == empresa_id,
            VarianteProducto.producto_id.in_(solicitud.producto_ids),
            VarianteProducto.activo.is_(True),
        ).order_by(VarianteProducto.id)
    ).all()
    sucursales = db.scalars(
        select(Sucursal).where(
            Sucursal.empresa_id == empresa_id,
            Sucursal.activo.is_(True),
        ).order_by(Sucursal.nombre, Sucursal.id)
    ).all()
    saldos = {
        (saldo.sucursal_id, saldo.variante_id): saldo
        for saldo in db.scalars(
            select(Existencia).where(
                Existencia.empresa_id == empresa_id,
                Existencia.variante_id.in_([item.id for item in variantes]),
                Existencia.sucursal_id.in_([item.id for item in sucursales]),
            )
        ).all()
    } if sucursales and variantes else {}
    promociones = active_promotions_for_products(db, productos)
    disponibles = {}
    for variante in variantes:
        disponibles.setdefault(variante.producto_id, []).append({
            "id": variante.id,
            "talla": variante.talla,
            "color": variante.color,
            "sucursales": [
                {
                    "sucursal_id": sucursal.id,
                    "sucursal": sucursal.nombre,
                    "estado": (
                        "NO_VERIFICADO" if (sucursal.id, variante.id) not in saldos
                        else "DISPONIBLE" if saldos[(sucursal.id, variante.id)].cantidad >
                            saldos[(sucursal.id, variante.id)].cantidad_comprometida
                        else "AGOTADO"
                    ),
                    "actualizado_en": saldos[(sucursal.id, variante.id)].actualizado_en.isoformat()
                        if (sucursal.id, variante.id) in saldos else None,
                } for sucursal in sucursales
            ],
        })
    resultado = []
    for producto_id in solicitud.producto_ids:
        producto = por_id[producto_id]
        ficha = ProductoResponse.model_validate(producto)
        promocion = promociones.get(producto.id)
        if promocion is not None:
            ficha = ficha.model_copy(update={
                "precio_promocional": promotional_price(producto.precio, promocion),
                "promocion_nombre": promocion.nombre,
            })
        resultado.append({
            **ficha.model_dump(mode="json"),
            "variantes": disponibles.get(producto_id, []),
        })
    return {
        "tienda": solicitud.tienda,
        "consultado_en": utc_now().isoformat(),
        "alcance": "DISPONIBILIDAD_REFERENCIAL",
        "items": resultado,
    }
