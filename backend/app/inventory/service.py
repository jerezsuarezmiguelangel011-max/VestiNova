from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.inventory.domain import (
    AdjustmentCommand, BranchReference, Identifier, IncompatibleReference,
    InventoryAuthorization, InventoryForbidden, InventoryKey, InventoryMovement,
    InventoryNotFound, InventoryPermission, StockBalance, VariantReference,
    validate_identifier,
)
from app.inventory.ports import (
    InventoryAuthorizer, InventoryReferenceResolver, InventoryUnitOfWork,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InventoryService:
    def __init__(
        self, authorizer: InventoryAuthorizer, references: InventoryReferenceResolver,
        uow_factory: Callable[[], InventoryUnitOfWork], *,
        clock: Callable[[], datetime] = _utc_now,
        movement_id_factory: Callable[[], UUID] = uuid4,
    ):
        self._authorizer = authorizer
        self._references = references
        self._uow_factory = uow_factory
        self._clock = clock
        self._movement_id_factory = movement_id_factory

    def get_balance(self, actor_id: Identifier, key: InventoryKey) -> StockBalance:
        self._authorize(actor_id, key, InventoryPermission.CONSULTAR)
        self._validate_references(key)
        with self._uow_factory() as work:
            return self._get_balance(work, key)

    def adjust(self, actor_id: Identifier, command: AdjustmentCommand) -> InventoryMovement:
        if not isinstance(command, AdjustmentCommand):
            raise IncompatibleReference("El comando de ajuste no es válido.")
        authorization = self._authorize(actor_id, command.key, InventoryPermission.AJUSTAR)
        self._validate_references(command.key)
        with self._uow_factory() as work:
            previous = self._get_balance(work, command.key)
            updated = previous.adjust_to(command.stock_actual_contado)
            movement = InventoryMovement(
                id=self._movement_id_factory(), operacion_id=command.operacion_id,
                key=command.key, actor_id=authorization.actor_id, ocurrido_en=self._clock(),
                motivo=command.motivo, anterior=previous, posterior=updated,
            )
            work.repository.save(updated)
            work.repository.append_movement(movement)
            work.commit()
            return movement

    def _authorize(
        self, actor_id: Identifier, key: InventoryKey, permission: InventoryPermission,
    ) -> InventoryAuthorization:
        validate_identifier(actor_id)
        if not isinstance(key, InventoryKey):
            raise IncompatibleReference("La clave de inventario no es válida.")
        authorization = self._authorizer.authorize(actor_id, key.empresa_id)
        if not isinstance(authorization, InventoryAuthorization) or authorization.actor_id != actor_id:
            raise InventoryForbidden("El contexto autorizado no corresponde al actor.")
        authorization.require(key, permission)
        return authorization

    def _validate_references(self, key: InventoryKey) -> None:
        branch = self._references.get_branch(key.sucursal_id)
        if branch is None:
            raise InventoryNotFound("No se encontró la sucursal de inventario.")
        if not isinstance(branch, BranchReference) or branch.id != key.sucursal_id or branch.empresa_id != key.empresa_id:
            raise IncompatibleReference("La sucursal no corresponde a la empresa indicada.")
        variant = self._references.get_variant(key.variante_id)
        if variant is None:
            raise InventoryNotFound("No se encontró la variante de inventario.")
        if not isinstance(variant, VariantReference) or variant.id != key.variante_id or variant.empresa_id != key.empresa_id:
            raise IncompatibleReference("La variante no corresponde a la empresa indicada.")

    @staticmethod
    def _get_balance(work: InventoryUnitOfWork, key: InventoryKey) -> StockBalance:
        balance = work.repository.get(key)
        if balance is None:
            raise InventoryNotFound("No existe información de inventario para esta sucursal y variante.")
        if not isinstance(balance, StockBalance) or balance.key != key:
            raise IncompatibleReference("El saldo no corresponde a la clave de inventario solicitada.")
        return balance
