from types import TracebackType
from typing import Protocol

from app.inventory.domain import (
    BranchReference, Identifier, InventoryAuthorization, InventoryKey,
    InventoryMovement, StockBalance, VariantReference,
)


class InventoryAuthorizer(Protocol):
    def authorize(self, actor_id: Identifier, empresa_id: Identifier) -> InventoryAuthorization:
        """Resolver identidad y permisos reales; nunca confiar en un contexto del cliente."""
        ...


class InventoryReferenceResolver(Protocol):
    def get_branch(self, identifier: Identifier) -> BranchReference | None: ...

    def get_variant(self, identifier: Identifier) -> VariantReference | None: ...


class InventoryRepository(Protocol):
    def get(self, key: InventoryKey) -> StockBalance | None: ...

    def save(self, balance: StockBalance) -> None:
        """Preparar el saldo sin confirmar una transacción independiente."""
        ...

    def append_movement(self, movement: InventoryMovement) -> None:
        """Preparar un movimiento nuevo; no editar ni eliminar la traza anterior."""
        ...


class InventoryUnitOfWork(Protocol):
    repository: InventoryRepository

    def __enter__(self) -> "InventoryUnitOfWork": ...

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        """Revertir lo preparado si no se completó commit; nunca suprimir errores."""
        ...

    def commit(self) -> None:
        """Confirmar saldo y movimiento juntos, o fallar sin persistir ninguno."""
        ...
