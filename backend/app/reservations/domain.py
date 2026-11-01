from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from app.inventory.domain import Identifier, InventoryKey, validate_identifier


class ReservationError(Exception):
    pass


class InvalidReservation(ReservationError):
    pass


class ReservationForbidden(ReservationError):
    pass


class ReservationNotFound(ReservationError):
    pass


class ReservationConflict(ReservationError):
    pass


class InsufficientStock(ReservationConflict):
    pass


class InvalidTransition(ReservationError):
    pass


class ReservationConfigurationError(ReservationError):
    pass


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise InvalidReservation("Las fechas deben incluir zona horaria.")
    return value.astimezone(timezone.utc)


def _text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReservation("El código o motivo no puede estar vacío.")
    return value.strip()


class ReservationState(str, Enum):
    CONFIRMADA = "CONFIRMADA"
    CANCELADA = "CANCELADA"
    VENCIDA = "VENCIDA"
    PENDIENTE_SINCRONIZACION = "PENDIENTE_SINCRONIZACION"
    RECHAZADA = "RECHAZADA"
    EN_CONFLICTO = "EN_CONFLICTO"
    ATENDIDA = "ATENDIDA"  # Estado externo de CU16; no se implementa su flujo.


class ReservationPermission(str, Enum):
    CONSULTAR = "consultar"
    REGISTRAR = "registrar"
    CANCELAR = "cancelar"
    VENCER = "vencer"


@dataclass(frozen=True, slots=True)
class ReservationLine:
    key: InventoryKey
    cantidad: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, InventoryKey):
            raise InvalidReservation("La línea debe referenciar inventario de CU08.")
        if type(self.cantidad) is not int or self.cantidad <= 0:
            raise InvalidReservation("La cantidad reservada debe ser un entero positivo.")


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    id: UUID
    empresa_id: Identifier
    cliente_id: Identifier
    sucursal_id: Identifier
    lineas: tuple[ReservationLine, ...]
    solicitado_en: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidReservation("La solicitud debe identificarse mediante UUID.")
        for identifier in (self.empresa_id, self.cliente_id, self.sucursal_id):
            validate_identifier(identifier)
        if not isinstance(self.lineas, tuple) or not self.lineas:
            raise InvalidReservation("La solicitud debe contener líneas inmutables y no vacías.")
        combined: dict[InventoryKey, int] = {}
        for line in self.lineas:
            if not isinstance(line, ReservationLine):
                raise InvalidReservation("La línea de reserva no es válida.")
            if line.key.empresa_id != self.empresa_id or line.key.sucursal_id != self.sucursal_id:
                raise InvalidReservation("Las variantes deben pertenecer a la empresa y sucursal de la solicitud.")
            combined[line.key] = combined.get(line.key, 0) + line.cantidad
        # Comprobar la cantidad total por variante, incluso si el cliente repite una línea.
        object.__setattr__(self, "lineas", tuple(ReservationLine(key, quantity) for key, quantity in combined.items()))
        object.__setattr__(self, "solicitado_en", utc(self.solicitado_en))

    def same_content(self, other: "ReservationRequest") -> bool:
        return (isinstance(other, ReservationRequest) and self.id == other.id
                and self.empresa_id == other.empresa_id and self.cliente_id == other.cliente_id
                and self.sucursal_id == other.sucursal_id and self.solicitado_en == other.solicitado_en
                and frozenset(self.lineas) == frozenset(other.lineas))


@dataclass(frozen=True, slots=True)
class CustomerReference:
    """Cliente habilitado en la empresa; no presupone un modelo maestro propio."""

    id: Identifier
    empresa_id: Identifier

    def __post_init__(self) -> None:
        validate_identifier(self.id)
        validate_identifier(self.empresa_id)


@dataclass(frozen=True, slots=True)
class ReservationAuthorization:
    actor_id: Identifier
    empresa_id: Identifier
    sucursales: frozenset[Identifier]
    permissions: frozenset[ReservationPermission]
    clientes_permitidos: frozenset[Identifier] | None

    def __post_init__(self) -> None:
        validate_identifier(self.actor_id)
        validate_identifier(self.empresa_id)
        if not isinstance(self.sucursales, frozenset) or not isinstance(self.permissions, frozenset):
            raise ReservationForbidden("El contexto debe utilizar conjuntos inmutables.")
        if self.clientes_permitidos is not None and not isinstance(self.clientes_permitidos, frozenset):
            raise ReservationForbidden("El alcance de clientes no es válido.")
        for identifier in (*self.sucursales, *(self.clientes_permitidos or ())):
            validate_identifier(identifier)
        if any(not isinstance(permission, ReservationPermission) for permission in self.permissions):
            raise ReservationForbidden("El contexto contiene permisos desconocidos.")

    def require(self, request: ReservationRequest, permission: ReservationPermission) -> None:
        if (not isinstance(permission, ReservationPermission) or self.empresa_id != request.empresa_id
                or request.sucursal_id not in self.sucursales or permission not in self.permissions
                or (self.clientes_permitidos is not None and request.cliente_id not in self.clientes_permitidos)):
            raise ReservationForbidden("El actor no tiene permiso sobre la empresa, sucursal o cliente de esta reserva.")


@dataclass(frozen=True, slots=True)
class ReservationEvent:
    actor_id: Identifier
    anterior: ReservationState | None
    posterior: ReservationState
    ocurrido_en: datetime
    motivo: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        validate_identifier(self.actor_id)
        if not isinstance(self.id, UUID) or not isinstance(self.posterior, ReservationState):
            raise InvalidReservation("El evento de reserva no es válido.")
        if self.anterior is not None and not isinstance(self.anterior, ReservationState):
            raise InvalidReservation("El estado anterior no es válido.")
        object.__setattr__(self, "ocurrido_en", utc(self.ocurrido_en))
        if self.motivo is not None:
            object.__setattr__(self, "motivo", _text(self.motivo))


@dataclass(frozen=True, slots=True)
class Reservation:
    request: ReservationRequest
    estado: ReservationState
    actualizado_en: datetime
    codigo: str | None = None
    confirmada_en: datetime | None = None
    vence_en: datetime | None = None
    eventos: tuple[ReservationEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.request, ReservationRequest) or not isinstance(self.estado, ReservationState):
            raise InvalidReservation("La reserva o su estado no son válidos.")
        object.__setattr__(self, "actualizado_en", utc(self.actualizado_en))
        if not isinstance(self.eventos, tuple) or any(not isinstance(event, ReservationEvent) for event in self.eventos):
            raise InvalidReservation("Los eventos deben ser inmutables.")
        confirmed = self.estado in {ReservationState.CONFIRMADA, ReservationState.CANCELADA, ReservationState.VENCIDA, ReservationState.ATENDIDA}
        if confirmed:
            object.__setattr__(self, "codigo", _text(self.codigo))
            confirmed_at, expires_at = utc(self.confirmada_en), utc(self.vence_en)
            if expires_at <= confirmed_at or self.actualizado_en < confirmed_at:
                raise InvalidReservation("El vencimiento debe ser posterior a la confirmación.")
            object.__setattr__(self, "confirmada_en", confirmed_at)
            object.__setattr__(self, "vence_en", expires_at)
        elif self.codigo is not None or self.confirmada_en is not None or self.vence_en is not None:
            raise InvalidReservation("Una solicitud no confirmada no puede tener código ni vencimiento central.")

    @property
    def id(self) -> UUID:
        return self.request.id

    @classmethod
    def pending(cls, request: ReservationRequest) -> "Reservation":
        return cls(request, ReservationState.PENDIENTE_SINCRONIZACION, request.solicitado_en)

    @classmethod
    def confirmed(
        cls, request: ReservationRequest, actor_id: Identifier, codigo: str,
        at: datetime, expires_at: datetime, *, from_pending: bool = False,
    ) -> "Reservation":
        event = ReservationEvent(actor_id, ReservationState.PENDIENTE_SINCRONIZACION if from_pending else None, ReservationState.CONFIRMADA, at)
        return cls(request, ReservationState.CONFIRMADA, at, codigo, at, expires_at, (event,))

    def cancel(self, actor_id: Identifier, at: datetime) -> "Reservation":
        at = utc(at)
        if self.estado is not ReservationState.CONFIRMADA or at >= self.vence_en or at < self.actualizado_en:
            raise InvalidTransition("Solo se puede cancelar una reserva confirmada, no vencida y cancelable.")
        return replace(self, estado=ReservationState.CANCELADA, actualizado_en=at,
                       eventos=(*self.eventos, ReservationEvent(actor_id, self.estado, ReservationState.CANCELADA, at)))

    def expire(self, actor_id: Identifier, at: datetime) -> "Reservation":
        at = utc(at)
        if self.estado is ReservationState.VENCIDA:
            return self
        if self.estado is not ReservationState.CONFIRMADA or at < self.vence_en or at < self.actualizado_en:
            raise InvalidTransition("Solo vence una reserva confirmada cuyo plazo terminó.")
        return replace(self, estado=ReservationState.VENCIDA, actualizado_en=at,
                       eventos=(*self.eventos, ReservationEvent(actor_id, self.estado, ReservationState.VENCIDA, at)))

    def reject(self, actor_id: Identifier, at: datetime, state: ReservationState, reason: str) -> "Reservation":
        if self.estado is not ReservationState.PENDIENTE_SINCRONIZACION or state not in {ReservationState.RECHAZADA, ReservationState.EN_CONFLICTO}:
            raise InvalidTransition("Solo una solicitud pendiente puede rechazarse o quedar en conflicto.")
        return replace(self, estado=state, actualizado_en=at,
                       eventos=(*self.eventos, ReservationEvent(actor_id, self.estado, state, at, _text(reason))))
