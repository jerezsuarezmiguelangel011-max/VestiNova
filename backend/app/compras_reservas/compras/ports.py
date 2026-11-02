from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.inventario.domain import StockBalance
from app.compras_reservas.compras.domain import PurchaseContext, PurchaseItem, PurchaseLine


class PurchaseGateway(Protocol):
    """Adaptador productivo explícito; no hay empresa, cliente o stock predeterminados.

    Todos los métodos participan en la sesión recibida y nunca hacen commit.
    El contexto verifica identidad, permisos y pertenencia; las ofertas se obtienen
    del catálogo de esa empresa y resuelven variantes reales, sin inventarlas.
    Este incremento devuelve una línea por producto; no divide una selección
    entre variantes que el cliente todavía no puede elegir.
    """

    def context(self, session: Session, token: str) -> PurchaseContext: ...

    def quote(self, session: Session, context: PurchaseContext, items: tuple[PurchaseItem, ...]) -> tuple[PurchaseLine, ...]: ...

    def balances(self, session: Session, context: PurchaseContext, lines: tuple[PurchaseLine, ...]) -> tuple[StockBalance, ...]: ...

    def consume(self, session: Session, context: PurchaseContext, purchase_id: UUID, lines: tuple[PurchaseLine, ...]) -> None:
        """Revalidar/bloquear y consumir solo disponible, sin tocar compromisos ajenos.

        El descuento físico y el kardex deben confirmarse junto a la compra.
        """
        ...
