from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.inventory.domain import (
    BranchReference, Identifier, IncompatibleReference, StockBalance,
    VariantReference, validate_identifier,
)
from app.reservations.domain import (
    CustomerReference, InsufficientStock, InvalidReservation, InvalidTransition,
    Reservation, ReservationAuthorization, ReservationConfigurationError, ReservationConflict, ReservationForbidden,
    ReservationNotFound, ReservationPermission, ReservationRequest, ReservationState, utc,
)
from app.reservations.ports import (
    ReservationAuthorizer, ReservationPolicy, ReservationReferences, ReservationUnitOfWork,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _code() -> str:
    return str(uuid4())


class ReservationService:
    def __init__(
        self, authorizer: ReservationAuthorizer, references: ReservationReferences,
        policy: ReservationPolicy, uow_factory: Callable[[], ReservationUnitOfWork], *,
        clock: Callable[[], datetime] = _utc_now, code_factory: Callable[[], str] = _code,
    ):
        self._authorizer = authorizer
        self._references = references
        self._policy = policy
        self._uow_factory = uow_factory
        self._clock = clock
        self._code_factory = code_factory

    def register_online(self, actor_id: Identifier, request: ReservationRequest) -> Reservation:
        return self._register(actor_id, request, from_pending=False)

    def _register(self, actor_id: Identifier, request: ReservationRequest, *, from_pending: bool) -> Reservation:
        if not isinstance(request, ReservationRequest):
            raise InvalidReservation("La solicitud de reserva no es válida.")
        context = self._context(actor_id, request.empresa_id)
        context.require(request, ReservationPermission.REGISTRAR)
        with self._uow_factory() as work:
            previous = work.repository.get(request.empresa_id, request.id)
            if previous is not None:
                self._check_stored(previous, request.empresa_id, request.id)
                if not previous.request.same_content(request):
                    raise ReservationConflict("El UUID ya corresponde a una solicitud diferente.")
                if previous.estado is ReservationState.PENDIENTE_SINCRONIZACION:
                    raise ReservationConflict("Una solicitud local no debe persistirse como reserva central.")
                # Un reenvío no vuelve a comprometer, incluso si después se canceló o venció.
                return previous
            self._validate_references(request)
            for line in request.lineas:
                balance = work.inventory.get(line.key)
                if balance is None:
                    raise ReservationNotFound("No existe disponibilidad conocida para una variante solicitada.")
                if not isinstance(balance, StockBalance) or balance.key != line.key:
                    raise ReservationForbidden("La disponibilidad no corresponde al ámbito solicitado.")
                if line.cantidad > balance.stock_disponible:
                    raise InsufficientStock("No hay unidades disponibles suficientes para confirmar la reserva.")
            now = self._now()
            try:
                expiration = utc(self._policy.expires_at(request, now))
                reservation = Reservation.confirmed(request, actor_id, self._code_factory(), now, expiration, from_pending=from_pending)
            except InvalidReservation as error:
                raise ReservationConfigurationError("No hay una configuración válida de vencimiento o código de reserva.") from error
            # hold vuelve a comprobar bajo control de concurrencia; no basta la lectura previa.
            work.inventory.hold(reservation.id, request.lineas)
            work.repository.add(reservation)
            work.commit()
            return reservation

    def get_reservation(self, actor_id: Identifier, empresa_id: Identifier, reservation_id: UUID) -> Reservation:
        context = self._context(actor_id, empresa_id, ReservationPermission.CONSULTAR)
        with self._uow_factory() as work:
            reservation = self._get(work, empresa_id, reservation_id)
            context.require(reservation.request, ReservationPermission.CONSULTAR)
            return reservation

    def cancel(self, actor_id: Identifier, empresa_id: Identifier, reservation_id: UUID) -> Reservation:
        context = self._context(actor_id, empresa_id, ReservationPermission.CANCELAR)
        with self._uow_factory() as work:
            previous = self._get(work, empresa_id, reservation_id)
            context.require(previous.request, ReservationPermission.CANCELAR)
            now = self._now()
            updated = previous.cancel(actor_id, now)
            if self._policy.ensure_cancelable(previous, now) is not None:
                raise ReservationConfigurationError("La política de cancelación debe autorizar explícitamente o rechazar mediante un error.")
            work.inventory.release(previous.id)
            work.repository.save(updated)
            work.commit()
            return updated

    def expire(self, actor_id: Identifier, empresa_id: Identifier, reservation_id: UUID) -> Reservation:
        context = self._context(actor_id, empresa_id, ReservationPermission.VENCER)
        with self._uow_factory() as work:
            previous = self._get(work, empresa_id, reservation_id)
            context.require(previous.request, ReservationPermission.VENCER)
            updated = previous.expire(actor_id, self._now())
            if updated is previous:
                return previous
            work.inventory.release(previous.id)
            work.repository.save(updated)
            work.commit()
            return updated

    def synchronize(self, actor_id: Identifier, pending: Reservation) -> Reservation:
        """Validación central pura; CU15 deberá transportar y conservar el resultado local."""
        if not isinstance(pending, Reservation) or pending.estado is not ReservationState.PENDIENTE_SINCRONIZACION:
            raise InvalidTransition("Solo se puede validar una solicitud pendiente de sincronización.")
        validate_identifier(actor_id)
        try:
            return self._register(actor_id, pending.request, from_pending=True)
        except ReservationConflict:
            return pending.reject(actor_id, self._now(), ReservationState.EN_CONFLICTO,
                                  "La solicitud no pudo confirmarse por un conflicto de disponibilidad o identificador.")
        except (ReservationForbidden, ReservationNotFound, InvalidReservation, IncompatibleReference):
            return pending.reject(actor_id, self._now(), ReservationState.RECHAZADA,
                                  "La solicitud no superó la validación central de autorización o referencias.")
        # Los fallos de infraestructura se propagan: no son rechazos comerciales y no cambian la solicitud.

    def _now(self) -> datetime:
        try:
            return utc(self._clock())
        except InvalidReservation as error:
            raise ReservationConfigurationError("El reloj central debe proporcionar fechas con zona horaria.") from error

    def _context(
        self, actor_id: Identifier, empresa_id: Identifier,
        permission: ReservationPermission | None = None,
    ) -> ReservationAuthorization:
        validate_identifier(actor_id)
        validate_identifier(empresa_id)
        context = self._authorizer.authorize(actor_id, empresa_id)
        if not isinstance(context, ReservationAuthorization) or context.actor_id != actor_id or context.empresa_id != empresa_id:
            raise ReservationForbidden("El contexto autorizado no corresponde al actor y empresa solicitados.")
        if permission is not None and permission not in context.permissions:
            raise ReservationForbidden("El actor no tiene permiso para esta operación de reservas.")
        return context

    def _validate_references(self, request: ReservationRequest) -> None:
        branch = self._references.get_branch(request.sucursal_id)
        if branch is None:
            raise ReservationNotFound("La sucursal no está disponible.")
        if not isinstance(branch, BranchReference) or branch.id != request.sucursal_id or branch.empresa_id != request.empresa_id:
            raise ReservationForbidden("La sucursal no corresponde a la empresa.")
        customer = self._references.get_customer(request.cliente_id, request.empresa_id)
        if customer is None:
            raise ReservationNotFound("El cliente no está disponible en esta empresa.")
        if not isinstance(customer, CustomerReference) or customer.id != request.cliente_id or customer.empresa_id != request.empresa_id:
            raise ReservationForbidden("El cliente no corresponde al ámbito autorizado.")
        for line in request.lineas:
            variant = self._references.get_variant(line.key.variante_id)
            if variant is None:
                raise ReservationNotFound("La variante no está disponible.")
            if not isinstance(variant, VariantReference) or variant.id != line.key.variante_id or variant.empresa_id != request.empresa_id:
                raise ReservationForbidden("La variante no corresponde a la empresa.")

    @staticmethod
    def _check_stored(reservation: Reservation, empresa_id: Identifier, reservation_id: UUID) -> None:
        if not isinstance(reservation, Reservation) or reservation.request.empresa_id != empresa_id or reservation.id != reservation_id:
            raise ReservationForbidden("La reserva no corresponde al ámbito autorizado.")

    @classmethod
    def _get(cls, work: ReservationUnitOfWork, empresa_id: Identifier, reservation_id: UUID) -> Reservation:
        if not isinstance(reservation_id, UUID):
            raise InvalidReservation("La reserva debe identificarse mediante UUID.")
        reservation = work.repository.get(empresa_id, reservation_id)
        if reservation is None:
            raise ReservationNotFound("No se encontró la reserva en esta empresa.")
        cls._check_stored(reservation, empresa_id, reservation_id)
        return reservation
