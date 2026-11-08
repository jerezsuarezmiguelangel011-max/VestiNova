"""CU09 móvil: Stripe TEST simulada, sin tarjetas reales ni red externa.

Comprueba pago diferido, idempotencia, historial CU25 y stock.
"""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.compras_reservas.compras import deferred_mobile as cu09_offline
from app.compras_reservas.compras.persistence import PurchaseRecord
from app.models import Existencia

from tests.test_cu09_stripe_flujos_alternativos import caso_cu09


@pytest.fixture
def deferred_case(caso_cu09, monkeypatch):
    case = caso_cu09
    calls = []
    monkeypatch.setattr(cu09_offline, "_stripe", lambda: "sk_test_diferido_falso")
    monkeypatch.setattr(cu09_offline, "_verify_method",
                        lambda db, row, key: ("visa", "4242") if row else None)
    with case.sf() as db:
        db.add(cu09_offline.MetodoDiferido(
            empresa_id=case.ids["empresa"],
            cliente_id=case.ids["cliente"],
            stripe_customer_id="cus_test_diferido",
            payment_method_id="pm_test_autorizado",
        ))
        db.commit()

    def payment_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="pi_diferido_test", status="succeeded",
                               amount=kwargs["amount"], currency=kwargs["currency"],
                               customer=kwargs["customer"])

    monkeypatch.setattr(cu09_offline.stripe.PaymentIntent, "create",
                        payment_create)
    return case, calls


def offline_request(case, *, compra_id=None, amount=8010, qty=1,
                    product_id=None, variant_id=None):
    request = {
        "id": compra_id or str(uuid4()),
        "sucursal_id": case.ids["sucursal"],
        "entrega": "RETIRO",
        "direccion": "",
        "items": [{
            "producto_id": product_id or case.ids["producto"],
            "variante_id": variant_id or case.ids["variante"],
            "cantidad": qty,
        }],
        "importe_aceptado_centavos": amount,
        "autoriza_cobro_diferido": True,
        "creado_local_en": datetime.now(timezone.utc).isoformat(),
    }
    return request


def test_cu09_offline_confirmada_aparece_en_mis_compras_y_no_duplica_cobro(deferred_case):
    c, calls = deferred_case
    payload = offline_request(c)
    url = c.url + "/offline/sincronizar"

    first = c.client.post(url, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["estado"] == "CONFIRMADA"
    assert first.json()["pago_verificado"] is True
    assert first.json()["reserva_confirmada"] is False

    second = c.client.post(url, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["estado"] == "CONFIRMADA"
    assert len(calls) == 1
    assert calls[0]["amount"] == 8010
    assert calls[0]["currency"] == "bob"
    assert calls[0]["off_session"] is True
    assert calls[0]["idempotency_key"] == f"vestinova-offline-cu09-{payload['id']}"

    history = c.client.get(
        f"/api/tiendas/cu09-prueba-andina/cuenta/compras",
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 1
    receipt = history.json()["items"][0]
    assert receipt["id"] == payload["id"]
    assert receipt["estado"] == "CONFIRMADA"
    assert receipt["seguimiento_entrega"] == "PENDIENTE"
    assert receipt["importe_total"] == "80.10"
    assert receipt["items"][0]["nombre"] == "Polera clásica"
    with c.sf() as db:
        stock = db.get(Existencia, (
            c.ids["empresa"], c.ids["sucursal"], c.ids["variante"],
        ))
        assert stock.cantidad == 11
        assert db.get(PurchaseRecord, payload["id"]) is not None


def test_cu09_offline_rechaza_importe_cambiado_sin_cobro(deferred_case):
    c, calls = deferred_case
    payload = offline_request(c, amount=7999)
    response = c.client.post(c.url + "/offline/sincronizar", json=payload)
    assert response.status_code == 409, response.text
    assert "precio" in str(response.json()).lower()
    assert not calls
    with c.sf() as db:
        assert db.get(PurchaseRecord, payload["id"]) is None


def test_cu09_offline_rechaza_stock_insuficiente_y_otra_empresa(deferred_case):
    c, calls = deferred_case
    wrong = offline_request(c,
        product_id=c.ids["producto_otro"],
        variant_id=c.ids["variante_otra"])
    foreign = c.client.post(c.url + "/offline/sincronizar", json=wrong)
    assert foreign.status_code == 409
    with c.sf() as db:
        stock = db.get(Existencia, (
            c.ids["empresa"], c.ids["sucursal"], c.ids["variante"],
        ))
        stock.cantidad_comprometida = stock.cantidad
        db.commit()
    out_of_stock = c.client.post(c.url + "/offline/sincronizar",
                                 json=offline_request(c))
    assert out_of_stock.status_code == 409
    assert not calls
