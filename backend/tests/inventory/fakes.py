"""Adaptadores en memoria exclusivos de pruebas, sin base de datos ni garantías de concurrencia."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType

from app.inventory.domain import (
    BranchReference,
    Identifier,
    InventoryAuthorization,
    InventoryForbidden,
    InventoryKey,
    InventoryMovement,
    StockBalance,
    VariantReference,
)


@dataclass
class InventoryTestState:
    balances: dict[InventoryKey, StockBalance] = field(default_factory=dict)
    movements: list[InventoryMovement] = field(default_factory=list)


class FakeAuthorizer:
    def __init__(self, authorization: InventoryAuthorization | None):
        self.authorization = authorization
        self.calls: list[tuple[Identifier, Identifier]] = []

    def authorize(self, actor_id: Identifier, empresa_id: Identifier) -> InventoryAuthorization:
        self.calls.append((actor_id, empresa_id))
        if self.authorization is None:
            raise InventoryForbidden("No existe una autorización de prueba.")
        # La prueba puede devolver un contexto incompatible para comprobar que el servicio lo rechace.
        return self.authorization


class FakeReferenceResolver:
    def __init__(self, branches: dict[Identifier, BranchReference], variants: dict[Identifier, VariantReference]):
        self.branches = branches
        self.variants = variants
        self.branch_calls: list[Identifier] = []
        self.variant_calls: list[Identifier] = []

    def get_branch(self, branch_id: Identifier) -> BranchReference | None:
        self.branch_calls.append(branch_id)
        return self.branches.get(branch_id)

    def get_variant(self, variant_id: Identifier) -> VariantReference | None:
        self.variant_calls.append(variant_id)
        return self.variants.get(variant_id)


class FakeInventoryRepository:
    def __init__(self, state: InventoryTestState, *, fail_append: bool = False):
        self.balances = deepcopy(state.balances)
        self.movements = deepcopy(state.movements)
        self.fail_append = fail_append
        self.get_calls: list[InventoryKey] = []
        self.save_calls: list[StockBalance] = []
        self.append_calls: list[InventoryMovement] = []

    def get(self, key: InventoryKey) -> StockBalance | None:
        self.get_calls.append(key)
        return deepcopy(self.balances.get(key))

    def save(self, balance: StockBalance) -> None:
        self.save_calls.append(deepcopy(balance))
        self.balances[balance.key] = deepcopy(balance)

    def append_movement(self, movement: InventoryMovement) -> None:
        self.append_calls.append(deepcopy(movement))
        self.movements.append(deepcopy(movement))
        if self.fail_append:
            raise RuntimeError("Fallo simulado al agregar el movimiento.")


class FakeInventoryUnitOfWork:
    def __init__(self, state: InventoryTestState, *, fail_append: bool = False, fail_commit: bool = False):
        self.state = state
        self.fail_append = fail_append
        self.fail_commit = fail_commit
        self.repository = FakeInventoryRepository(state, fail_append=fail_append)
        self.entered = False
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.commit_calls = 0

    def __enter__(self) -> FakeInventoryUnitOfWork:
        if self.entered:
            raise RuntimeError("La unidad de trabajo de prueba no se puede reutilizar.")
        self.entered = True
        self.repository = FakeInventoryRepository(self.state, fail_append=self.fail_append)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.closed = True
        if not self.committed:
            self.rolled_back = True
            self.repository.balances = deepcopy(self.state.balances)
            self.repository.movements = deepcopy(self.state.movements)
        return None

    def commit(self) -> None:
        if not self.entered or self.closed or self.committed:
            raise RuntimeError("Commit fuera de una unidad de trabajo activa.")
        self.commit_calls += 1
        if self.fail_commit:
            raise RuntimeError("Fallo simulado al confirmar la unidad de trabajo.")
        balances = deepcopy(self.repository.balances)
        movements = deepcopy(self.repository.movements)
        self.state.balances, self.state.movements = balances, movements
        self.committed = True


class FakeUnitOfWorkFactory:
    def __init__(self, state: InventoryTestState):
        self.state = state
        self.fail_append = False
        self.fail_commit = False
        self.instances: list[FakeInventoryUnitOfWork] = []

    def __call__(self) -> FakeInventoryUnitOfWork:
        unit = FakeInventoryUnitOfWork(self.state, fail_append=self.fail_append, fail_commit=self.fail_commit)
        self.instances.append(unit)
        return unit
