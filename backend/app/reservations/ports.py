from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from app.inventory.domain import Identifier, InventoryKey, StockBalance
from app.inventory.ports import InventoryReferenceResolver
from app.reservations.domain import (
    CustomerReference, Reservation, ReservationAuthorization, ReservationLine, ReservationRequest,
)


class ReservationAuthorizer(Protocol):
    def authorize(self, actor_id: Identifier, empresa_id: Identifier) -> ReservationAuthorization:
        """Verificar identidad, rol y ámbitos reales antes de conceder permisos.

        No interpretar el administrador global actual como administrador de empresa
        ni aceptar roles o ámbitos enviados por el cliente como prueba de acceso.
        """
        ...


class ReservationReferences(InventoryReferenceResolver, Protocol):
    def get_customer(self, cliente_id: Identifier, empresa_id: Identifier) -> CustomerReference | None: ...


class ReservationPolicy(Protocol):
    def expires_at(self, request: ReservationRequest, confirmed_at: datetime) -> datetime:
        """Resolver vencimiento configurado; no existe un plazo predeterminado en CU11."""
        ...

    def ensure_cancelable(self, reservation: Reservation, at: datetime) -> None:
        """Rechazar si la atención u otra condición oficial impide liberar el compromiso."""
        ...


class ReservationRepository(Protocol):
    def get(self, empresa_id: Identifier, reservation_id: UUID) -> Reservation | None:
        """Obtener dentro del ámbito autorizado; bloquear para modificar en el adaptador futuro."""
        ...

    def add(self, reservation: Reservation) -> None:
        """Preparar inserción con UUID y código únicos; nunca sobrescribir una solicitud distinta."""
        ...

    def save(self, reservation: Reservation) -> None: ...


class ReservationInventory(Protocol):
    def get(self, key: InventoryKey) -> StockBalance | None: ...

    def hold(self, reservation_id: UUID, lines: tuple[ReservationLine, ...]) -> None:
        """Revalidar disponibilidad bajo concurrencia y comprometer sin cambiar el físico.

        El adaptador debe participar en la misma unidad de trabajo que la reserva.
        La lectura previa del servicio no sustituye esta comprobación atómica.
        """
        ...

    def release(self, reservation_id: UUID) -> None:
        """Liberar solo las unidades comprometidas por esta reserva, una única vez."""
        ...


class ReservationUnitOfWork(Protocol):
    repository: ReservationRepository
    inventory: ReservationInventory

    def __enter__(self) -> "ReservationUnitOfWork": ...

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        """Revertir reserva y compromisos no confirmados; no suprimir errores."""
        ...

    def commit(self) -> None:
        """Confirmar reserva y compromisos juntos, o fallar sin guardar ninguno."""
        ...
