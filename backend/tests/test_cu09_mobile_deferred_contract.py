"""Contratos del CU09 diferido sin credenciales Stripe ni transacciones."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.compras_reservas.compras.deferred_mobile import CompraDiferidaInput
from app.compras_reservas.alertas_push import NativeChannelInput


def payload():
    return {
        "id": str(uuid4()),
        "sucursal_id": 1,
        "entrega": "RETIRO",
        "direccion": "",
        "items": [{"producto_id": 1, "variante_id": 2, "cantidad": 1}],
        "importe_aceptado_centavos": 12500,
        "autoriza_cobro_diferido": True,
        "creado_local_en": datetime.now(timezone.utc).isoformat(),
    }


def test_cu09_rechaza_solicitud_sin_consentimiento():
    data = payload()
    data["autoriza_cobro_diferido"] = False
    with pytest.raises(ValidationError):
        CompraDiferidaInput.model_validate(data)


def test_cu09_rechaza_monto_no_positivo():
    data = payload()
    data["importe_aceptado_centavos"] = 0
    with pytest.raises(ValidationError):
        CompraDiferidaInput.model_validate(data)


def test_cu09_rechaza_tarjeta_enviado_desde_flutter():
    data = payload()
    data["tarjeta"] = {"numero": "4242424242424242"}
    with pytest.raises(ValidationError):
        CompraDiferidaInput.model_validate(data)


def test_cu09_rechaza_uuid_con_variantes_duplicadas():
    data = payload()
    data["items"].append(data["items"][0].copy())
    with pytest.raises(ValidationError):
        CompraDiferidaInput.model_validate(data)


def test_cu09_rechaza_fecha_sin_zona():
    data = payload()
    data["creado_local_en"] = "2026-11-08T11:30:00"
    with pytest.raises(ValidationError):
        CompraDiferidaInput.model_validate(data)


def test_cu09_valido_requiere_monto_y_consentimiento():
    result = CompraDiferidaInput.model_validate(payload())
    assert result.autoriza_cobro_diferido
    assert result.importe_aceptado_centavos == 12500


def test_cu26_solo_acepta_token_fcm_y_no_url():
    NativeChannelInput(token="a" * 150 + ":APA91b")
    with pytest.raises(ValidationError):
        NativeChannelInput(token="https://127.0.0.1:8001/admin")
