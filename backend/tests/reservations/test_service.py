from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.inventory.domain import BranchReference, InventoryKey, StockBalance, VariantReference
from app.reservations.domain import (
    CustomerReference, InsufficientStock, InvalidReservation, InvalidTransition,
    Reservation, ReservationAuthorization, ReservationConfigurationError, ReservationConflict,
    ReservationForbidden, ReservationLine, ReservationNotFound, ReservationPermission,
    ReservationRequest, ReservationState,
)
from app.reservations.service import ReservationService
from tests.reservations.fakes import (
    FakeAuthorizer, FakePolicy, FakeReferences, FakeUnitOfWorkFactory, ReservationTestState,
)


ACTOR, COMPANY, BRANCH, CUSTOMER = 50, 1, 10, 1000
KEY = InventoryKey(COMPANY, BRANCH, 100)
SECOND_KEY = InventoryKey(COMPANY, BRANCH, 101)
OTHER_KEY = InventoryKey(2, 20, 200)
NOW = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
CONFIGURED_DURATION = timedelta(hours=2)  # Configuración explícita de la prueba, no regla de negocio.


def request(*, reservation_id=None, lines=None, customer=CUSTOMER, requested_at=None):
    return ReservationRequest(
        id=reservation_id or uuid4(), empresa_id=COMPANY, cliente_id=customer, sucursal_id=BRANCH,
        lineas=lines if lines is not None else (ReservationLine(KEY, 2), ReservationLine(SECOND_KEY, 3)),
        solicitado_en=requested_at or NOW - timedelta(minutes=15),
    )


def make_service(env, *, code_factory=None, clock=None):
    return ReservationService(
        env.authorizer, env.references, env.policy, env.factory,
        clock=clock or (lambda: env.now),
        code_factory=code_factory or (lambda: f"PRUEBA-{next(env.codes)}"),
    )


@pytest.fixture
def reservations():
    env = SimpleNamespace(now=NOW, codes=count(1))
    env.state = ReservationTestState(balances={
        KEY: StockBalance(KEY, 5, 1),
        SECOND_KEY: StockBalance(SECOND_KEY, 8, 2),
        OTHER_KEY: StockBalance(OTHER_KEY, 100, 7),
    })
    env.grant = ReservationAuthorization(
        actor_id=ACTOR, empresa_id=COMPANY, sucursales=frozenset({BRANCH}),
        permissions=frozenset(ReservationPermission), clientes_permitidos=frozenset({CUSTOMER}),
    )
    env.authorizer = FakeAuthorizer(env.grant)
    env.references = FakeReferences(
        {BRANCH: BranchReference(BRANCH, COMPANY)},
        {KEY.variante_id: VariantReference(KEY.variante_id, COMPANY), SECOND_KEY.variante_id: VariantReference(SECOND_KEY.variante_id, COMPANY)},
        {(COMPANY, CUSTOMER): CustomerReference(CUSTOMER, COMPANY), (COMPANY, 1001): CustomerReference(1001, COMPANY)},
    )
    env.policy = FakePolicy(CONFIGURED_DURATION)
    env.factory = FakeUnitOfWorkFactory(env.state)
    env.service = make_service(env)
    return env


def total_holds(env):
    return sum(len(unit.inventory.hold_calls) for unit in env.factory.instances if unit.entered)


def total_releases(env):
    return sum(len(unit.inventory.release_calls) for unit in env.factory.instances if unit.entered)


def test_register_confirms_with_server_policy_and_commits_reservation_and_cu08_holds_together(reservations):
    env = reservations
    original = deepcopy(env.state)
    submitted = request()
    confirmed = env.service.register_online(ACTOR, submitted)
    assert confirmed.estado is ReservationState.CONFIRMADA
    assert confirmed.request == submitted
    assert confirmed.codigo == "PRUEBA-1"
    assert confirmed.confirmada_en == NOW
    assert confirmed.vence_en == NOW + CONFIGURED_DURATION
    assert confirmed.actualizado_en == NOW
    assert len(confirmed.eventos) == 1
    assert confirmed.eventos[0].actor_id == ACTOR
    assert confirmed.eventos[0].anterior is None
    assert confirmed.eventos[0].posterior is ReservationState.CONFIRMADA
    assert env.policy.expiry_calls == [(submitted, NOW)]
    assert env.state.reservations == {submitted.id: confirmed}
    assert env.state.commitments == {submitted.id: submitted.lineas}
    for line in submitted.lineas:
        before, after = original.balances[line.key], env.state.balances[line.key]
        assert after.stock_actual == before.stock_actual
        assert after.stock_reservado == before.stock_reservado + line.cantidad
        assert after.stock_disponible == before.stock_disponible - line.cantidad
    assert env.state.balances[OTHER_KEY] == original.balances[OTHER_KEY]
    unit = env.factory.instances[0]
    assert unit.inventory.hold_calls == [(submitted.id, submitted.lineas)]
    assert unit.repository.add_calls == [confirmed]
    assert unit.commit_calls == 1 and unit.committed and unit.closed


def test_get_is_scoped_read_only_and_does_not_touch_commitments(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    original = deepcopy(env.state)
    result = env.service.get_reservation(ACTOR, COMPANY, confirmed.id)
    assert result == confirmed
    assert env.state == original
    unit = env.factory.instances[-1]
    assert unit.repository.get_calls == [(COMPANY, confirmed.id)]
    assert unit.repository.add_calls == unit.repository.save_calls == []
    assert unit.inventory.hold_calls == unit.inventory.release_calls == []
    assert unit.commit_calls == 0


@pytest.mark.parametrize("changes", [
    {"actor_id": "otro-actor"}, {"empresa_id": 2}, {"sucursales": frozenset({20})},
    {"permissions": frozenset({ReservationPermission.CONSULTAR})}, {"clientes_permitidos": frozenset()},
])
def test_register_rejects_forged_or_insufficient_scope_before_opening_uow(reservations, changes):
    env = reservations
    env.authorizer.authorization = replace(env.grant, **changes)
    original = deepcopy(env.state)
    with pytest.raises(ReservationForbidden):
        env.service.register_online(ACTOR, request())
    assert env.factory.instances == []
    assert env.state == original


def test_missing_authorization_is_not_an_implicit_company_wide_grant(reservations):
    env = reservations
    env.authorizer.authorization = None
    with pytest.raises(ReservationForbidden):
        env.service.register_online(ACTOR, request())
    assert env.factory.instances == []


def test_only_explicit_customer_wide_grant_can_register_another_customer(reservations):
    env = reservations
    submitted = request(customer=1001)
    with pytest.raises(ReservationForbidden):
        env.service.register_online(ACTOR, submitted)
    env.authorizer.authorization = replace(env.grant, clientes_permitidos=None)
    assert env.service.register_online(ACTOR, submitted).request.cliente_id == 1001


@pytest.mark.parametrize("kind", ["branch", "variant", "customer"])
def test_missing_master_reference_does_not_create_central_reservation(reservations, kind):
    env = reservations
    getattr(env.references, {"branch": "branches", "variant": "variants", "customer": "customers"}[kind]).clear()
    original = deepcopy(env.state)
    with pytest.raises(ReservationNotFound):
        env.service.register_online(ACTOR, request())
    assert len(env.factory.instances) == 1
    assert env.factory.instances[0].repository.add_calls == []
    assert total_holds(env) == 0
    assert env.state == original


@pytest.mark.parametrize("kind,reference", [
    ("branch", BranchReference(99, COMPANY)), ("branch", BranchReference(BRANCH, 2)),
    ("variant", VariantReference(99, COMPANY)), ("variant", VariantReference(KEY.variante_id, 2)),
    ("customer", CustomerReference(99, COMPANY)), ("customer", CustomerReference(CUSTOMER, 2)),
])
def test_reference_resolver_cannot_replace_identity_or_cross_company(reservations, kind, reference):
    env = reservations
    if kind == "branch":
        env.references.branches[BRANCH] = reference
    elif kind == "variant":
        env.references.variants[KEY.variante_id] = reference
    else:
        env.references.customers[(COMPANY, CUSTOMER)] = reference
    with pytest.raises(ReservationForbidden):
        env.service.register_online(ACTOR, request())
    assert len(env.factory.instances) == 1
    assert env.factory.instances[0].repository.add_calls == []
    assert total_holds(env) == 0


def test_missing_inventory_is_unknown_and_not_silently_replaced_with_zero(reservations):
    env = reservations
    del env.state.balances[KEY]
    original = deepcopy(env.state)
    with pytest.raises(ReservationNotFound):
        env.service.register_online(ACTOR, request())
    assert env.state == original
    assert total_holds(env) == 0


def test_inventory_adapter_cannot_return_a_balance_for_another_key(reservations):
    env = reservations
    env.factory.inventory_reads[KEY] = env.state.balances[OTHER_KEY]
    original = deepcopy(env.state)
    with pytest.raises(ReservationForbidden):
        env.service.register_online(ACTOR, request())
    assert env.state == original
    assert total_holds(env) == 0


def test_insufficient_second_line_rejects_entire_reservation_without_partial_holds(reservations):
    env = reservations
    env.state.balances[SECOND_KEY] = StockBalance(SECOND_KEY, 2, 2)
    original = deepcopy(env.state)
    with pytest.raises(InsufficientStock):
        env.service.register_online(ACTOR, request())
    assert env.state == original
    assert total_holds(env) == 0


def test_hold_rechecks_authoritative_cu08_stock_and_rolls_back_first_line_if_second_changed(reservations):
    env = reservations
    env.factory.inventory_reads[SECOND_KEY] = env.state.balances[SECOND_KEY]
    env.state.balances[SECOND_KEY] = StockBalance(SECOND_KEY, 2, 2)
    original = deepcopy(env.state)
    with pytest.raises(InsufficientStock):
        env.service.register_online(ACTOR, request())
    assert env.state == original
    unit = env.factory.instances[-1]
    assert unit.inventory.held_keys == [KEY]
    assert len(unit.inventory.hold_calls) == 1
    assert unit.rolled_back and not unit.committed


def test_same_uuid_and_content_returns_current_record_without_another_hold(reservations):
    env = reservations
    submitted = request()
    confirmed = env.service.register_online(ACTOR, submitted)
    original = deepcopy(env.state)
    assert env.service.register_online(ACTOR, submitted) == confirmed
    assert env.state == original
    assert total_holds(env) == 1
    assert env.factory.instances[-1].commit_calls == 0


def test_same_uuid_with_different_content_is_conflict_and_never_overwrites(reservations):
    env = reservations
    submitted = request()
    env.service.register_online(ACTOR, submitted)
    original = deepcopy(env.state)
    different = replace(submitted, lineas=(ReservationLine(KEY, 1),))
    with pytest.raises(ReservationConflict):
        env.service.register_online(ACTOR, different)
    assert env.state == original
    assert total_holds(env) == 1


def test_generated_code_collision_rolls_back_new_reservation_and_its_hold(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request(lines=(ReservationLine(KEY, 1),)))
    original = deepcopy(env.state)
    duplicate_code_service = make_service(env, code_factory=lambda: confirmed.codigo)
    with pytest.raises(ReservationConflict):
        duplicate_code_service.register_online(ACTOR, request(lines=(ReservationLine(KEY, 1),)))
    assert env.state == original
    assert env.factory.instances[-1].rolled_back


@pytest.mark.parametrize("operation", ["register", "synchronize"])
def test_uuid_is_global_and_cannot_overwrite_a_reservation_in_another_company(reservations, operation):
    env = reservations
    identifier = uuid4()
    external_request = ReservationRequest(
        identifier, 2, 2000, 20, (ReservationLine(OTHER_KEY, 1),), NOW - timedelta(minutes=5),
    )
    external = Reservation.confirmed(external_request, ACTOR, "EXTERNA", NOW, NOW + CONFIGURED_DURATION).cancel(ACTOR, NOW)
    env.state.reservations[identifier] = external
    original = deepcopy(env.state)
    submitted = request(reservation_id=identifier)
    if operation == "register":
        with pytest.raises(ReservationConflict):
            env.service.register_online(ACTOR, submitted)
    else:
        assert env.service.synchronize(ACTOR, Reservation.pending(submitted)).estado is ReservationState.EN_CONFLICTO
    assert env.state == original


@pytest.mark.parametrize("failure", ["add", "hold", "commit"])
def test_registration_failure_rolls_back_central_record_and_all_stock_holds(reservations, failure):
    env = reservations
    setattr(env.factory, f"fail_{failure}", True)
    original = deepcopy(env.state)
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        env.service.register_online(ACTOR, request())
    assert env.state == original
    unit = env.factory.instances[-1]
    assert unit.closed and unit.rolled_back and not unit.committed


@pytest.mark.parametrize("action", ["cancel", "expire"])
def test_terminal_transition_releases_only_own_hold_once_and_never_decrements_physical(reservations, action):
    env = reservations
    first = env.service.register_online(ACTOR, request(lines=(ReservationLine(KEY, 1),)))
    second = env.service.register_online(ACTOR, request(lines=(ReservationLine(KEY, 1),)))
    env.now = NOW + (timedelta(minutes=10) if action == "cancel" else CONFIGURED_DURATION)
    result = getattr(env.service, action)(ACTOR, COMPANY, first.id)
    expected_state = ReservationState.CANCELADA if action == "cancel" else ReservationState.VENCIDA
    assert result.estado is expected_state
    assert result.eventos[-1].actor_id == ACTOR
    assert result.eventos[-1].anterior is ReservationState.CONFIRMADA
    assert result.eventos[-1].posterior is expected_state
    assert env.state.balances[KEY] == StockBalance(KEY, 5, 2)
    assert env.state.commitments == {second.id: second.request.lineas}
    assert env.state.reservations[second.id] == second
    assert total_releases(env) == 1
    original = deepcopy(env.state)
    if action == "cancel":
        with pytest.raises(InvalidTransition):
            env.service.cancel(ACTOR, COMPANY, first.id)
    else:
        assert env.service.expire(ACTOR, COMPANY, first.id) == result
    assert env.state == original
    assert total_releases(env) == 1
    assert env.factory.instances[-1].commit_calls == 0


def test_cancellation_uses_injected_policy_and_does_not_invent_a_cutoff(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    env.now = NOW + timedelta(minutes=10)
    env.policy.cancellation_error = InvalidTransition("La condición externa impide cancelar.")
    original = deepcopy(env.state)
    with pytest.raises(InvalidTransition):
        env.service.cancel(ACTOR, COMPANY, confirmed.id)
    assert env.policy.cancel_calls == [(confirmed, env.now)]
    assert env.state == original
    assert total_releases(env) == 0


@pytest.mark.parametrize("policy_result", [False, True])
def test_boolean_cancellation_policy_result_is_configuration_error_before_release(reservations, policy_result):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    env.policy.cancellation_result = policy_result
    original = deepcopy(env.state)
    with pytest.raises(ReservationConfigurationError):
        env.service.cancel(ACTOR, COMPANY, confirmed.id)
    assert env.state == original
    assert total_releases(env) == 0


@pytest.mark.parametrize("failure", ["save", "release", "commit"])
def test_cancellation_failure_rolls_back_status_and_released_units(reservations, failure):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    setattr(env.factory, f"fail_{failure}", True)
    original = deepcopy(env.state)
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        env.service.cancel(ACTOR, COMPANY, confirmed.id)
    assert env.state == original
    unit = env.factory.instances[-1]
    assert unit.closed and unit.rolled_back and not unit.committed


def test_reservation_does_not_expire_before_configured_server_deadline(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    env.now = confirmed.vence_en - timedelta(microseconds=1)
    original = deepcopy(env.state)
    with pytest.raises(InvalidTransition):
        env.service.expire(ACTOR, COMPANY, confirmed.id)
    assert env.state == original
    assert total_releases(env) == 0


@pytest.mark.parametrize("operation,permission", [
    ("get_reservation", ReservationPermission.CONSULTAR),
    ("cancel", ReservationPermission.CANCELAR), ("expire", ReservationPermission.VENCER),
])
def test_read_cancel_and_expire_require_their_own_permission(reservations, operation, permission):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    env.authorizer.authorization = replace(env.grant, permissions=env.grant.permissions - {permission})
    original = deepcopy(env.state)
    with pytest.raises(ReservationForbidden):
        getattr(env.service, operation)(ACTOR, COMPANY, confirmed.id)
    assert env.state == original
    assert total_releases(env) == 0


def test_read_revalidates_customer_scope_and_rejects_forged_repository_result(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    env.authorizer.authorization = replace(env.grant, clientes_permitidos=frozenset({1001}))
    with pytest.raises(ReservationForbidden):
        env.service.get_reservation(ACTOR, COMPANY, confirmed.id)
    env.authorizer.authorization = env.grant
    other_request = replace(confirmed.request, id=uuid4())
    env.factory.reservation_reads[(COMPANY, confirmed.id)] = Reservation.confirmed(
        other_request, ACTOR, "OTRA", NOW, NOW + CONFIGURED_DURATION,
    )
    with pytest.raises(ReservationForbidden):
        env.service.get_reservation(ACTOR, COMPANY, confirmed.id)


def test_synchronization_confirms_using_server_time_without_treating_offline_age_as_a_hold(reservations):
    env = reservations
    pending = Reservation.pending(request(requested_at=NOW - timedelta(days=2)))
    original_pending = deepcopy(pending)
    confirmed = env.service.synchronize(ACTOR, pending)
    assert confirmed.estado is ReservationState.CONFIRMADA
    assert confirmed.confirmada_en == NOW
    assert confirmed.vence_en == NOW + CONFIGURED_DURATION
    assert confirmed.eventos[0].anterior is ReservationState.PENDIENTE_SINCRONIZACION
    assert pending == original_pending
    assert pending.codigo is pending.vence_en is pending.confirmada_en is None
    assert env.state.commitments == {pending.id: pending.request.lineas}


def test_duplicate_synchronization_returns_current_state_without_reholding_even_after_cancellation(reservations):
    env = reservations
    pending = Reservation.pending(request())
    confirmed = env.service.synchronize(ACTOR, pending)
    assert env.service.synchronize(ACTOR, pending) == confirmed
    assert total_holds(env) == 1
    cancelled = env.service.cancel(ACTOR, COMPANY, confirmed.id)
    original = deepcopy(env.state)
    assert env.service.synchronize(ACTOR, pending) == cancelled
    assert env.state == original
    assert total_holds(env) == 1
    assert total_releases(env) == 1


def test_sync_retry_after_lost_response_returns_confirmation_even_when_master_references_disappear(reservations):
    env = reservations
    pending = Reservation.pending(request())
    confirmed = env.service.synchronize(ACTOR, pending)
    env.references.customers.clear()
    env.references.variants.clear()
    before = deepcopy(env.state)
    reference_calls = (len(env.references.customer_calls), len(env.references.variant_calls))
    assert env.service.synchronize(ACTOR, pending) == confirmed
    assert env.state == before
    assert total_holds(env) == 1
    assert (len(env.references.customer_calls), len(env.references.variant_calls)) == reference_calls
    assert env.factory.instances[-1].commit_calls == 0


@pytest.mark.parametrize("failure", ["forbidden", "missing", "incompatible", "invalid"])
def test_sync_business_rejection_changes_only_returned_local_copy(reservations, failure):
    env = reservations
    pending = Reservation.pending(request())
    original_pending, original_state = deepcopy(pending), deepcopy(env.state)
    if failure == "forbidden":
        env.authorizer.authorization = replace(env.grant, clientes_permitidos=frozenset())
    elif failure == "missing":
        env.references.customers.clear()
    elif failure == "incompatible":
        env.references.variants[KEY.variante_id] = VariantReference(KEY.variante_id, 2)
    else:
        env.authorizer.error = InvalidReservation("Solicitud incompatible con el contexto del cliente.")
    rejected = env.service.synchronize(ACTOR, pending)
    assert rejected.estado is ReservationState.RECHAZADA
    assert rejected.eventos[-1].actor_id == ACTOR
    assert rejected.eventos[-1].motivo
    assert rejected.codigo is None
    assert env.state == original_state
    assert pending == original_pending
    if failure in {"forbidden", "invalid"}:
        assert env.factory.instances == []
    else:
        assert len(env.factory.instances) == 1
        assert env.factory.instances[0].commit_calls == 0


@pytest.mark.parametrize("failure", ["stock", "uuid"])
def test_sync_conflict_never_persists_pending_or_conflict_as_a_central_reservation(reservations, failure):
    env = reservations
    submitted = request()
    if failure == "stock":
        env.state.balances[KEY] = StockBalance(KEY, 1, 1)
    else:
        env.service.register_online(ACTOR, submitted)
        submitted = replace(submitted, lineas=(ReservationLine(KEY, 1),))
    original = deepcopy(env.state)
    pending = Reservation.pending(submitted)
    result = env.service.synchronize(ACTOR, pending)
    assert result.estado is ReservationState.EN_CONFLICTO
    assert result.eventos[-1].motivo
    assert env.state == original
    assert pending.estado is ReservationState.PENDIENTE_SINCRONIZACION


def test_sync_infrastructure_failure_keeps_pending_for_retry_and_rolls_back_everything(reservations):
    env = reservations
    pending = Reservation.pending(request())
    original_pending, original_state = deepcopy(pending), deepcopy(env.state)
    env.factory.fail_commit = True
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        env.service.synchronize(ACTOR, pending)
    assert pending == original_pending
    assert env.state == original_state
    env.factory.fail_commit = False
    confirmed = env.service.synchronize(ACTOR, pending)
    assert confirmed.estado is ReservationState.CONFIRMADA
    assert env.state.commitments == {pending.id: pending.request.lineas}
    assert len(env.state.reservations) == 1


@pytest.mark.parametrize("configuration", ["expiry_missing", "expiry_not_future", "code", "clock"])
def test_sync_configuration_failure_is_not_a_business_rejection_and_never_holds_stock(reservations, configuration):
    env = reservations
    pending = Reservation.pending(request())
    original_pending, original_state = deepcopy(pending), deepcopy(env.state)
    if configuration == "expiry_missing":
        env.policy.duration = None
    elif configuration == "expiry_not_future":
        env.policy.duration = timedelta(0)
    elif configuration == "code":
        env.service = make_service(env, code_factory=lambda: " ")
    else:
        env.service = make_service(env, clock=lambda: NOW.replace(tzinfo=None))
    with pytest.raises(ReservationConfigurationError):
        env.service.synchronize(ACTOR, pending)
    assert pending == original_pending
    assert env.state == original_state
    assert total_holds(env) == 0


def test_sync_refuses_a_reservation_that_is_already_centrally_confirmed(reservations):
    env = reservations
    confirmed = env.service.register_online(ACTOR, request())
    original = deepcopy(env.state)
    with pytest.raises(InvalidTransition):
        env.service.synchronize(ACTOR, confirmed)
    assert env.state == original
    assert total_holds(env) == 1


def test_two_concurrent_requests_for_last_unit_cannot_both_confirm(reservations):
    env = reservations
    env.state.balances[KEY] = StockBalance(KEY, 1, 0)
    submissions = [request(lines=(ReservationLine(KEY, 1),)) for _ in range(2)]
    starting = Barrier(2)

    def register(submitted):
        starting.wait(timeout=5)
        try:
            return env.service.register_online(ACTOR, submitted)
        except InsufficientStock as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(register, submissions))
    confirmed = [item for item in outcomes if isinstance(item, Reservation)]
    rejected = [item for item in outcomes if isinstance(item, InsufficientStock)]
    assert len(confirmed) == len(rejected) == 1
    assert env.state.balances[KEY] == StockBalance(KEY, 1, 1)
    assert env.state.reservations == {confirmed[0].id: confirmed[0]}
    assert env.state.commitments == {confirmed[0].id: confirmed[0].request.lineas}
