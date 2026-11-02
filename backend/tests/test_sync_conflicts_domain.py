from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.operacion_sin_conexion.conflictos_sincronizacion.domain import (
    OfflineLine, OfflineOperation, SyncActorContext, SyncDecision, classify_offline,
)


NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def operation():
    return OfflineOperation(
        id=uuid4(), empresa_id=1, sucursal_id=2, tipo="VENTA_CONTADO",
        lineas=(OfflineLine(9, 2, Decimal("149.90")),), capturado_en=NOW,
    )


def test_new_operation_is_only_pending_not_confirmed():
    item = operation()
    staff = SyncActorContext(empresa_id=1, sucursales_permitidas=frozenset({2}), rol="CAJERO")
    assert classify_offline(item, staff, None) is SyncDecision.NUEVA_PENDIENTE_VALIDACION
    assert classify_offline(item, staff, item) is SyncDecision.REPETIDA_MISMO_CONTENIDO


def test_same_uuid_different_payload_is_conflict():
    from dataclasses import replace
    item = operation()
    modified = replace(item, lineas=(OfflineLine(9, 3, Decimal("149.90")),))
    staff = SyncActorContext(1, frozenset({2}), "CAJERO")
    assert classify_offline(modified, staff, item) is SyncDecision.CONFLICTO_UUID


@pytest.mark.parametrize("actor", [
    SyncActorContext(2, frozenset({2}), "CAJERO"),
    SyncActorContext(1, frozenset({3}), "CAJERO"),
    SyncActorContext(1, frozenset({2}), "OPERADOR"),
])
def test_rejects_other_company_branch_or_role(actor):
    assert classify_offline(operation(), actor, None) is SyncDecision.DENEGADA


def test_rejects_invalid_input_values():
    for price in [Decimal("NaN"), Decimal("-1.00"), Decimal("1.234")]:
        with pytest.raises(ValueError):
            OfflineLine(1, 2, price)
    with pytest.raises(ValueError):
        OfflineLine(1, 0, Decimal("1.00"))
