from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.db import Base, build_session_factory
from app.inventario.domain import InventoryKey
from app.compras_reservas.compras.domain import (
    Purchase, PurchaseCommand, PurchaseContext, PurchaseItem, PurchaseLine,
    PurchaseUnavailable, identifier_token,
)
from app.compras_reservas.compras.persistence import PurchaseLineRecord, PurchaseRecord, add_purchase, find_purchase


CONTEXT = PurchaseContext(actor_id="actor-1", empresa_id=1, cliente_id="cliente-1", sucursal_id=10)
NOW = datetime(2026, 10, 25, 20, 30, tzinfo=timezone.utc)


def purchase(context=CONTEXT, *, id=None):
    identifier = id or uuid4()
    lines = (
        PurchaseLine(InventoryKey(context.empresa_id, context.sucursal_id, "variante-A"), 7, "Camisa de lino", 2, Decimal("149.90")),
        PurchaseLine(InventoryKey(context.empresa_id, context.sucursal_id, 456), 9, "Falda de algodón", 3, Decimal("59.95")),
    )
    command = PurchaseCommand(identifier, tuple(PurchaseItem(line.producto_id, line.cantidad) for line in lines))
    return Purchase(identifier, context, command.fingerprint, lines, NOW)


@pytest.fixture
def purchase_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield build_session_factory(engine)
    engine.dispose()


def test_purchase_and_ordered_price_snapshots_persist_between_sessions(purchase_factory):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    with purchase_factory() as session:
        restored = find_purchase(session, CONTEXT, original.id)
        assert restored == original
        assert restored.total == Decimal("479.65")
        assert restored.lines[0].precio_unitario == Decimal("149.90")
        assert restored.lines[0].key.variante_id == "variante-A"
        assert restored.lines[1].key.variante_id == 456
        assert type(restored.lines[1].key.variante_id) is int
        assert restored.creado_en.utcoffset().total_seconds() == 0
        header = session.get(PurchaseRecord, str(original.id))
        assert header.moneda == "BOB"
        assert header.contexto == {
            "actor_id": CONTEXT.actor_id, "empresa_id": CONTEXT.empresa_id,
            "cliente_id": CONTEXT.cliente_id, "sucursal_id": CONTEXT.sucursal_id,
        }


def test_add_does_not_commit_and_rollback_removes_both_header_and_lines(purchase_factory):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.flush()
        assert session.scalar(select(func.count()).select_from(PurchaseLineRecord)) == 2
        session.rollback()
    with purchase_factory() as session:
        assert find_purchase(session, CONTEXT, original.id) is None
        assert session.scalar(select(func.count()).select_from(PurchaseRecord)) == 0
        assert session.scalar(select(func.count()).select_from(PurchaseLineRecord)) == 0


@pytest.mark.parametrize("changes", [{"empresa_id": 2}, {"cliente_id": "otro-cliente"}, {"sucursal_id": 20}])
def test_find_never_returns_purchase_outside_authorized_company_customer_branch(purchase_factory, changes):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    with purchase_factory() as session:
        assert find_purchase(session, replace(CONTEXT, **changes), original.id) is None


@pytest.mark.parametrize("field", ["empresa_id", "cliente_id", "sucursal_id"])
def test_identifier_tokens_preserve_integer_and_string_scope_identity(purchase_factory, field):
    context = PurchaseContext(50, 1, 2, 3)
    original = purchase(context)
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    other = replace(context, **{field: str(getattr(context, field))})
    with purchase_factory() as session:
        assert find_purchase(session, context, original.id) == original
        assert find_purchase(session, other, original.id) is None


def test_uuid_is_globally_unique_and_collision_cannot_overwrite_another_company(purchase_factory):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    other = purchase(replace(CONTEXT, empresa_id=2), id=original.id)
    with purchase_factory() as session:
        add_purchase(session, other)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    with purchase_factory() as session:
        assert find_purchase(session, CONTEXT, original.id) == original
        assert find_purchase(session, other.context, original.id) is None
        assert session.scalar(select(func.count()).select_from(PurchaseLineRecord)) == 2


def test_composite_foreign_key_blocks_a_line_attached_to_another_company(purchase_factory):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    with purchase_factory() as session:
        session.add(PurchaseLineRecord(
            compra_id=str(original.id), posicion=2, empresa_clave=identifier_token(2), producto_id=99,
            variante_ref="variante-ajena", nombre="No debe guardarse", cantidad=1, precio_unitario=Decimal("10.00"),
        ))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    with purchase_factory() as session:
        assert find_purchase(session, CONTEXT, original.id) == original


@pytest.mark.parametrize("changes", [
    {"cantidad": 0}, {"cantidad": -1}, {"precio_unitario": Decimal("0.00")},
    {"precio_unitario": Decimal("100000000.00")}, {"nombre": "   "}, {"producto_id": 0},
])
def test_database_rejects_invalid_snapshot_line_without_changing_purchase(purchase_factory, changes):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
    fields = {
        "compra_id": str(original.id), "posicion": 2, "empresa_clave": identifier_token(CONTEXT.empresa_id),
        "producto_id": 99, "variante_ref": "otra-variante", "nombre": "Prenda", "cantidad": 1,
        "precio_unitario": Decimal("10.00"),
    }
    with purchase_factory() as session:
        session.add(PurchaseLineRecord(**(fields | changes)))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    with purchase_factory() as session:
        assert find_purchase(session, CONTEXT, original.id) == original


@pytest.mark.parametrize("changes", [
    {"total": Decimal("1.00")}, {"huella": "0" * 64},
    {"contexto": {"actor_id": CONTEXT.actor_id, "empresa_id": 2, "cliente_id": CONTEXT.cliente_id, "sucursal_id": CONTEXT.sucursal_id}},
])
def test_incoherent_stored_total_fingerprint_or_context_is_not_returned_as_confirmed(purchase_factory, changes):
    original = purchase()
    with purchase_factory() as session:
        add_purchase(session, original)
        session.commit()
        session.execute(update(PurchaseRecord).where(PurchaseRecord.id == str(original.id)).values(**changes))
        session.commit()
    with purchase_factory() as session:
        with pytest.raises(PurchaseUnavailable):
            find_purchase(session, CONTEXT, original.id)
