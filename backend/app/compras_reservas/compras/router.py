from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.db import get_db
from app.compras_reservas.compras.domain import (
    Purchase, PurchaseCommand, PurchaseConflict, PurchaseForbidden, PurchaseInvalid,
    PurchaseItem, PurchaseUnavailable,
)
from app.compras_reservas.compras.service import PurchaseNotFound, PurchaseService, PurchaseUnauthenticated


router = APIRouter(prefix="/api/compras", tags=["CU09: compras digitales"])
bearer = HTTPBearer(auto_error=False)


class ItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producto_id: StrictInt = Field(gt=0)
    cantidad: StrictInt = Field(gt=0, le=2147483647)


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    items: list[ItemRequest] = Field(min_length=1)


def receipt(purchase: Purchase) -> dict:
    return {
        "id": str(purchase.id), "estado": "CONFIRMADA", "moneda": "BOB",
        "total": f"{purchase.total:.2f}", "creado_en": purchase.creado_en.isoformat(),
        "items": [{"producto_id": line.producto_id, "nombre": line.nombre, "cantidad": line.cantidad,
                   "precio_unitario": f"{line.precio_unitario:.2f}", "subtotal": f"{line.subtotal:.2f}"} for line in purchase.lines],
    }


def service(request: Request) -> PurchaseService:
    return PurchaseService(getattr(request.app.state, "purchase_gateway", None))


def invoke(action):
    try:
        return receipt(action())
    except PurchaseUnauthenticated as error:
        raise HTTPException(401, str(error), headers={"Cache-Control": "no-store"}) from None
    except PurchaseForbidden as error:
        raise HTTPException(403, str(error), headers={"Cache-Control": "no-store"}) from None
    except PurchaseNotFound as error:
        raise HTTPException(404, str(error), headers={"Cache-Control": "no-store"}) from None
    except PurchaseConflict as error:
        raise HTTPException(409, str(error), headers={"Cache-Control": "no-store"}) from None
    except PurchaseInvalid as error:
        raise HTTPException(422, str(error), headers={"Cache-Control": "no-store"}) from None
    except PurchaseUnavailable as error:
        raise HTTPException(503, str(error), headers={"Cache-Control": "no-store"}) from None


@router.get("/capacidades")
def capabilities(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    enabled = getattr(request.app.state, "purchase_gateway", None) is not None
    return {"habilitado": enabled, "detail": "Compras disponibles con autorización e inventario verificados." if enabled else "La confirmación de compras todavía no está disponible. Puedes seguir preparando tu selección."}


@router.post("", status_code=201)
def confirm(payload: PurchaseRequest, request: Request, response: Response, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    response.headers["Cache-Control"] = "no-store"
    return invoke(lambda: service(request).confirm(db, credentials.credentials if credentials else None,
                                                 PurchaseCommand(payload.id, tuple(PurchaseItem(item.producto_id, item.cantidad) for item in payload.items))))


@router.get("/{purchase_id}")
def detail(purchase_id: UUID, request: Request, response: Response, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    response.headers["Cache-Control"] = "no-store"
    return invoke(lambda: service(request).get(db, credentials.credentials if credentials else None, purchase_id))
