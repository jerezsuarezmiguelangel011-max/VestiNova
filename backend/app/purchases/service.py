from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.inventory.domain import StockBalance
from app.purchases.domain import (
    Purchase, PurchaseCommand, PurchaseConflict, PurchaseContext, PurchaseForbidden,
    PurchaseInvalid, PurchaseUnavailable,
)
from app.purchases.persistence import add_purchase, find_purchase
from app.purchases.ports import PurchaseGateway


class PurchaseUnauthenticated(PurchaseForbidden):
    pass


class PurchaseNotFound(Exception):
    pass


class PurchaseService:
    def __init__(self, gateway: PurchaseGateway | None):
        self.gateway = gateway

    def context(self, session: Session, token: str | None) -> PurchaseContext:
        if self.gateway is None:
            raise PurchaseUnavailable("Compras pendientes de integración: faltan autorización de cliente, empresa, sucursal y disponibilidad reales.")
        if not token or not token.strip():
            raise PurchaseUnauthenticated("Se requiere una sesión de cliente autorizada.")
        context = self.gateway.context(session, token)
        if not isinstance(context, PurchaseContext):
            raise PurchaseForbidden("No se pudo verificar el contexto de compra.")
        return context

    @staticmethod
    def _same(purchase: Purchase, context: PurchaseContext, command: PurchaseCommand) -> Purchase:
        if purchase.context != context or purchase.fingerprint != command.fingerprint:
            raise PurchaseConflict("El identificador ya corresponde a otra solicitud de compra.")
        return purchase

    def confirm(self, session: Session, token: str | None, command: PurchaseCommand) -> Purchase:
        try:
            context = self.context(session, token)
            existing = find_purchase(session, context, command.id)
            if existing:
                return self._same(existing, context, command)
            lines = self.gateway.quote(session, context, command.items)
            if not isinstance(lines, tuple):
                raise PurchaseUnavailable("El catálogo autorizado no devolvió una oferta válida.")
            purchase = Purchase(command.id, context, command.fingerprint, lines, datetime.now(timezone.utc))
            balances = self.gateway.balances(session, context, lines)
            wanted = defaultdict(int)
            for line in lines:
                wanted[line.key] += line.cantidad
            known = {}
            for balance in balances:
                if not isinstance(balance, StockBalance) or balance.key not in wanted or balance.key in known:
                    raise PurchaseUnavailable("No se pudo verificar la disponibilidad real.")
                known[balance.key] = balance
            if set(known) != set(wanted):
                raise PurchaseUnavailable("Hay prendas sin información de inventario verificada.")
            if any(known[key].stock_disponible < quantity for key, quantity in wanted.items()):
                raise PurchaseConflict("No hay disponibilidad suficiente para completar la compra.")
            self.gateway.consume(session, context, command.id, lines)
            add_purchase(session, purchase)
            session.commit()
            return purchase
        except PurchaseConflict:
            # Otro reenvío puede haber confirmado este UUID mientras se comprobaba
            # o consumía disponibilidad. Revertir el intento antes de leer al ganador.
            session.rollback()
            context = self.context(session, token)
            existing = find_purchase(session, context, command.id)
            if existing is not None and existing.context == context and existing.fingerprint == command.fingerprint:
                return self._same(existing, context, command)
            raise
        except IntegrityError:
            # El consumo debe pertenecer a esta misma transacción: también se revierte.
            session.rollback()
            context = self.context(session, token)
            existing = find_purchase(session, context, command.id)
            if existing:
                return self._same(existing, context, command)
            raise PurchaseConflict("No se pudo registrar la compra por un conflicto concurrente.") from None
        except BaseException:
            session.rollback()
            raise

    def get(self, session: Session, token: str | None, purchase_id: UUID) -> Purchase:
        context = self.context(session, token)
        purchase = find_purchase(session, context, purchase_id)
        if purchase is None or purchase.context != context:
            raise PurchaseNotFound("No se encontró la compra en el contexto autorizado.")
        return purchase
