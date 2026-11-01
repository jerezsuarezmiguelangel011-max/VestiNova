from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import UUID

from app.inventory.domain import Identifier, InventoryKey, validate_identifier


class PurchaseError(Exception):
    pass


class PurchaseInvalid(PurchaseError):
    pass


class PurchaseForbidden(PurchaseError):
    pass


class PurchaseConflict(PurchaseError):
    pass


class PurchaseUnavailable(PurchaseError):
    pass


def identifier_token(value: Identifier) -> str:
    validate_identifier(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PurchaseItem:
    producto_id: int
    cantidad: int

    def __post_init__(self) -> None:
        if type(self.producto_id) is not int or self.producto_id <= 0:
            raise PurchaseInvalid("El producto debe tener un identificador válido.")
        if type(self.cantidad) is not int or not 1 <= self.cantidad <= 2147483647:
            raise PurchaseInvalid("La cantidad debe ser un entero positivo válido.")


@dataclass(frozen=True, slots=True)
class PurchaseCommand:
    id: UUID
    items: tuple[PurchaseItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.items, tuple) or not self.items:
            raise PurchaseInvalid("La compra requiere UUID y prendas seleccionadas.")
        combined: dict[int, int] = {}
        for item in self.items:
            if not isinstance(item, PurchaseItem):
                raise PurchaseInvalid("La selección no es válida.")
            combined[item.producto_id] = combined.get(item.producto_id, 0) + item.cantidad
        object.__setattr__(self, "items", tuple(PurchaseItem(product, quantity) for product, quantity in sorted(combined.items())))

    @property
    def fingerprint(self) -> str:
        payload = json.dumps([(item.producto_id, item.cantidad) for item in self.items], separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PurchaseContext:
    actor_id: Identifier
    empresa_id: Identifier
    cliente_id: Identifier
    sucursal_id: Identifier

    def __post_init__(self) -> None:
        for identifier in (self.actor_id, self.empresa_id, self.cliente_id, self.sucursal_id):
            validate_identifier(identifier)


@dataclass(frozen=True, slots=True)
class PurchaseLine:
    key: InventoryKey
    producto_id: int
    nombre: str
    cantidad: int
    precio_unitario: Decimal

    def __post_init__(self) -> None:
        PurchaseItem(self.producto_id, self.cantidad)
        if not isinstance(self.key, InventoryKey) or not isinstance(self.nombre, str) or not self.nombre.strip():
            raise PurchaseInvalid("La oferta de la prenda no es válida.")
        price = self.precio_unitario
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0 or price > Decimal("99999999.99") or price.as_tuple().exponent < -2:
            raise PurchaseInvalid("El precio debe ser decimal positivo con hasta dos decimales.")

    @property
    def subtotal(self) -> Decimal:
        return self.precio_unitario * self.cantidad


@dataclass(frozen=True, slots=True)
class Purchase:
    id: UUID
    context: PurchaseContext
    fingerprint: str
    lines: tuple[PurchaseLine, ...]
    creado_en: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.context, PurchaseContext) or not isinstance(self.lines, tuple) or not self.lines:
            raise PurchaseInvalid("La compra no es válida.")
        if not isinstance(self.creado_en, datetime) or self.creado_en.utcoffset() is None:
            raise PurchaseInvalid("La fecha de compra debe incluir zona horaria.")
        object.__setattr__(self, "creado_en", self.creado_en.astimezone(timezone.utc))
        for line in self.lines:
            if not isinstance(line, PurchaseLine) or line.key.empresa_id != self.context.empresa_id or line.key.sucursal_id != self.context.sucursal_id:
                raise PurchaseForbidden("La oferta no corresponde a la empresa y sucursal autorizadas.")
        if len({line.producto_id for line in self.lines}) != len(self.lines):
            raise PurchaseInvalid("La oferta debe devolver una línea por producto seleccionado.")
        expected = PurchaseCommand(self.id, tuple(PurchaseItem(line.producto_id, line.cantidad) for line in self.lines)).fingerprint
        if expected != self.fingerprint:
            raise PurchaseInvalid("La compra no coincide con su solicitud.")

    @property
    def total(self) -> Decimal:
        return sum((line.subtotal for line in self.lines), Decimal("0.00"))
