from collections import defaultdict
from decimal import Decimal
import json
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.inventory.domain import InventoryKey, StockBalance
from app.purchases.domain import (
    PurchaseConflict, PurchaseContext, PurchaseForbidden, PurchaseLine, PurchaseUnavailable,
)
from app.purchases.persistence import PurchaseLineRecord, PurchaseRecord
from app.purchases.service import PurchaseUnauthenticated
import app.purchases.service as purchase_service


CONTEXT = PurchaseContext('actor-a', 'empresa-a', 'cliente-a', 'sucursal-a')
OFFERS = {
    7: ('Camisa de lino', Decimal('149.90'), 'variante-lino-natural'),
    8: ('Pañuelo verde', Decimal('20.05'), 'variante-panuelo-verde'),
}
TOKEN = {'Authorization': 'Bearer cliente-prueba'}


class GatewayTestBase(DeclarativeBase):
    """Tablas exclusivas de pruebas; no forman parte del esquema de la aplicación."""


class FakeStock(GatewayTestBase):
    __tablename__ = 'test_purchase_gateway_stock'

    key: Mapped[str] = mapped_column(String(500), primary_key=True)
    actual: Mapped[int] = mapped_column(Integer)
    reservado: Mapped[int] = mapped_column(Integer)


class FakeConsumption(GatewayTestBase):
    __tablename__ = 'test_purchase_gateway_consumption'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[str] = mapped_column(String(36))
    key: Mapped[str] = mapped_column(String(500))
    cantidad: Mapped[int] = mapped_column(Integer)


def stock_key(key: InventoryKey) -> str:
    return json.dumps((key.empresa_id, key.sucursal_id, key.variante_id), separators=(',', ':'))


def offer_key(context: PurchaseContext, variant: str) -> InventoryKey:
    return InventoryKey(context.empresa_id, context.sucursal_id, variant)


class FakeGateway:
    """Autorización, ofertas y stock controlados únicamente por esta batería."""

    def __init__(self):
        self.contexts = {
            'cliente-prueba': CONTEXT,
            'otra-empresa': PurchaseContext('actor-b', 'empresa-b', 'cliente-b', 'sucursal-b'),
            'otro-cliente': PurchaseContext('actor-a', 'empresa-a', 'cliente-b', 'sucursal-a'),
            'otra-sucursal': PurchaseContext('actor-a', 'empresa-a', 'cliente-a', 'sucursal-b'),
            'otro-actor': PurchaseContext('actor-b', 'empresa-a', 'cliente-a', 'sucursal-a'),
        }
        self.offers = dict(OFFERS)
        self.sessions = []
        self.quote_calls = 0
        self.consume_calls = 0
        self.fail_after_consume = False

    def context(self, session: Session, token: str) -> PurchaseContext:
        self.sessions.append(id(session))
        if token == 'sin-permiso':
            raise PurchaseForbidden('No tienes permiso para comprar en este contexto.')
        if token not in self.contexts:
            raise PurchaseUnauthenticated('La sesión de cliente no es válida.')
        return self.contexts[token]

    def quote(self, session, context, items):
        self.sessions.append(id(session))
        self.quote_calls += 1
        return tuple(
            PurchaseLine(offer_key(context, self.offers[item.producto_id][2]), item.producto_id,
                         self.offers[item.producto_id][0], item.cantidad, self.offers[item.producto_id][1])
            for item in items
        )

    def balances(self, session, context, lines):
        self.sessions.append(id(session))
        balances = []
        for key in dict.fromkeys(line.key for line in lines):
            row = session.get(FakeStock, stock_key(key))
            if row is not None:
                balances.append(StockBalance(key, row.actual, row.reservado))
        return tuple(balances)

    def consume(self, session, context, purchase_id, lines):
        self.sessions.append(id(session))
        self.consume_calls += 1
        wanted = defaultdict(int)
        for line in lines:
            wanted[line.key] += line.cantidad
        for key, quantity in wanted.items():
            row = session.get(FakeStock, stock_key(key))
            if row is None:
                raise PurchaseUnavailable('No hay inventario verificado.')
            if row.actual - row.reservado < quantity:
                raise PurchaseConflict('No hay disponibilidad suficiente.')
            row.actual -= quantity
            session.add(FakeConsumption(purchase_id=str(purchase_id), key=stock_key(key), cantidad=quantity))
        session.flush()
        if self.fail_after_consume:
            raise SQLAlchemyError('Fallo interno simulado después de consumir stock.')


@pytest.fixture
def gateway(app, engine, session_factory):
    GatewayTestBase.metadata.create_all(engine)
    gateway = FakeGateway()
    with session_factory() as session:
        for _, _, variant in OFFERS.values():
            session.add(FakeStock(key=stock_key(offer_key(CONTEXT, variant)), actual=10, reservado=3))
        session.commit()
    app.state.purchase_gateway = gateway
    return gateway


def payload(*, purchase_id=None, quantity=2):
    return {'id': str(purchase_id or uuid4()), 'items': [{'producto_id': 7, 'cantidad': quantity}]}


def counts(session_factory):
    with session_factory() as session:
        return (
            session.scalar(select(func.count()).select_from(PurchaseRecord)),
            session.scalar(select(func.count()).select_from(PurchaseLineRecord)),
        )


def stock(session_factory, variant='variante-lino-natural'):
    with session_factory() as session:
        row = session.get(FakeStock, stock_key(offer_key(CONTEXT, variant)))
        return row.actual, row.reservado


def test_unconfigured_capability_rejects_before_any_sql_and_creates_no_purchase(client, engine, session_factory):
    statements = []

    def record_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', record_sql)
    try:
        assert client.get('/api/compras/capacidades').json()['habilitado'] is False
        body = payload()
        assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 503
        assert client.post('/api/compras', json=body).status_code == 503
        assert client.get(f"/api/compras/{body['id']}", headers=TOKEN).status_code == 503
        assert statements == []
    finally:
        event.remove(engine, 'before_cursor_execute', record_sql)
    assert counts(session_factory) == (0, 0)


@pytest.mark.parametrize(('field', 'value'), [
    ('producto_id', True), ('producto_id', 0), ('producto_id', -1), ('producto_id', '7'), ('producto_id', 7.5),
    ('cantidad', True), ('cantidad', 0), ('cantidad', -1), ('cantidad', '2'), ('cantidad', 1.5),
    ('cantidad', 2147483648),
])
def test_payload_requires_strict_positive_integer_items(client, gateway, session_factory, field, value):
    body = payload()
    body['items'][0][field] = value
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 422
    assert gateway.quote_calls == gateway.consume_calls == 0
    assert counts(session_factory) == (0, 0)


@pytest.mark.parametrize(('field', 'value'), [
    ('empresa_id', 'empresa-inyectada'), ('cliente_id', 'cliente-inyectado'),
    ('sucursal_id', 'sucursal-inyectada'), ('total', '0.01'), ('moneda', 'USD'),
])
def test_payload_cannot_supply_context_or_totals(client, gateway, session_factory, field, value):
    body = {**payload(), field: value}
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 422
    assert counts(session_factory) == (0, 0)


def test_payload_cannot_supply_unit_prices(client, gateway, session_factory):
    body = payload()
    body['items'][0]['precio_unitario'] = '0.01'
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 422
    assert gateway.consume_calls == 0
    assert counts(session_factory) == (0, 0)


@pytest.mark.parametrize(('headers', 'status'), [
    ({}, 401), ({'Authorization': 'Basic credencial-no-bearer'}, 401),
    ({'Authorization': 'Bearer desconocido'}, 401), ({'Authorization': 'Bearer sin-permiso'}, 403),
])
def test_enabled_purchase_requires_authorized_client_context(client, gateway, session_factory, headers, status):
    assert client.post('/api/compras', json=payload(), headers=headers).status_code == status
    assert gateway.consume_calls == 0
    assert counts(session_factory) == (0, 0)


def test_confirms_server_priced_snapshot_and_reads_it_without_requoting(client, gateway, session_factory):
    body = payload()
    body['items'].append({'producto_id': 8, 'cantidad': 1})
    assert client.get('/api/compras/capacidades').json()['habilitado'] is True
    response = client.post('/api/compras', json=body, headers=TOKEN)
    assert response.status_code == 201
    receipt = response.json()
    assert receipt['id'] == body['id']
    assert receipt['estado'] == 'CONFIRMADA'
    assert receipt['total'] == '319.85'
    assert receipt['moneda'] == 'BOB'
    assert receipt.get('pagada') is not True
    assert receipt['items'] == [
        {'producto_id': 7, 'nombre': 'Camisa de lino', 'cantidad': 2, 'precio_unitario': '149.90', 'subtotal': '299.80'},
        {'producto_id': 8, 'nombre': 'Pañuelo verde', 'cantidad': 1, 'precio_unitario': '20.05', 'subtotal': '20.05'},
    ]
    assert len(set(gateway.sessions)) == 1
    assert counts(session_factory) == (1, 2)
    assert stock(session_factory) == (8, 3)
    gateway.offers[7] = ('Nombre posterior', Decimal('900.00'), 'variante-lino-natural')
    retrieved = client.get(f"/api/compras/{body['id']}", headers=TOKEN)
    assert retrieved.status_code == 200
    assert retrieved.json() == receipt
    assert gateway.quote_calls == gateway.consume_calls == 1


def test_insufficient_available_stock_is_conflict_without_purchase_or_consumption(client, gateway, session_factory):
    assert client.post('/api/compras', json=payload(quantity=8), headers=TOKEN).status_code == 409
    assert counts(session_factory) == (0, 0)
    assert stock(session_factory) == (10, 3)
    assert gateway.consume_calls == 0


def test_repeated_product_lines_do_not_bypass_available_stock(client, gateway, session_factory):
    body = payload(quantity=4)
    body['items'].append({'producto_id': 7, 'cantidad': 4})
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 409
    assert counts(session_factory) == (0, 0)
    assert stock(session_factory) == (10, 3)


def test_missing_inventory_is_unavailable_instead_of_inventing_stock(client, gateway, session_factory):
    with session_factory() as session:
        session.delete(session.get(FakeStock, stock_key(offer_key(CONTEXT, 'variante-lino-natural'))))
        session.commit()
    assert client.post('/api/compras', json=payload(), headers=TOKEN).status_code == 503
    assert counts(session_factory) == (0, 0)
    assert gateway.consume_calls == 0


def test_same_uuid_returns_original_receipt_without_consuming_again(client, gateway, session_factory):
    body = payload()
    first = client.post('/api/compras', json=body, headers=TOKEN)
    gateway.offers[7] = ('Precio posterior', Decimal('300.00'), 'variante-lino-natural')
    repeated = client.post('/api/compras', json=body, headers=TOKEN)
    assert first.status_code == repeated.status_code == 201
    assert first.json() == repeated.json()
    assert counts(session_factory) == (1, 1)
    assert gateway.quote_calls == gateway.consume_calls == 1
    assert stock(session_factory) == (8, 3)


def test_same_uuid_with_different_selection_is_conflict(client, gateway, session_factory):
    body = payload()
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 201
    body['items'][0]['cantidad'] = 3
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 409
    assert counts(session_factory) == (1, 1)
    assert stock(session_factory) == (8, 3)
    assert gateway.consume_calls == 1


@pytest.mark.parametrize('other_token', ['otra-empresa', 'otro-cliente', 'otra-sucursal', 'otro-actor'])
def test_receipt_is_not_readable_from_a_different_context(client, gateway, session_factory, other_token):
    body = payload()
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 201
    response = client.get(f"/api/compras/{body['id']}", headers={'Authorization': f'Bearer {other_token}'})
    assert response.status_code == 404
    assert 'Camisa de lino' not in response.text
    assert '149.90' not in response.text
    assert counts(session_factory) == (1, 1)


def test_gateway_sql_failure_rolls_back_consumption_and_purchase(client, gateway, session_factory):
    gateway.fail_after_consume = True
    response = client.post('/api/compras', json=payload(), headers=TOKEN)
    assert response.status_code == 503
    assert 'Fallo interno simulado' not in response.text
    assert counts(session_factory) == (0, 0)
    assert stock(session_factory) == (10, 3)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FakeConsumption)) == 0


def test_failure_after_purchase_write_rolls_back_stock_and_receipt(client, gateway, session_factory, monkeypatch):
    original_add = purchase_service.add_purchase

    def fail_after_write(session, purchase):
        original_add(session, purchase)
        session.flush()
        raise SQLAlchemyError('Fallo simulado después de escribir la compra.')

    monkeypatch.setattr(purchase_service, 'add_purchase', fail_after_write)
    response = client.post('/api/compras', json=payload(), headers=TOKEN)
    assert response.status_code == 503
    assert counts(session_factory) == (0, 0)
    assert stock(session_factory) == (10, 3)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FakeConsumption)) == 0


def miss_first_purchase_lookup(monkeypatch):
    """Simular la lectura inicial anterior al commit ganador, sin hilos SQLite."""
    original_find = purchase_service.find_purchase
    calls = 0

    def find_after_winner(session, context, purchase_id):
        nonlocal calls
        calls += 1
        return None if calls == 1 else original_find(session, context, purchase_id)

    monkeypatch.setattr(purchase_service, 'find_purchase', find_after_winner)


def test_duplicate_race_returns_winner_when_stock_is_exhausted_before_balance_read(client, gateway, session_factory, monkeypatch):
    body = payload(quantity=7)
    winner = client.post('/api/compras', json=body, headers=TOKEN)
    assert winner.status_code == 201
    assert stock(session_factory) == (3, 3)
    miss_first_purchase_lookup(monkeypatch)

    repeated = client.post('/api/compras', json=body, headers=TOKEN)

    assert repeated.status_code == 201
    assert repeated.json() == winner.json()
    assert gateway.quote_calls == 2
    assert gateway.consume_calls == 1
    assert counts(session_factory) == (1, 1)
    assert stock(session_factory) == (3, 3)


def test_duplicate_race_rolls_back_tentative_consumption_before_returning_winner(client, gateway, session_factory, monkeypatch):
    body = payload(quantity=2)
    winner = client.post('/api/compras', json=body, headers=TOKEN)
    assert winner.status_code == 201
    miss_first_purchase_lookup(monkeypatch)
    original_consume = gateway.consume

    def consume_then_detect_winner(session, context, purchase_id, lines):
        original_consume(session, context, purchase_id, lines)
        raise PurchaseConflict('El consumo concurrente detectó una operación ya confirmada.')

    monkeypatch.setattr(gateway, 'consume', consume_then_detect_winner)
    repeated = client.post('/api/compras', json=body, headers=TOKEN)

    assert repeated.status_code == 201
    assert repeated.json() == winner.json()
    assert gateway.consume_calls == 2
    assert counts(session_factory) == (1, 1)
    assert stock(session_factory) == (8, 3)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FakeConsumption)) == 1


def test_conflict_recovery_does_not_return_receipt_for_a_different_selection(client, gateway, session_factory, monkeypatch):
    body = payload(quantity=1)
    assert client.post('/api/compras', json=body, headers=TOKEN).status_code == 201
    miss_first_purchase_lookup(monkeypatch)
    body['items'][0]['cantidad'] = 7

    response = client.post('/api/compras', json=body, headers=TOKEN)

    assert response.status_code == 409
    assert response.json()['detail'] == 'No hay disponibilidad suficiente para completar la compra.'
    assert counts(session_factory) == (1, 1)
    assert stock(session_factory) == (9, 3)
    assert gateway.consume_calls == 1


@pytest.mark.parametrize(('error_type', 'status'), [(PurchaseUnauthenticated, 401), (PurchaseForbidden, 403)])
def test_conflict_recovery_reauthorizes_and_propagates_access_denial(client, gateway, session_factory, monkeypatch, error_type, status):
    original_context = gateway.context
    calls = 0

    def reject_reauthorization(session, token):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise error_type('El acceso cambió durante la operación.')
        return original_context(session, token)

    monkeypatch.setattr(gateway, 'context', reject_reauthorization)
    response = client.post('/api/compras', json=payload(quantity=8), headers=TOKEN)

    assert response.status_code == status
    assert response.json()['detail'] == 'El acceso cambió durante la operación.'
    assert calls == 2
    assert counts(session_factory) == (0, 0)
    assert stock(session_factory) == (10, 3)
