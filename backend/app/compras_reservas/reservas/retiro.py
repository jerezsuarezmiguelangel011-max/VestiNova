"""CU14: verificación previa al retiro, sin registrar aún una entrega central."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.compras_reservas.reservas.domain import (
    InvalidReservation, InvalidTransition, Reservation, ReservationForbidden,
    ReservationState, utc,
)

ALLOWED_ROLES = frozenset({"CAJERO", "ENCARGADO_SUCURSAL"})


@dataclass(frozen=True, slots=True)
class HandoverContext:
    actor_id: int
    empresa_id: int
    sucursales: frozenset[int]
    rol: str


@dataclass(frozen=True, slots=True)
class HandoverPreview:
    reserva_id: UUID
    codigo: str
    sucursal_id: int
    cliente_id: int
    vence_en: datetime
    items: tuple[tuple[int, int], ...]
    estado: str = "LISTA_PARA_VERIFICACION_FISICA"


def prepare_handover(
    reservation: Reservation,
    context: HandoverContext,
    supplied_code: str,
    at: datetime,
) -> HandoverPreview:
    """Valida el retiro sin mutar la reserva, el stock ni emitir una constancia.

    El adaptador transaccional aún pendiente deberá verificar identidad del
    cliente, bloquear inventario y aplicar salida/liberación exactamente una vez.
    """
    if not isinstance(reservation, Reservation) or not isinstance(context, HandoverContext):
        raise InvalidReservation("La solicitud de atención no es válida.")
    if type(context.actor_id) is not int or context.actor_id < 1:
        raise ReservationForbidden("El actor no es válido.")
    if (
        context.rol not in ALLOWED_ROLES
        or context.empresa_id != reservation.request.empresa_id
        or reservation.request.sucursal_id not in context.sucursales
    ):
        raise ReservationForbidden("No puedes atender reservas de esta empresa o sucursal.")
    if reservation.estado is not ReservationState.CONFIRMADA:
        raise InvalidTransition("Solo se pueden preparar reservas confirmadas.")
    now = utc(at)
    if reservation.vence_en is None or now >= reservation.vence_en:
        raise InvalidTransition("La reserva venció y no puede prepararse para retiro.")
    if not isinstance(supplied_code, str) or not supplied_code.strip() or supplied_code.strip() != reservation.codigo:
        raise ReservationForbidden("El código de retiro no coincide con la reserva.")
    return HandoverPreview(
        reserva_id=reservation.id,
        codigo=reservation.codigo,
        sucursal_id=reservation.request.sucursal_id,
        cliente_id=reservation.request.cliente_id,
        vence_en=reservation.vence_en,
        items=tuple((line.key.variante_id, line.cantidad) for line in reservation.request.lineas),
    )
