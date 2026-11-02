from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.inventory.domain import (
    AdjustmentCommand,
    BranchReference,
    IncompatibleReference,
    InventoryAuthorization,
    InventoryError,
    InventoryForbidden,
    InventoryKey,
    InventoryNotFound,
    InventoryPermission,
    InvalidAdjustment,
    StockBalance,
    VariantReference,
)
from app.inventory.service import InventoryService
from tests.inventory.fakes import FakeAuthorizer, FakeReferenceResolver, FakeUnitOfWorkFactory, InventoryTestState


ACTOR = 50
KEY = InventoryKey(empresa_id=1, sucursal_id=10, variante_id=100)
OTHER_KEY = InventoryKey(empresa_id=2, sucursal_id=20, variante_id=200)
NOW = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
MOVEMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
OPERATION_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def inventory():
    balance = StockBalance(key=KEY, stock_actual=10, stock_reservado=3)
    other = StockBalance(key=OTHER_KEY, stock_actual=90, stock_reservado=4)
    state = InventoryTestState(balances={KEY: balance, OTHER_KEY: other})
    grant = InventoryAuthorization(
        actor_id=ACTOR,
        empresa_id=KEY.empresa_id,
        sucursales=frozenset({KEY.sucursal_id}),
        permissions=frozenset({InventoryPermission.CONSULTAR, InventoryPermission.AJUSTAR}),
    )
    authorizer = FakeAuthorizer(grant)
    references = FakeReferenceResolver(
        {KEY.sucursal_id: BranchReference(id=KEY.sucursal_id, empresa_id=KEY.empresa_id)},
        {KEY.variante_id: VariantReference(id=KEY.variante_id, empresa_id=KEY.empresa_id)},
    )
    factory = FakeUnitOfWorkFactory(state)
    service = InventoryService(
        authorizer, references, factory, clock=lambda: NOW, movement_id_factory=lambda: MOVEMENT_ID,
    )
    return SimpleNamespace(
        balance=balance, other=other, state=state, grant=grant, authorizer=authorizer,
        references=references, factory=factory, service=service,
    )


def adjustment(counted=13):
    return AdjustmentCommand(
        key=KEY, stock_actual_contado=counted, motivo="Recuento físico autorizado", operacion_id=OPERATION_ID,
    )


def invoke(inventory, operation):
    if operation == "consultar":
        return inventory.service.get_balance(ACTOR, KEY)
    return inventory.service.adjust(ACTOR, adjustment())


@pytest.mark.parametrize("operation", ["consultar", "ajustar"])
def test_missing_authorization_does_not_open_unit_of_work(inventory, operation):
    inventory.authorizer.authorization = None
    with pytest.raises(InventoryForbidden):
        invoke(inventory, operation)
    assert inventory.factory.instances == []
    assert inventory.state.balances[KEY] == inventory.balance
    assert inventory.state.movements == []


@pytest.mark.parametrize("operation", ["consultar", "ajustar"])
@pytest.mark.parametrize("changes", [
    {"actor_id": "otro-actor"},
    {"empresa_id": "otra-empresa"},
    {"sucursales": frozenset({999})},
])
def test_rejects_forged_or_out_of_scope_authorization_before_storage(inventory, operation, changes):
    inventory.authorizer.authorization = replace(inventory.grant, **changes)
    with pytest.raises(InventoryForbidden):
        invoke(inventory, operation)
    assert inventory.authorizer.calls == [(ACTOR, KEY.empresa_id)]
    assert inventory.factory.instances == []


@pytest.mark.parametrize("operation,granted", [
    ("consultar", InventoryPermission.AJUSTAR),
    ("ajustar", InventoryPermission.CONSULTAR),
])
def test_consult_and_adjust_permissions_are_independent(inventory, operation, granted):
    inventory.authorizer.authorization = replace(inventory.grant, permissions=frozenset({granted}))
    with pytest.raises(InventoryForbidden):
        invoke(inventory, operation)
    assert inventory.factory.instances == []


@pytest.mark.parametrize("operation", ["consultar", "ajustar"])
@pytest.mark.parametrize("missing", ["branch", "variant"])
def test_missing_reference_is_not_inventory_zero_and_does_not_open_storage(inventory, operation, missing):
    if missing == "branch":
        inventory.references.branches.clear()
    else:
        inventory.references.variants.clear()
    with pytest.raises(InventoryNotFound):
        invoke(inventory, operation)
    assert inventory.factory.instances == []
    assert inventory.state.balances[KEY] == inventory.balance


@pytest.mark.parametrize("reference", [
    BranchReference(id=999, empresa_id=KEY.empresa_id),
    BranchReference(id=KEY.sucursal_id, empresa_id=OTHER_KEY.empresa_id),
    VariantReference(id=999, empresa_id=KEY.empresa_id),
    VariantReference(id=KEY.variante_id, empresa_id=OTHER_KEY.empresa_id),
])
def test_reference_resolver_cannot_cross_tenants_or_return_another_identity(inventory, reference):
    if isinstance(reference, BranchReference):
        inventory.references.branches[KEY.sucursal_id] = reference
    else:
        inventory.references.variants[KEY.variante_id] = reference
    with pytest.raises(IncompatibleReference):
        inventory.service.adjust(ACTOR, adjustment())
    assert inventory.factory.instances == []
    assert inventory.state.movements == []


def test_get_balance_reads_without_writes_commit_or_movements(inventory):
    before = deepcopy(inventory.state)
    balance = inventory.service.get_balance(ACTOR, KEY)
    assert balance == inventory.balance
    assert balance.stock_actual == 10
    assert balance.stock_reservado == 3
    assert balance.stock_disponible == 7
    assert inventory.authorizer.calls == [(ACTOR, KEY.empresa_id)]
    assert inventory.references.branch_calls == [KEY.sucursal_id]
    assert inventory.references.variant_calls == [KEY.variante_id]
    assert len(inventory.factory.instances) == 1
    unit = inventory.factory.instances[0]
    assert unit.repository.get_calls == [KEY]
    assert unit.repository.save_calls == []
    assert unit.repository.append_calls == []
    assert unit.commit_calls == 0
    assert unit.closed
    assert inventory.state == before


@pytest.mark.parametrize("operation", ["consultar", "ajustar"])
def test_absent_balance_is_not_implicitly_created_with_zero(inventory, operation):
    del inventory.state.balances[KEY]
    before = deepcopy(inventory.state)
    with pytest.raises(InventoryNotFound):
        invoke(inventory, operation)
    assert inventory.state == before
    unit = inventory.factory.instances[0]
    assert unit.repository.save_calls == []
    assert unit.repository.append_calls == []
    assert unit.commit_calls == 0
    assert unit.closed


@pytest.mark.parametrize("operation", ["consultar", "ajustar"])
def test_repository_cannot_substitute_balance_from_another_key(inventory, operation):
    inventory.state.balances[KEY] = inventory.other
    before = deepcopy(inventory.state)
    with pytest.raises(IncompatibleReference):
        invoke(inventory, operation)
    assert inventory.state == before
    unit = inventory.factory.instances[0]
    assert unit.commit_calls == 0
    assert unit.repository.save_calls == []
    assert unit.repository.append_calls == []


@pytest.mark.parametrize("counted,delta,available", [(13, 3, 10), (6, -4, 3), (3, -7, 0)])
def test_adjust_absolute_count_preserves_reserved_and_commits_complete_trace(inventory, counted, delta, available):
    command = adjustment(counted)
    movement = inventory.service.adjust(ACTOR, command)
    assert movement.id == MOVEMENT_ID
    assert movement.operacion_id == OPERATION_ID
    assert movement.key == KEY
    assert movement.actor_id == ACTOR
    assert movement.ocurrido_en == NOW
    assert movement.ocurrido_en.tzinfo is not None
    assert movement.ocurrido_en.utcoffset().total_seconds() == 0
    assert movement.motivo == command.motivo
    assert movement.tipo == "AJUSTE_RECUENTO"
    assert movement.anterior == inventory.balance
    assert movement.posterior.stock_actual == counted
    assert movement.posterior.stock_reservado == 3
    assert movement.posterior.stock_disponible == available
    assert movement.delta_actual == delta
    assert movement.delta_reservado == 0
    assert inventory.state.balances[KEY] == movement.posterior
    assert inventory.state.balances[OTHER_KEY] == inventory.other
    assert inventory.state.movements == [movement]
    assert inventory.balance.stock_actual == 10
    assert len(inventory.factory.instances) == 1
    unit = inventory.factory.instances[0]
    assert unit.repository.save_calls == [movement.posterior]
    assert unit.repository.append_calls == [movement]
    assert unit.commit_calls == 1
    assert unit.committed and unit.closed


def test_adjust_rejects_no_op_without_creating_kardex_entry(inventory):
    before = deepcopy(inventory.state)
    with pytest.raises(InvalidAdjustment):
        inventory.service.adjust(ACTOR, adjustment(10))
    assert inventory.state == before
    unit = inventory.factory.instances[0]
    assert unit.repository.save_calls == []
    assert unit.repository.append_calls == []
    assert unit.commit_calls == 0
    assert unit.rolled_back


def test_count_below_reserved_is_rejected_without_clamping_or_changing_reserved(inventory):
    before = deepcopy(inventory.state)
    with pytest.raises(InventoryError):
        inventory.service.adjust(ACTOR, adjustment(2))
    assert inventory.state == before
    assert inventory.state.balances[KEY].stock_reservado == 3
    unit = inventory.factory.instances[0]
    assert unit.repository.save_calls == []
    assert unit.repository.append_calls == []
    assert unit.commit_calls == 0


@pytest.mark.parametrize("failure", ["append", "commit"])
def test_adjust_failure_rolls_back_both_balance_and_movement(inventory, failure):
    before = deepcopy(inventory.state)
    if failure == "append":
        inventory.factory.fail_append = True
    else:
        inventory.factory.fail_commit = True
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        inventory.service.adjust(ACTOR, adjustment())
    assert inventory.state == before
    unit = inventory.factory.instances[0]
    assert len(unit.repository.save_calls) == 1
    assert len(unit.repository.append_calls) == 1
    assert unit.commit_calls == (0 if failure == "append" else 1)
    assert not unit.committed
    assert unit.closed and unit.rolled_back
    assert unit.repository.balances == before.balances
    assert unit.repository.movements == before.movements
