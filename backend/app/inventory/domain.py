from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TypeAlias
from uuid import UUID, uuid4


Identifier: TypeAlias = int | str


class InventoryError(Exception):
    """Error de una regla o contrato de inventario."""


class InvalidQuantity(InventoryError):
    pass


class InvalidAdjustment(InventoryError):
    pass


class IncompatibleReference(InventoryError):
    pass


class InventoryForbidden(InventoryError):
    pass


class InventoryNotFound(InventoryError):
    pass


def validate_identifier(value: Identifier) -> None:
    # No convertir tipos: la representación canónica corresponde al adaptador.
    if type(value) is int and value > 0:
        return
    if type(value) is str and value and value == value.strip():
        return
    raise IncompatibleReference("La referencia debe ser un entero positivo o un identificador de texto sin espacios en los extremos.")


def _quantity(value: int) -> None:
    if type(value) is not int or value < 0:
        raise InvalidQuantity("Las cantidades deben ser enteros no negativos; no se admiten booleanos ni fracciones.")


def _reason(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAdjustment("El motivo del ajuste es obligatorio.")
    return value.strip()


@dataclass(frozen=True, slots=True)
class InventoryKey:
    empresa_id: Identifier
    sucursal_id: Identifier
    variante_id: Identifier

    def __post_init__(self) -> None:
        for value in (self.empresa_id, self.sucursal_id, self.variante_id):
            validate_identifier(value)


@dataclass(frozen=True, slots=True)
class BranchReference:
    """Referencia resuelta por CU04; no es una sucursal persistida por CU08."""

    id: Identifier
    empresa_id: Identifier

    def __post_init__(self) -> None:
        validate_identifier(self.id)
        validate_identifier(self.empresa_id)


@dataclass(frozen=True, slots=True)
class VariantReference:
    """Referencia resuelta por CU05; no crea ni sustituye una variante."""

    id: Identifier
    empresa_id: Identifier

    def __post_init__(self) -> None:
        validate_identifier(self.id)
        validate_identifier(self.empresa_id)


class InventoryPermission(str, Enum):
    CONSULTAR = "consultar"
    AJUSTAR = "ajustar"


@dataclass(frozen=True, slots=True)
class InventoryAuthorization:
    """Contexto verificado que deberá proporcionar el adaptador de autorización."""

    actor_id: Identifier
    empresa_id: Identifier
    sucursales: frozenset[Identifier]
    permissions: frozenset[InventoryPermission]

    def __post_init__(self) -> None:
        validate_identifier(self.actor_id)
        validate_identifier(self.empresa_id)
        if not isinstance(self.sucursales, frozenset) or not isinstance(self.permissions, frozenset):
            raise InventoryForbidden("El contexto autorizado debe utilizar conjuntos inmutables.")
        for branch in self.sucursales:
            validate_identifier(branch)
        if any(not isinstance(permission, InventoryPermission) for permission in self.permissions):
            raise InventoryForbidden("El contexto contiene permisos de inventario desconocidos.")

    def require(self, key: InventoryKey, permission: InventoryPermission) -> None:
        if not isinstance(key, InventoryKey):
            raise IncompatibleReference("La clave de inventario no es válida.")
        if (not isinstance(permission, InventoryPermission) or self.empresa_id != key.empresa_id
                or key.sucursal_id not in self.sucursales or permission not in self.permissions):
            raise InventoryForbidden("El actor no tiene permiso para esta operación en la empresa y sucursal indicadas.")


@dataclass(frozen=True, slots=True)
class StockBalance:
    key: InventoryKey
    stock_actual: int
    stock_reservado: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, InventoryKey):
            raise IncompatibleReference("El saldo debe identificar empresa, sucursal y variante.")
        _quantity(self.stock_actual)
        _quantity(self.stock_reservado)
        if self.stock_reservado > self.stock_actual:
            raise InvalidQuantity("El stock reservado no puede superar el stock actual.")

    @property
    def stock_disponible(self) -> int:
        return self.stock_actual - self.stock_reservado

    def adjust_to(self, stock_actual: int) -> "StockBalance":
        _quantity(stock_actual)
        if stock_actual < self.stock_reservado:
            raise InvalidAdjustment("El recuento no puede dejar el stock actual por debajo del reservado.")
        if stock_actual == self.stock_actual:
            raise InvalidAdjustment("El recuento no modifica el stock actual.")
        return StockBalance(self.key, stock_actual, self.stock_reservado)


@dataclass(frozen=True, slots=True)
class AdjustmentCommand:
    key: InventoryKey
    stock_actual_contado: int
    motivo: str
    operacion_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.key, InventoryKey):
            raise IncompatibleReference("El ajuste debe identificar empresa, sucursal y variante.")
        _quantity(self.stock_actual_contado)
        object.__setattr__(self, "motivo", _reason(self.motivo))
        if not isinstance(self.operacion_id, UUID):
            raise InvalidAdjustment("La operación debe identificarse mediante UUID.")


@dataclass(frozen=True, slots=True)
class InventoryMovement:
    id: UUID
    operacion_id: UUID
    key: InventoryKey
    actor_id: Identifier
    ocurrido_en: datetime
    motivo: str
    anterior: StockBalance
    posterior: StockBalance

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.operacion_id, UUID):
            raise InvalidAdjustment("El movimiento y su operación deben identificarse mediante UUID.")
        validate_identifier(self.actor_id)
        if not isinstance(self.key, InventoryKey) or not isinstance(self.anterior, StockBalance) or not isinstance(self.posterior, StockBalance):
            raise IncompatibleReference("La traza debe contener una clave y saldos válidos.")
        if self.anterior.key != self.key or self.posterior.key != self.key:
            raise IncompatibleReference("La traza no puede combinar empresas, sucursales o variantes diferentes.")
        if self.anterior.stock_reservado != self.posterior.stock_reservado:
            raise InvalidAdjustment("Un ajuste de recuento no modifica el stock reservado.")
        if self.anterior.stock_actual == self.posterior.stock_actual:
            raise InvalidAdjustment("Un ajuste debe registrar un cambio de stock actual.")
        if not isinstance(self.ocurrido_en, datetime) or self.ocurrido_en.utcoffset() is None:
            raise InvalidAdjustment("La fecha del movimiento debe incluir zona horaria.")
        object.__setattr__(self, "ocurrido_en", self.ocurrido_en.astimezone(timezone.utc))
        object.__setattr__(self, "motivo", _reason(self.motivo))

    @property
    def tipo(self) -> str:
        return "AJUSTE_RECUENTO"

    @property
    def delta_actual(self) -> int:
        return self.posterior.stock_actual - self.anterior.stock_actual

    @property
    def delta_reservado(self) -> int:
        return self.posterior.stock_reservado - self.anterior.stock_reservado
