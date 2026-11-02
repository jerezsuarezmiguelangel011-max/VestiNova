from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from uuid import UUID, uuid4

import pytest

from app.inventory.domain import InventoryKey
from app.reservations.domain import (
    InvalidReservation,
    InvalidTransition,
    Reservation,
    ReservationAuthorization,
    ReservationEvent,
    ReservationForbidden,
    ReservationLine,
    ReservationPermission,
    ReservationRequest,
    ReservationState,
)


KEY = InventoryKey(empresa_id=1, sucursal_id=2, variante_id="variante-3")
REQUESTED_AT = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
CONFIRMED_AT = REQUESTED_AT + timedelta(minutes=5)
EXPIRES_AT = CONFIRMED_AT + timedelta(minutes=37, seconds=17)


def request(**changes):
    return ReservationRequest(**{
        "id": uuid4(), "empresa_id": 1, "cliente_id": "cliente-1", "sucursal_id": 2,
        "lineas": (ReservationLine(KEY, 2),), "solicitado_en": REQUESTED_AT,
        **changes,
    })


def confirmed(**changes):
    return Reservation.confirmed(**{
        "request": request(), "actor_id": "actor-7", "codigo": " RES-001 ",
        "at": CONFIRMED_AT, "expires_at": EXPIRES_AT, **changes,
    })


def authorization(**changes):
    return ReservationAuthorization(**{
        "actor_id": "actor-7", "empresa_id": 1,
        "sucursales": frozenset({2}),
        "permissions": frozenset(ReservationPermission),
        "clientes_permitidos": frozenset({"cliente-1"}), **changes,
    })


def in_state(state):
    if state is ReservationState.PENDIENTE_SINCRONIZACION:
        return Reservation.pending(request())
    if state in {ReservationState.RECHAZADA, ReservationState.EN_CONFLICTO}:
        return Reservation.pending(request()).reject("sincronizador", CONFIRMED_AT, state, "Solicitud no confirmada")
    original = confirmed()
    if state is ReservationState.CANCELADA:
        return original.cancel("actor-7", CONFIRMED_AT + timedelta(minutes=1))
    if state is ReservationState.VENCIDA:
        return original.expire("scheduler", EXPIRES_AT)
    return replace(original, estado=state)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.0, 1.5, Fraction(1, 2)])
def test_line_requires_strictly_positive_integer_quantities(quantity):
    with pytest.raises(InvalidReservation):
        ReservationLine(KEY, quantity)


def test_request_consolidates_duplicate_variants_before_stock_is_checked():
    another = InventoryKey(1, 2, "variante-4")
    reservation_request = request(lineas=(
        ReservationLine(KEY, 2), ReservationLine(another, 1), ReservationLine(KEY, 3),
    ))
    assert {line.key: line.cantidad for line in reservation_request.lineas} == {KEY: 5, another: 1}
    assert len(reservation_request.lineas) == 2
    assert all(isinstance(line.key, InventoryKey) for line in reservation_request.lineas)


@pytest.mark.parametrize("incompatible", [InventoryKey(9, 2, 3), InventoryKey(1, 9, 3)])
def test_request_cannot_mix_company_or_branch_in_its_lines(incompatible):
    with pytest.raises(InvalidReservation):
        request(lineas=(ReservationLine(KEY, 1), ReservationLine(incompatible, 1)))


def test_request_requires_nonempty_immutable_lines():
    for lines in [(), [ReservationLine(KEY, 1)]]:
        with pytest.raises(InvalidReservation):
            request(lineas=lines)


def test_same_content_compares_the_consolidated_request_independently_of_line_order():
    another = InventoryKey(1, 2, "variante-4")
    original = request(lineas=(ReservationLine(KEY, 2), ReservationLine(another, 1), ReservationLine(KEY, 3)))
    reordered = replace(original, lineas=(ReservationLine(another, 1), ReservationLine(KEY, 5)))
    assert original.same_content(reordered)
    assert not original.same_content(replace(original, cliente_id="cliente-2"))
    assert not original.same_content(replace(original, lineas=(ReservationLine(KEY, 6),)))


@pytest.mark.parametrize("from_pending", [False, True])
def test_confirmation_records_online_or_pending_origin_without_mutating_the_request(from_pending):
    reservation_request = request()
    pending = Reservation.pending(reservation_request)
    reservation = confirmed(request=reservation_request, from_pending=from_pending)
    assert reservation.id == reservation_request.id
    assert reservation.estado is ReservationState.CONFIRMADA
    assert reservation.codigo == "RES-001"
    assert reservation.confirmada_en == CONFIRMED_AT
    assert reservation.vence_en == EXPIRES_AT
    assert reservation.eventos[0].anterior is (ReservationState.PENDIENTE_SINCRONIZACION if from_pending else None)
    assert reservation.eventos[0].posterior is ReservationState.CONFIRMADA
    assert reservation.eventos[0].actor_id == "actor-7"
    assert pending.estado is ReservationState.PENDIENTE_SINCRONIZACION
    assert pending.codigo is pending.confirmada_en is pending.vence_en is None


@pytest.mark.parametrize("duration", [timedelta(seconds=41), timedelta(days=3, minutes=7)])
def test_expiry_uses_the_configured_deadline_without_a_fixed_duration_policy(duration):
    reservation = confirmed(expires_at=CONFIRMED_AT + duration)
    assert reservation.vence_en == CONFIRMED_AT + duration


def test_pending_client_clock_does_not_define_the_central_confirmation_or_deadline():
    client_request = request(solicitado_en=REQUESTED_AT + timedelta(days=3))
    reservation = confirmed(request=client_request, from_pending=True)
    assert reservation.confirmada_en == CONFIRMED_AT
    assert reservation.vence_en == EXPIRES_AT
    assert reservation.request.solicitado_en > reservation.confirmada_en


@pytest.mark.parametrize("deadline", [CONFIRMED_AT, CONFIRMED_AT - timedelta(seconds=1)])
def test_confirmation_requires_expiry_strictly_after_confirmation(deadline):
    with pytest.raises(InvalidReservation):
        confirmed(expires_at=deadline)


def test_cancel_before_deadline_preserves_the_confirmation_and_appends_an_immutable_trace():
    original = confirmed()
    at = CONFIRMED_AT + timedelta(minutes=1)
    cancelled = original.cancel("actor-cancela", at)
    assert cancelled.estado is ReservationState.CANCELADA
    assert cancelled.codigo == original.codigo
    assert cancelled.confirmada_en == original.confirmada_en
    assert cancelled.vence_en == original.vence_en
    assert cancelled.actualizado_en == at
    assert cancelled.eventos[:-1] == original.eventos
    assert cancelled.eventos[-1].anterior is ReservationState.CONFIRMADA
    assert cancelled.eventos[-1].posterior is ReservationState.CANCELADA
    assert cancelled.eventos[-1].actor_id == "actor-cancela"
    assert original.estado is ReservationState.CONFIRMADA
    assert len(original.eventos) == 1
    with pytest.raises(InvalidTransition):
        cancelled.cancel("actor-cancela", at + timedelta(seconds=1))
    with pytest.raises(FrozenInstanceError):
        cancelled.estado = ReservationState.CONFIRMADA
    with pytest.raises(FrozenInstanceError):
        cancelled.eventos[-1].actor_id = "otro-actor"


@pytest.mark.parametrize("at", [EXPIRES_AT, EXPIRES_AT + timedelta(seconds=1), CONFIRMED_AT - timedelta(seconds=1)])
def test_cancel_rejects_expired_or_backdated_operations(at):
    with pytest.raises(InvalidTransition):
        confirmed().cancel("actor-7", at)


@pytest.mark.parametrize("state", [
    ReservationState.PENDIENTE_SINCRONIZACION,
    ReservationState.RECHAZADA,
    ReservationState.EN_CONFLICTO,
    ReservationState.VENCIDA,
    ReservationState.ATENDIDA,
])
def test_cancel_does_not_apply_to_pending_or_terminal_reservations(state):
    with pytest.raises(InvalidTransition):
        in_state(state).cancel("actor-7", CONFIRMED_AT + timedelta(minutes=1))


def test_expiry_is_allowed_at_the_deadline_and_retries_do_not_duplicate_events():
    original = confirmed()
    with pytest.raises(InvalidTransition):
        original.expire("scheduler", EXPIRES_AT - timedelta(microseconds=1))
    expired = original.expire("scheduler", EXPIRES_AT)
    assert expired.estado is ReservationState.VENCIDA
    assert expired.eventos[-1].anterior is ReservationState.CONFIRMADA
    assert expired.eventos[-1].posterior is ReservationState.VENCIDA
    assert expired.actualizado_en == EXPIRES_AT
    assert original.estado is ReservationState.CONFIRMADA
    assert expired.expire("scheduler", EXPIRES_AT + timedelta(minutes=5)) is expired
    assert len(expired.eventos) == 2


@pytest.mark.parametrize("state", [ReservationState.CANCELADA, ReservationState.ATENDIDA, ReservationState.PENDIENTE_SINCRONIZACION])
def test_expiry_cannot_process_cancelled_attended_or_unconfirmed_reservations(state):
    with pytest.raises(InvalidTransition):
        in_state(state).expire("scheduler", EXPIRES_AT)


@pytest.mark.parametrize("state", [ReservationState.RECHAZADA, ReservationState.EN_CONFLICTO])
def test_pending_can_be_rejected_or_marked_conflicting_without_a_confirmation_code(state):
    pending = Reservation.pending(request())
    rejected = pending.reject("sincronizador", CONFIRMED_AT, state, "  Stock insuficiente  ")
    assert rejected.estado is state
    assert rejected.codigo is rejected.confirmada_en is rejected.vence_en is None
    assert rejected.eventos[-1].anterior is ReservationState.PENDIENTE_SINCRONIZACION
    assert rejected.eventos[-1].posterior is state
    assert rejected.eventos[-1].motivo == "Stock insuficiente"
    assert pending.estado is ReservationState.PENDIENTE_SINCRONIZACION
    assert pending.eventos == ()
    with pytest.raises(InvalidTransition):
        rejected.reject("sincronizador", CONFIRMED_AT, state, "Repetida")


def test_rejection_only_accepts_pending_sources_and_rejection_or_conflict_destinations():
    for original in [confirmed(), in_state(ReservationState.CANCELADA), in_state(ReservationState.ATENDIDA)]:
        with pytest.raises(InvalidTransition):
            original.reject("actor-7", CONFIRMED_AT, ReservationState.RECHAZADA, "No permitido")
    for destination in [ReservationState.CONFIRMADA, ReservationState.CANCELADA]:
        with pytest.raises(InvalidTransition):
            Reservation.pending(request()).reject("actor-7", CONFIRMED_AT, destination, "No permitido")


@pytest.mark.parametrize("state", [ReservationState.PENDIENTE_SINCRONIZACION, ReservationState.RECHAZADA, ReservationState.EN_CONFLICTO])
def test_unconfirmed_states_never_accept_a_central_code_confirmation_or_expiry(state):
    original = in_state(state)
    for values in [{"codigo": "RES-001"}, {"confirmada_en": CONFIRMED_AT}, {"vence_en": EXPIRES_AT}]:
        with pytest.raises(InvalidReservation):
            replace(original, **values)


def test_dates_are_aware_and_normalized_to_utc_through_request_confirmation_and_events():
    local = datetime(2026, 10, 25, 8, tzinfo=timezone(timedelta(hours=-4)))
    reservation_request = request(solicitado_en=local)
    reservation = confirmed(request=reservation_request, at=local + timedelta(minutes=5), expires_at=local + timedelta(hours=1))
    assert reservation_request.solicitado_en == REQUESTED_AT
    assert reservation_request.solicitado_en.tzinfo is timezone.utc
    assert reservation.confirmada_en.tzinfo is timezone.utc
    assert reservation.vence_en.tzinfo is timezone.utc
    assert reservation.eventos[0].ocurrido_en.tzinfo is timezone.utc
    assert isinstance(reservation.eventos[0].id, UUID)
    with pytest.raises(FrozenInstanceError):
        reservation_request.lineas = ()


def test_naive_dates_and_blank_rejection_reasons_are_rejected():
    naive = datetime(2026, 10, 25, 12)
    with pytest.raises(InvalidReservation):
        request(solicitado_en=naive)
    with pytest.raises(InvalidReservation):
        confirmed(at=naive)
    with pytest.raises(InvalidReservation):
        ReservationEvent("actor-7", None, ReservationState.CONFIRMADA, naive)
    with pytest.raises(InvalidReservation):
        Reservation.pending(request()).reject("actor-7", CONFIRMED_AT, ReservationState.RECHAZADA, " \n\t")


def test_authorization_requires_explicit_permission_and_the_correct_company_branch_and_customer():
    reservation_request = request()
    access = authorization()
    for permission in ReservationPermission:
        access.require(reservation_request, permission)
    for denied_request in [
        request(empresa_id=9, lineas=(ReservationLine(InventoryKey(9, 2, 3), 1),)),
        request(sucursal_id=9, lineas=(ReservationLine(InventoryKey(1, 9, 3), 1),)),
        request(cliente_id="cliente-2"),
    ]:
        with pytest.raises(ReservationForbidden):
            access.require(denied_request, ReservationPermission.CONSULTAR)
    assert access.actor_id == "actor-7"
    assert authorization(clientes_permitidos=None).require(request(cliente_id="cliente-2"), ReservationPermission.CONSULTAR) is None


def test_actor_identity_does_not_grant_permissions_or_bypass_an_empty_customer_scope():
    for actor in ["administrador", "encargado", "cliente"]:
        with pytest.raises(ReservationForbidden):
            authorization(actor_id=actor, permissions=frozenset()).require(request(), ReservationPermission.REGISTRAR)
    read_only = authorization(permissions=frozenset({ReservationPermission.CONSULTAR}))
    with pytest.raises(ReservationForbidden):
        read_only.require(request(), ReservationPermission.CANCELAR)
    with pytest.raises(ReservationForbidden):
        authorization(clientes_permitidos=frozenset()).require(request(), ReservationPermission.CONSULTAR)
    with pytest.raises(ReservationForbidden):
        authorization().require(request(), "consultar")


def test_authorization_context_rejects_mutable_grants_and_untyped_permissions():
    for changes in [
        {"sucursales": {2}},
        {"permissions": {ReservationPermission.CONSULTAR}},
        {"permissions": frozenset({"consultar"})},
        {"clientes_permitidos": {"cliente-1"}},
    ]:
        with pytest.raises(ReservationForbidden):
            authorization(**changes)
    with pytest.raises(FrozenInstanceError):
        authorization().empresa_id = 9
