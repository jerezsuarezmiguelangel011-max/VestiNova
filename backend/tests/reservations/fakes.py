"""Doubles exclusivos de pruebas, sin tablas maestras ni persistencia productiva.

El RLock simula una unidad de trabajo serializada, no demuestra bloqueos PostgreSQL.
Los saldos CU08 son la única fuente de cantidades; la reserva no contiene otra copia.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from types import TracebackType
from uuid import UUID

from app.inventory.domain import BranchReference, Identifier, InventoryKey, StockBalance, VariantReference
from app.reservations.domain import (
    CustomerReference, InsufficientStock, InvalidReservation, Reservation,
    ReservationAuthorization, ReservationConflict, ReservationForbidden,
    ReservationLine, ReservationNotFound, ReservationRequest,
)


@dataclass
class ReservationTestState:
    reservations: dict[UUID, Reservation] = field(default_factory=dict)
    balances: dict[InventoryKey, StockBalance] = field(default_factory=dict)
    commitments: dict[UUID, tuple[ReservationLine, ...]] = field(default_factory=dict)


class FakeAuthorizer:
    def __init__(self, authorization: ReservationAuthorization | None):
        self.authorization = authorization
        self.error: Exception | None = None
        self.calls: list[tuple[Identifier, Identifier]] = []

    def authorize(self, actor_id: Identifier, empresa_id: Identifier) -> ReservationAuthorization:
        self.calls.append((actor_id, empresa_id))
        if self.error is not None:
            raise self.error
        if self.authorization is None:
            raise ReservationForbidden("No existe una autorización de prueba.")
        return self.authorization


class FakeReferences:
    def __init__(
        self, branches: dict[Identifier, BranchReference], variants: dict[Identifier, VariantReference],
        customers: dict[tuple[Identifier, Identifier], CustomerReference],
    ):
        self.branches, self.variants, self.customers = branches, variants, customers
        self.branch_calls: list[Identifier] = []
        self.variant_calls: list[Identifier] = []
        self.customer_calls: list[tuple[Identifier, Identifier]] = []

    def get_branch(self, identifier: Identifier) -> BranchReference | None:
        self.branch_calls.append(identifier)
        return self.branches.get(identifier)

    def get_variant(self, identifier: Identifier) -> VariantReference | None:
        self.variant_calls.append(identifier)
        return self.variants.get(identifier)

    def get_customer(self, cliente_id: Identifier, empresa_id: Identifier) -> CustomerReference | None:
        self.customer_calls.append((cliente_id, empresa_id))
        return self.customers.get((empresa_id, cliente_id))


class FakePolicy:
    def __init__(self, duration: timedelta | None):
        # Cada prueba proporciona su configuración; no existe plazo predeterminado.
        self.duration = duration
        self.cancellation_error: Exception | None = None
        self.cancellation_result: object = None
        self.expiry_calls: list[tuple[ReservationRequest, datetime]] = []
        self.cancel_calls: list[tuple[Reservation, datetime]] = []

    def expires_at(self, request: ReservationRequest, confirmed_at: datetime) -> datetime:
        self.expiry_calls.append((request, confirmed_at))
        if self.duration is None:
            raise InvalidReservation("La política de prueba no tiene vencimiento configurado.")
        return confirmed_at + self.duration

    def ensure_cancelable(self, reservation: Reservation, at: datetime) -> None:
        self.cancel_calls.append((reservation, at))
        if self.cancellation_error is not None:
            raise self.cancellation_error
        return self.cancellation_result


class FakeReservationRepository:
    def __init__(self, unit: FakeUnitOfWork):
        self.unit = unit
        self.get_calls: list[tuple[Identifier, UUID]] = []
        self.add_calls: list[Reservation] = []
        self.save_calls: list[Reservation] = []

    def get(self, empresa_id: Identifier, reservation_id: UUID) -> Reservation | None:
        self.get_calls.append((empresa_id, reservation_id))
        override = (empresa_id, reservation_id)
        if override in self.unit.factory.reservation_reads:
            return deepcopy(self.unit.factory.reservation_reads[override])
        reservation = self.unit.staged.reservations.get(reservation_id)
        if reservation is None or reservation.request.empresa_id != empresa_id:
            return None
        return deepcopy(reservation)

    def _unique_code(self, reservation: Reservation) -> None:
        if any(item.id != reservation.id and item.codigo == reservation.codigo
               for item in self.unit.staged.reservations.values()):
            raise ReservationConflict("El código ya pertenece a otra reserva.")

    def add(self, reservation: Reservation) -> None:
        self.add_calls.append(reservation)
        if reservation.id in self.unit.staged.reservations:
            raise ReservationConflict("El UUID ya existe, incluso en otra empresa.")
        self._unique_code(reservation)
        self.unit.staged.reservations[reservation.id] = deepcopy(reservation)
        if self.unit.factory.fail_add:
            raise RuntimeError("Fallo simulado al agregar la reserva.")

    def save(self, reservation: Reservation) -> None:
        self.save_calls.append(reservation)
        previous = self.unit.staged.reservations.get(reservation.id)
        if previous is None or previous.request.empresa_id != reservation.request.empresa_id:
            raise ReservationNotFound("No existe una reserva en el ámbito solicitado.")
        self._unique_code(reservation)
        self.unit.staged.reservations[reservation.id] = deepcopy(reservation)
        if self.unit.factory.fail_save:
            raise RuntimeError("Fallo simulado al actualizar la reserva.")


class FakeReservationInventory:
    def __init__(self, unit: FakeUnitOfWork):
        self.unit = unit
        self.get_calls: list[InventoryKey] = []
        self.hold_calls: list[tuple[UUID, tuple[ReservationLine, ...]]] = []
        self.release_calls: list[UUID] = []
        self.held_keys: list[InventoryKey] = []

    def get(self, key: InventoryKey) -> StockBalance | None:
        self.get_calls.append(key)
        if key in self.unit.factory.inventory_reads:
            return deepcopy(self.unit.factory.inventory_reads[key])
        return deepcopy(self.unit.staged.balances.get(key))

    def hold(self, reservation_id: UUID, lines: tuple[ReservationLine, ...]) -> None:
        self.hold_calls.append((reservation_id, lines))
        if reservation_id in self.unit.staged.commitments:
            raise ReservationConflict("La reserva ya tiene un compromiso propio.")
        for line in lines:
            # Leer el saldo autoritativo otra vez; get puede haber devuelto una lectura optimista obsoleta.
            balance = self.unit.staged.balances.get(line.key)
            if balance is None:
                raise ReservationNotFound("No existe inventario conocido.")
            if balance.stock_disponible < line.cantidad:
                raise InsufficientStock("La disponibilidad cambió antes de comprometer las unidades.")
            self.unit.staged.balances[line.key] = StockBalance(
                line.key, balance.stock_actual, balance.stock_reservado + line.cantidad,
            )
            self.held_keys.append(line.key)
        self.unit.staged.commitments[reservation_id] = deepcopy(lines)
        if self.unit.factory.fail_hold:
            raise RuntimeError("Fallo simulado al comprometer inventario.")

    def release(self, reservation_id: UUID) -> None:
        self.release_calls.append(reservation_id)
        lines = self.unit.staged.commitments.pop(reservation_id, None)
        if lines is None:
            raise ReservationConflict("No existe un compromiso propio pendiente de liberar.")
        for line in lines:
            balance = self.unit.staged.balances[line.key]
            if balance.stock_reservado < line.cantidad:
                raise ReservationConflict("El compromiso no coincide con el saldo reservado.")
            self.unit.staged.balances[line.key] = StockBalance(
                line.key, balance.stock_actual, balance.stock_reservado - line.cantidad,
            )
        if self.unit.factory.fail_release:
            raise RuntimeError("Fallo simulado al liberar inventario.")


class FakeUnitOfWork:
    repository: FakeReservationRepository
    inventory: FakeReservationInventory

    def __init__(self, factory: FakeUnitOfWorkFactory):
        self.factory = factory
        self.entered = False
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.commit_calls = 0

    def __enter__(self) -> FakeUnitOfWork:
        if self.entered:
            raise RuntimeError("La unidad de trabajo de prueba no se reutiliza.")
        self.factory.lock.acquire()
        try:
            # Clonar DESPUÉS del lock: la segunda solicitud ve el compromiso confirmado por la primera.
            self.staged = deepcopy(self.factory.state)
            self.repository = FakeReservationRepository(self)
            self.inventory = FakeReservationInventory(self)
            self.entered = True
            return self
        except BaseException:
            self.factory.lock.release()
            raise

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.closed = True
            if not self.committed:
                self.rolled_back = True
                self.staged = deepcopy(self.factory.state)
        finally:
            self.factory.lock.release()

    def commit(self) -> None:
        if not self.entered or self.closed or self.committed:
            raise RuntimeError("Commit fuera de una unidad de trabajo activa.")
        self.commit_calls += 1
        if self.factory.fail_commit:
            raise RuntimeError("Fallo simulado al confirmar la unidad de trabajo.")
        snapshot = deepcopy(self.staged)
        source = self.factory.state
        source.reservations, source.balances, source.commitments = (
            snapshot.reservations, snapshot.balances, snapshot.commitments,
        )
        self.committed = True


class FakeUnitOfWorkFactory:
    def __init__(self, state: ReservationTestState):
        self.state = state
        self.lock = RLock()
        self.fail_add = False
        self.fail_save = False
        self.fail_hold = False
        self.fail_release = False
        self.fail_commit = False
        self.inventory_reads: dict[InventoryKey, StockBalance | None] = {}
        self.reservation_reads: dict[tuple[Identifier, UUID], Reservation | None] = {}
        self.instances: list[FakeUnitOfWork] = []

    def __call__(self) -> FakeUnitOfWork:
        unit = FakeUnitOfWork(self)
        self.instances.append(unit)
        return unit
