"""CU13: clasificación pura de una operación offline antes de validación central.

No persiste ventas/reservas ni actualiza stock. El adaptador futuro deberá
bloquear y comparar por (empresa_id, UUID) en una única transacción.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID


class SyncDecision(str, Enum):
    NUEVA_PENDIENTE_VALIDACION = "NUEVA_PENDIENTE_VALIDACION"
    REPETIDA_MISMO_CONTENIDO = "REPETIDA_MISMO_CONTENIDO"
    CONFLICTO_UUID = "CONFLICTO_UUID"
    DENEGADA = "DENEGADA"


@dataclass(frozen=True)
class OfflineLine:
    variante_id: int
    cantidad: int
    precio_capturado: Decimal

    def __post_init__(self):
        if type(self.variante_id) is not int or self.variante_id <= 0:
            raise ValueError("La variante no es válida.")
        if type(self.cantidad) is not int or not 1 <= self.cantidad <= 100000:
            raise ValueError("La cantidad no es válida.")
        if not isinstance(self.precio_capturado, Decimal) or not self.precio_capturado.is_finite() or self.precio_capturado < 0 or self.precio_capturado.as_tuple().exponent < -2:
            raise ValueError("El precio capturado debe conservar dos decimales como máximo.")


@dataclass(frozen=True)
class OfflineOperation:
    id: UUID
    empresa_id: int
    sucursal_id: int
    tipo: str
    lineas: tuple[OfflineLine, ...]
    capturado_en: datetime

    def __post_init__(self):
        if not isinstance(self.id, UUID) or type(self.empresa_id) is not int or self.empresa_id <= 0:
            raise ValueError("La operación o empresa no son válidas.")
        if type(self.sucursal_id) is not int or self.sucursal_id <= 0:
            raise ValueError("La sucursal no es válida.")
        if self.tipo not in {"RESERVA", "VENTA_CONTADO"} or not isinstance(self.lineas, tuple) or not self.lineas:
            raise ValueError("La operación offline no es válida.")
        if any(not isinstance(line, OfflineLine) for line in self.lineas):
            raise ValueError("Las líneas son inválidas.")
        if not isinstance(self.capturado_en, datetime) or self.capturado_en.utcoffset() is None:
            raise ValueError("La fecha debe incluir zona horaria.")


@dataclass(frozen=True)
class SyncActorContext:
    empresa_id: int
    sucursales_permitidas: frozenset[int]
    rol: str


def classify_offline(
    command: OfflineOperation,
    actor: SyncActorContext,
    previously_stored: OfflineOperation | None,
) -> SyncDecision:
    """Nunca devuelve CONFIRMADA: falta la validación central transaccional."""
    if not isinstance(command, OfflineOperation) or not isinstance(actor, SyncActorContext):
        raise ValueError("Contexto de sincronización inválido.")
    allowed = (
        actor.rol in {"CAJERO", "ENCARGADO_SUCURSAL"}
        and command.empresa_id == actor.empresa_id
        and command.sucursal_id in actor.sucursales_permitidas
    )
    if not allowed:
        return SyncDecision.DENEGADA
    if previously_stored is None:
        return SyncDecision.NUEVA_PENDIENTE_VALIDACION
    # El repositorio del futuro limitará previamente su búsqueda al mismo tenant.
    if previously_stored.empresa_id != command.empresa_id or previously_stored.id != command.id:
        return SyncDecision.DENEGADA
    return SyncDecision.REPETIDA_MISMO_CONTENIDO if previously_stored == command else SyncDecision.CONFLICTO_UUID
