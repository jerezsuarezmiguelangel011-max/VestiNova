"""Historial privado de compras del cliente autenticado."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.compras_reservas.compras.domain import Purchase
from app.compras_reservas.compras.persistence import find_purchase_for_customer, list_purchases_for_customer
from app.compras_reservas.compras.valoraciones import EntregaCompra
from app.db import get_db
from app.models import Cliente, Empresa, SesionCliente


router = APIRouter(prefix="/api/tiendas/{slug}/cuenta/compras", tags=["CU16 · Historial de compras"])


def history_item(purchase: Purchase, entrega: EntregaCompra | None = None) -> dict:
    return {
        "id": str(purchase.id),
        "estado": "CONFIRMADA",
        "seguimiento_entrega": "ENTREGADA" if entrega else "NO_DISPONIBLE",
        "entregada_en": entrega.entregada_en.isoformat() if entrega else None,
        "moneda": "BOB",
        "importe_total": f"{purchase.total:.2f}",
        "creado_en": purchase.creado_en.isoformat(),
        "sucursal_id": purchase.context.sucursal_id,
        "items": [
            {
                "producto_id": line.producto_id,
                "variante_id": line.key.variante_id,
                "nombre": line.nombre,
                "cantidad": line.cantidad,
                "precio_unitario": f"{line.precio_unitario:.2f}",
                "subtotal": f"{line.subtotal:.2f}",
            }
            for line in purchase.lines
        ],
    }


@router.get("")
def customer_purchase_history(
    response: Response,
    pagination_limit: int = Query(default=20, alias="limit", ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    purchases, total = list_purchases_for_customer(
        db, company.id, customer.id, limit=pagination_limit, offset=offset,
    )
    return {
        "items": [history_item(purchase, db.get(EntregaCompra, str(purchase.id))) for purchase in purchases],
        "total": total,
        "limit": pagination_limit,
        "offset": offset,
    }


@router.get("/{purchase_id}")
def customer_purchase_detail(
    purchase_id: UUID,
    response: Response,
    current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    customer, _, company = current
    purchase = find_purchase_for_customer(db, company.id, customer.id, purchase_id)
    if purchase is None:
        raise HTTPException(404, "No se encontró la compra en el historial de esta cuenta.")
    return history_item(purchase, db.get(EntregaCompra, str(purchase.id)))
