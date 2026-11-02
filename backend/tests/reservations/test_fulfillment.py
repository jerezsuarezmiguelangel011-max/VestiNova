from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.inventario.domain import InventoryKey
from app.compras_reservas.reservas.domain import (
    InvalidTransition, Reservation, ReservationForbidden,
    ReservationLine, ReservationRequest, ReservationState,
)
from app.compras_reservas.reservas.retiro import HandoverContext, prepare_handover


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def sample():
    key = InventoryKey(empresa_id=1, sucursal_id=3, variante_id=9)
    request = ReservationRequest(
        id=uuid4(), empresa_id=1, cliente_id=5, sucursal_id=3,
        lineas=(ReservationLine(key, 2),), solicitado_en=NOW - timedelta(minutes=3),
    )
    reservation = Reservation.confirmed(
        request, actor_id=4, codigo="VN-CODE-123",
        at=NOW - timedelta(minutes=2), expires_at=NOW + timedelta(hours=1),
    )
    staff = HandoverContext(actor_id=4, empresa_id=1, sucursales=frozenset({3}), rol="CAJERO")
    return reservation, staff


def test_preview_only_verifies_confirmed_reservation_without_mutating_it():
    reservation, staff = sample()
    original = reservation
    check = prepare_handover(reservation, staff, "VN-CODE-123", NOW)
    assert check.reserva_id == reservation.id
    assert check.items == ((9, 2),)
    assert check.estado == "LISTA_PARA_VERIFICACION_FISICA"
    assert reservation is original
    assert reservation.estado is ReservationState.CONFIRMADA
    assert len(reservation.eventos) == 1


@pytest.mark.parametrize("context", [
    HandoverContext(4, 2, frozenset({3}), "CAJERO"),
    HandoverContext(4, 1, frozenset({999}), "CAJERO"),
    HandoverContext(4, 1, frozenset({3}), "OPERADOR"),
])
def test_preview_rejects_wrong_company_branch_or_role(context):
    reservation, _ = sample()
    with pytest.raises(ReservationForbidden):
        prepare_handover(reservation, context, "VN-CODE-123", NOW)


def test_preview_rejects_wrong_code_expired_or_nonconfirmed_request():
    reservation, staff = sample()
    with pytest.raises(ReservationForbidden):
        prepare_handover(reservation, staff, "incorrecto", NOW)
    with pytest.raises(InvalidTransition):
        prepare_handover(reservation, staff, reservation.codigo, reservation.vence_en)
    with pytest.raises(InvalidTransition):
        prepare_handover(replace(reservation, estado=ReservationState.CANCELADA), staff, reservation.codigo, NOW)
