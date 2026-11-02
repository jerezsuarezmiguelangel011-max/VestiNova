from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.inventario.domain import IncompatibleReference, InventoryKey
from app.compras_reservas.compras.domain import (
    Purchase, PurchaseCommand, PurchaseContext, PurchaseForbidden, PurchaseInvalid,
    PurchaseItem, PurchaseLine, identifier_token,
)


CONTEXT = PurchaseContext('actor-a', 'empresa-a', 'cliente-a', 'sucursal-a')
KEY = InventoryKey('empresa-a', 'sucursal-a', 'variante-lino-natural')
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('product', [True, False, 0, -1, 7.0, '7', None])
def test_product_reference_is_a_strict_positive_integer(product):
    with pytest.raises(PurchaseInvalid):
        PurchaseItem(product, 1)


@pytest.mark.parametrize('quantity', [True, False, 0, -1, 1.5, '1', None, 2147483648])
def test_quantity_is_a_strict_positive_bounded_integer(quantity):
    with pytest.raises(PurchaseInvalid):
        PurchaseItem(7, quantity)


def test_command_combines_repeated_items_and_fingerprints_equivalent_selections():
    purchase_id = uuid4()
    duplicated = PurchaseCommand(purchase_id, (PurchaseItem(8, 1), PurchaseItem(7, 1), PurchaseItem(7, 2)))
    canonical = PurchaseCommand(purchase_id, (PurchaseItem(7, 3), PurchaseItem(8, 1)))
    changed = PurchaseCommand(purchase_id, (PurchaseItem(7, 2), PurchaseItem(8, 1)))
    assert duplicated.items == canonical.items
    assert duplicated.fingerprint == canonical.fingerprint
    assert changed.fingerprint != canonical.fingerprint
    with pytest.raises(FrozenInstanceError):
        canonical.items = ()


@pytest.mark.parametrize('items', [(), [], (object(),)])
def test_command_requires_nonempty_immutable_items(items):
    with pytest.raises(PurchaseInvalid):
        PurchaseCommand(uuid4(), items)


def test_merged_quantities_must_still_fit_the_quantity_contract():
    with pytest.raises(PurchaseInvalid):
        PurchaseCommand(uuid4(), (PurchaseItem(7, 2147483647), PurchaseItem(7, 1)))


@pytest.mark.parametrize('price', [
    Decimal('0'), Decimal('-1'), Decimal('10.001'), Decimal('100000000.00'),
    Decimal('NaN'), Decimal('Infinity'), 149.9, '149.90', True,
])
def test_server_price_requires_a_finite_positive_decimal_with_cent_precision(price):
    with pytest.raises(PurchaseInvalid):
        PurchaseLine(KEY, 7, 'Camisa de lino', 1, price)


def test_receipt_totals_keep_decimal_precision_and_normalize_aware_dates_to_utc():
    command = PurchaseCommand(uuid4(), (PurchaseItem(7, 3),))
    line = PurchaseLine(KEY, 7, 'Camisa de lino', 3, Decimal('149.90'))
    local_time = datetime(2026, 10, 25, 8, tzinfo=timezone(timedelta(hours=-4)))
    purchase = Purchase(command.id, CONTEXT, command.fingerprint, (line,), local_time)
    assert line.subtotal == Decimal('449.70')
    assert purchase.total == Decimal('449.70')
    assert purchase.creado_en == NOW
    assert purchase.creado_en.utcoffset() == timedelta(0)
    with pytest.raises(FrozenInstanceError):
        purchase.lines = ()


@pytest.mark.parametrize('key', [
    InventoryKey('otra-empresa', 'sucursal-a', 'variante-lino-natural'),
    InventoryKey('empresa-a', 'otra-sucursal', 'variante-lino-natural'),
])
def test_quote_lines_cannot_cross_the_authorized_company_or_branch(key):
    command = PurchaseCommand(uuid4(), (PurchaseItem(7, 1),))
    with pytest.raises(PurchaseForbidden):
        Purchase(command.id, CONTEXT, command.fingerprint, (PurchaseLine(key, 7, 'Camisa', 1, Decimal('10.00')),), NOW)


def test_quote_cannot_change_the_requested_quantities():
    command = PurchaseCommand(uuid4(), (PurchaseItem(7, 2),))
    with pytest.raises(PurchaseInvalid):
        Purchase(command.id, CONTEXT, command.fingerprint, (PurchaseLine(KEY, 7, 'Camisa', 1, Decimal('10.00')),), NOW)


def test_quote_cannot_split_a_product_into_ambiguous_receipt_lines():
    command = PurchaseCommand(uuid4(), (PurchaseItem(7, 2),))
    line = PurchaseLine(KEY, 7, 'Camisa', 1, Decimal('10.00'))
    with pytest.raises(PurchaseInvalid):
        Purchase(command.id, CONTEXT, command.fingerprint, (line, line), NOW)


def test_receipt_requires_an_aware_date():
    command = PurchaseCommand(uuid4(), (PurchaseItem(7, 1),))
    line = PurchaseLine(KEY, 7, 'Camisa', 1, Decimal('10.00'))
    with pytest.raises(PurchaseInvalid):
        Purchase(command.id, CONTEXT, command.fingerprint, (line,), datetime(2026, 10, 25, 12))


def test_context_references_do_not_coerce_booleans_or_identifier_types():
    with pytest.raises(IncompatibleReference):
        PurchaseContext(True, 'empresa-a', 'cliente-a', 'sucursal-a')
    assert identifier_token(1) != identifier_token('1')
