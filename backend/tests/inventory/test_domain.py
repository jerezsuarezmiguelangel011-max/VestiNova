from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from uuid import UUID, uuid4

import pytest

from app.inventory.domain import (
    AdjustmentCommand,
    BranchReference,
    IncompatibleReference,
    InvalidAdjustment,
    InvalidQuantity,
    InventoryAuthorization,
    InventoryError,
    InventoryForbidden,
    InventoryKey,
    InventoryMovement,
    InventoryPermission,
    StockBalance,
    VariantReference,
)


KEY = InventoryKey(empresa_id=1, sucursal_id=2, variante_id=3)
INVALID_IDENTIFIERS = [0, -1, True, False, 1.0, 1.5, "", " ", " empresa", "empresa ", None]
INVALID_QUANTITIES = [-1, True, False, 1.0, 1.5, "2", None, Decimal("2"), Fraction(2, 1)]


def balance(actual=10, reserved=3, key=KEY):
    return StockBalance(key=key, stock_actual=actual, stock_reservado=reserved)


def authorization(**changes):
    return InventoryAuthorization(**{
        "actor_id": "encargado-1",
        "empresa_id": KEY.empresa_id,
        "sucursales": frozenset({KEY.sucursal_id}),
        "permissions": frozenset({InventoryPermission.CONSULTAR, InventoryPermission.AJUSTAR}),
        **changes,
    })


def movement(**changes):
    return InventoryMovement(**{
        "id": uuid4(),
        "operacion_id": uuid4(),
        "key": KEY,
        "actor_id": "encargado-1",
        "ocurrido_en": datetime(2026, 10, 25, 9, 30, tzinfo=timezone(timedelta(hours=-4))),
        "motivo": "Recuento físico",
        "anterior": balance(),
        "posterior": balance(actual=12),
        **changes,
    })


def test_inventory_key_preserves_identifier_types_and_all_three_scope_dimensions():
    assert KEY != InventoryKey(empresa_id="1", sucursal_id=2, variante_id=3)
    assert KEY != InventoryKey(empresa_id=1, sucursal_id=4, variante_id=3)
    assert KEY != InventoryKey(empresa_id=1, sucursal_id=2, variante_id=4)
    assert InventoryKey("Empresa Norte", "Sucursal Centro", "SKU-003").empresa_id == "Empresa Norte"


def test_inventory_identity_and_authorization_cannot_be_mutated_after_validation():
    key = InventoryKey(empresa_id=1, sucursal_id=2, variante_id=3)
    access = authorization()
    with pytest.raises(FrozenInstanceError):
        key.empresa_id = 9
    with pytest.raises(FrozenInstanceError):
        access.sucursales = frozenset({9})
    with pytest.raises(FrozenInstanceError):
        access.permissions = frozenset()


@pytest.mark.parametrize("field", ["empresa_id", "sucursal_id", "variante_id"])
@pytest.mark.parametrize("value", INVALID_IDENTIFIERS)
def test_inventory_key_rejects_invalid_identifiers_without_coercion(field, value):
    values = {"empresa_id": 1, "sucursal_id": 2, "variante_id": 3, field: value}
    with pytest.raises(InventoryError):
        InventoryKey(**values)


@pytest.mark.parametrize("reference_type", [BranchReference, VariantReference])
def test_reference_keeps_its_company_and_identity(reference_type):
    reference = reference_type(id="referencia-1", empresa_id=1)
    assert reference.id == "referencia-1"
    assert reference.empresa_id == 1
    with pytest.raises(FrozenInstanceError):
        reference.empresa_id = 2


@pytest.mark.parametrize("reference_type", [BranchReference, VariantReference])
@pytest.mark.parametrize("field", ["id", "empresa_id"])
@pytest.mark.parametrize("value", [False, 0, " referencia", "", 1.0])
def test_reference_validates_company_and_identity(reference_type, field, value):
    with pytest.raises(InventoryError):
        reference_type(**{"id": 2, "empresa_id": 1, field: value})


@pytest.mark.parametrize("actual,reserved,available", [(0, 0, 0), (10, 0, 10), (10, 3, 7), (3, 3, 0)])
def test_stock_available_excludes_reserved_units_and_accepts_zero(actual, reserved, available):
    stock = balance(actual=actual, reserved=reserved)
    assert stock.stock_disponible == available


@pytest.mark.parametrize("field", ["stock_actual", "stock_reservado"])
@pytest.mark.parametrize("value", INVALID_QUANTITIES)
def test_stock_quantities_must_be_nonnegative_integers_without_coercion(field, value):
    with pytest.raises(InvalidQuantity):
        StockBalance(**{"key": KEY, "stock_actual": 10, "stock_reservado": 0, field: value})


def test_stock_cannot_reserve_more_units_than_exist():
    with pytest.raises(InvalidQuantity):
        balance(actual=2, reserved=3)


def test_adjustment_is_an_absolute_count_and_preserves_reservations_and_original_balance():
    previous = balance()
    adjusted = previous.adjust_to(12)
    assert adjusted is not previous
    assert adjusted.key == previous.key
    assert adjusted.stock_actual == 12
    assert adjusted.stock_reservado == 3
    assert adjusted.stock_disponible == 9
    assert previous.stock_actual == 10
    assert previous.stock_reservado == 3
    with pytest.raises(FrozenInstanceError):
        previous.stock_actual = 12


def test_adjustment_can_reduce_stock_to_reserved_units_or_zero_when_unreserved():
    assert balance().adjust_to(3).stock_disponible == 0
    zero = balance(reserved=0).adjust_to(0)
    assert zero.stock_actual == 0
    assert zero.stock_disponible == 0


@pytest.mark.parametrize("count", INVALID_QUANTITIES)
def test_adjustment_rejects_invalid_count_types_and_negative_values(count):
    with pytest.raises(InvalidQuantity):
        balance().adjust_to(count)


@pytest.mark.parametrize("count", [0, 2, 10])
def test_adjustment_rejects_counts_below_reserved_and_unchanged_counts(count):
    previous = balance()
    with pytest.raises(InvalidAdjustment):
        previous.adjust_to(count)
    assert previous.stock_actual == 10
    assert previous.stock_reservado == 3


def test_zero_count_is_not_a_movement_when_stock_is_already_zero():
    with pytest.raises(InvalidAdjustment):
        balance(actual=0, reserved=0).adjust_to(0)


@pytest.mark.parametrize("permission", list(InventoryPermission))
def test_authorization_accepts_only_granted_permissions_within_its_scope(permission):
    authorization().require(KEY, permission)


@pytest.mark.parametrize("key", [
    InventoryKey(empresa_id=9, sucursal_id=2, variante_id=3),
    InventoryKey(empresa_id="1", sucursal_id=2, variante_id=3),
    InventoryKey(empresa_id=1, sucursal_id=9, variante_id=3),
    InventoryKey(empresa_id=1, sucursal_id="2", variante_id=3),
])
@pytest.mark.parametrize("permission", list(InventoryPermission))
def test_authorization_rejects_company_or_branch_outside_granted_scope(key, permission):
    with pytest.raises(InventoryForbidden):
        authorization().require(key, permission)


def test_read_permission_does_not_authorize_adjustments():
    access = authorization(permissions=frozenset({InventoryPermission.CONSULTAR}))
    access.require(KEY, InventoryPermission.CONSULTAR)
    with pytest.raises(InventoryForbidden):
        access.require(KEY, InventoryPermission.AJUSTAR)


def test_empty_branch_or_permission_grants_do_not_authorize_access():
    for access in [authorization(sucursales=frozenset()), authorization(permissions=frozenset())]:
        with pytest.raises(InventoryForbidden):
            access.require(KEY, InventoryPermission.CONSULTAR)


@pytest.mark.parametrize("field", ["actor_id", "empresa_id"])
@pytest.mark.parametrize("value", [False, 0, "", " actor", 1.0])
def test_authorization_rejects_invalid_actor_and_company_identifiers(field, value):
    with pytest.raises(InventoryError):
        authorization(**{field: value})


def test_adjustment_command_normalizes_reason_and_creates_an_independent_operation_uuid():
    command = AdjustmentCommand(key=KEY, stock_actual_contado=0, motivo="  Recuento físico  ")
    another = AdjustmentCommand(key=KEY, stock_actual_contado=0, motivo="Recuento físico")
    assert command.stock_actual_contado == 0
    assert command.motivo == "Recuento físico"
    assert isinstance(command.operacion_id, UUID)
    assert command.operacion_id.version == 4
    assert command.operacion_id != another.operacion_id
    operation = uuid4()
    assert AdjustmentCommand(KEY, 1, "Recuento", operacion_id=operation).operacion_id == operation
    with pytest.raises(FrozenInstanceError):
        command.motivo = "Otro motivo"


@pytest.mark.parametrize("count", INVALID_QUANTITIES)
def test_adjustment_command_rejects_invalid_count(count):
    with pytest.raises(InvalidQuantity):
        AdjustmentCommand(key=KEY, stock_actual_contado=count, motivo="Recuento")


@pytest.mark.parametrize("reason", ["", " ", "\n\t", None, 123])
def test_adjustment_command_requires_a_nonblank_text_reason(reason):
    with pytest.raises(InventoryError):
        AdjustmentCommand(key=KEY, stock_actual_contado=1, motivo=reason)


def test_adjustment_command_does_not_impose_an_unspecified_reason_length_limit():
    reason = "Motivo detallado. " * 400
    command = AdjustmentCommand(key=KEY, stock_actual_contado=1, motivo=reason)
    assert command.motivo == reason.strip()


@pytest.mark.parametrize("new_count,delta", [(12, 2), (5, -5), (3, -7)])
def test_movement_records_actor_operation_scope_balances_and_exact_deltas(new_count, delta):
    operation = uuid4()
    record = movement(operacion_id=operation, posterior=balance(actual=new_count))
    assert isinstance(record.id, UUID)
    assert record.operacion_id == operation
    assert record.actor_id == "encargado-1"
    assert record.key == record.anterior.key == record.posterior.key == KEY
    assert record.delta_actual == delta
    assert record.delta_reservado == 0
    assert record.tipo == "AJUSTE_RECUENTO"
    assert record.anterior.stock_actual == 10
    assert record.posterior.stock_actual == new_count
    with pytest.raises(FrozenInstanceError):
        record.actor_id = "otro-actor"


def test_movement_normalizes_aware_datetime_to_utc_and_trims_reason():
    record = movement(motivo="  Recuento físico  ")
    assert record.ocurrido_en == datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc)
    assert record.ocurrido_en.tzinfo is timezone.utc
    assert record.motivo == "Recuento físico"


def test_movement_rejects_a_naive_datetime_instead_of_guessing_a_timezone():
    with pytest.raises(InventoryError):
        movement(ocurrido_en=datetime(2026, 10, 25, 9, 30))


@pytest.mark.parametrize("field", ["anterior", "posterior"])
def test_movement_rejects_balances_from_a_different_company_branch_or_variant(field):
    incompatible = balance(actual=12, key=InventoryKey(empresa_id=1, sucursal_id=9, variante_id=3))
    with pytest.raises(IncompatibleReference):
        movement(**{field: incompatible})


def test_movement_rejects_a_key_different_from_its_balances():
    with pytest.raises(IncompatibleReference):
        movement(key=InventoryKey(empresa_id=9, sucursal_id=2, variante_id=3))


def test_recount_movement_cannot_modify_reserved_stock():
    with pytest.raises(InvalidAdjustment):
        movement(posterior=balance(actual=12, reserved=2))


def test_recount_movement_cannot_record_an_unchanged_balance():
    with pytest.raises(InvalidAdjustment):
        movement(posterior=balance())


@pytest.mark.parametrize("reason", ["", " \n\t", None])
def test_movement_requires_a_reason_for_the_audit_trace(reason):
    with pytest.raises(InventoryError):
        movement(motivo=reason)


@pytest.mark.parametrize("field", ["id", "operacion_id"])
def test_movement_requires_uuid_identifiers(field):
    with pytest.raises(InventoryError):
        movement(**{field: "not-a-uuid"})
