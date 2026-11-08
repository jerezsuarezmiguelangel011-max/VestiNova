"""CU10: pruebas aisladas de reserva. No usa Stripe ni PostgreSQL operativo."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.compras_reservas.reservas import online
from app.models import Cliente, Empresa, Existencia, Producto, Sucursal, VarianteProducto
from app.security import hash_password

PWD = "Clave-de-reserva-de-prueba-2026"


@pytest.fixture
def demo(client, administrator, session_factory):
    with session_factory() as db:
        company = db.scalar(select(Empresa).where(Empresa.slug == "empresa-prueba"))
        branch = Sucursal(empresa_id=company.id, codigo="R01", nombre="Reserva Centro", activo=True)
        product = Producto(empresa_id=company.id, slug="reserva-polera", nombre="Polera test",
                           precio=Decimal("80.10"), activo=True)
        customer = Cliente(empresa_id=company.id, nombre="Cliente Reserva",
                           correo="reserva@vestinova.test", password_hash=hash_password(PWD), activo=True)
        db.add_all([branch, product, customer])
        db.flush()
        variant = VarianteProducto(empresa_id=company.id, producto_id=product.id,
                                   talla="M", color="Blanco", activo=True)
        db.add(variant)
        db.flush()
        db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id, variante_id=variant.id,
                         cantidad=5, cantidad_comprometida=0))
        db.commit()
        ids = company.id, branch.id, variant.id, customer.id
    login = client.post("/api/tiendas/empresa-prueba/cuenta/login", json={
        "correo": "reserva@vestinova.test", "password": PWD,
    })
    assert login.status_code == 200, login.text
    return {"company": ids[0], "branch": ids[1], "variant": ids[2], "customer": ids[3],
            "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
            "base": "/api/tiendas/empresa-prueba/reservas"}


def request(demo, *, id=None, quantity=2, variant=None, branch=None):
    return {
        "id": id or str(uuid4()),
        "sucursal_id": branch or demo["branch"],
        "lineas": [{"variante_id": variant or demo["variant"], "cantidad": quantity}],
    }


def balance(factory, demo):
    with factory() as db:
        return db.get(Existencia, (demo["company"], demo["branch"], demo["variant"]))


def test_confirm_holds_without_physical_deduction(client, demo, session_factory):
    result = client.post(demo["base"], json=request(demo), headers=demo["headers"])
    assert result.status_code == 201, result.text
    assert result.json()["estado"] == "CONFIRMADA"
    assert result.json()["codigo"].startswith("VN-R-")
    row = balance(session_factory, demo)
    assert row.cantidad == 5 and row.cantidad_comprometida == 2


def test_idempotent_retry_does_not_duplicate_hold(client, demo, session_factory):
    payload = request(demo)
    first = client.post(demo["base"], json=payload, headers=demo["headers"])
    second = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert first.status_code == second.status_code == 201
    assert first.json()["codigo"] == second.json()["codigo"]
    assert balance(session_factory, demo).cantidad_comprometida == 2


def test_same_uuid_changed_content_rejected(client, demo, session_factory):
    payload = request(demo)
    client.post(demo["base"], json=payload, headers=demo["headers"])
    payload["lineas"][0]["cantidad"] = 4
    response = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert response.status_code == 409
    assert balance(session_factory, demo).cantidad_comprometida == 2


def test_stock_insufficient_leaves_balance_untouched(client, demo, session_factory):
    response = client.post(demo["base"], json=request(demo, quantity=6), headers=demo["headers"])
    assert response.status_code == 409
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_available_equals_physical_less_committed(client, demo, session_factory):
    one = client.post(demo["base"], json=request(demo, quantity=4), headers=demo["headers"])
    two = client.post(demo["base"], json=request(demo, quantity=2), headers=demo["headers"])
    assert one.status_code == 201 and two.status_code == 409
    assert balance(session_factory, demo).cantidad == 5
    assert balance(session_factory, demo).cantidad_comprometida == 4


def test_cancel_releases_once_and_keeps_history(client, demo, session_factory):
    created = client.post(demo["base"], json=request(demo), headers=demo["headers"]).json()
    url = f"{demo['base']}/{created['id']}/cancelar"
    cancelled = client.post(url, headers=demo["headers"])
    repeated = client.post(url, headers=demo["headers"])
    assert cancelled.status_code == 200 and cancelled.json()["estado"] == "CANCELADA"
    assert repeated.status_code == 409
    row = balance(session_factory, demo)
    assert row.cantidad == 5 and row.cantidad_comprometida == 0
    assert client.get(demo["base"], headers=demo["headers"]).json()[0]["estado"] == "CANCELADA"


def test_expired_reservation_releases_hold(client, demo, session_factory):
    created = client.post(demo["base"], json=request(demo), headers=demo["headers"]).json()
    with session_factory() as db:
        record = db.get(online.ReservationRecord, created["id"])
        record.vence_en = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    result = client.get(demo["base"], headers=demo["headers"])
    assert result.status_code == 200
    assert result.json()[0]["estado"] == "VENCIDA"
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_expired_cannot_be_cancelled_again(client, demo, session_factory):
    created = client.post(demo["base"], json=request(demo), headers=demo["headers"]).json()
    with session_factory() as db:
        db.get(online.ReservationRecord, created["id"]).vence_en = (
            datetime.now(timezone.utc) - timedelta(minutes=5))
        db.commit()
    response = client.post(f"{demo['base']}/{created['id']}/cancelar", headers=demo["headers"])
    assert response.status_code == 409
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_list_requires_client_auth(client, demo):
    assert client.get(demo["base"]).status_code == 401
    assert client.post(demo["base"], json=request(demo)).status_code == 401


@pytest.mark.parametrize("lineas", [[], [{"variante_id": 1, "cantidad": 0}],
                                    [{"variante_id": 1, "cantidad": 101}]])
def test_invalid_lines_rejected(client, demo, lineas):
    payload = request(demo)
    payload["lineas"] = lineas
    result = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert result.status_code == 422


def test_duplicate_variant_rejected(client, demo):
    payload = request(demo)
    payload["lineas"] = [payload["lineas"][0], payload["lineas"][0]]
    assert client.post(demo["base"], json=payload, headers=demo["headers"]).status_code == 422


def test_foreign_variant_and_branch_rejected(client, demo, session_factory):
    with session_factory() as db:
        second = Empresa(slug="otra-empresa-cu10", nombre="Otra empresa", activo=True)
        db.add(second)
        db.flush()
        branch = Sucursal(empresa_id=second.id, codigo="O01", nombre="Sucursal ajena", activo=True)
        product = Producto(empresa_id=second.id, slug="ajeno-cu10", nombre="Producto ajeno",
                           precio=Decimal("11"), activo=True)
        db.add_all([branch, product])
        db.flush()
        variant = VarianteProducto(empresa_id=second.id, producto_id=product.id, talla="S", color="Azul", activo=True)
        db.add(variant)
        db.commit()
        other_branch, other_variant = branch.id, variant.id
    first = client.post(demo["base"], json=request(demo, variant=other_variant), headers=demo["headers"])
    second = client.post(demo["base"], json=request(demo, branch=other_branch), headers=demo["headers"])
    assert first.status_code == 404 and second.status_code == 404
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_customer_cannot_read_other_customer_reservation(client, demo, session_factory):
    created = client.post(demo["base"], json=request(demo), headers=demo["headers"]).json()
    with session_factory() as db:
        other = Cliente(empresa_id=demo["company"], nombre="Otro Cliente",
                        correo="otro-reserva@vestinova.test", password_hash=hash_password(PWD), activo=True)
        db.add(other)
        db.commit()
    login = client.post("/api/tiendas/empresa-prueba/cuenta/login",
                        json={"correo": "otro-reserva@vestinova.test", "password": PWD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"{demo['base']}/{created['id']}", headers=headers).status_code == 404
    assert client.get(demo["base"], headers=headers).json() == []


def test_staff_authorized_branch_and_customer(client, demo, administrator):
    admin_login = client.post("/api/auth/login", json={
        "correo": administrator.correo, "password": " Clave de prueba local 2026 ",
    })
    assert admin_login.status_code == 200, admin_login.text
    headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}",
               "X-Empresa-Id": str(demo["company"])}
    body = request(demo)
    body["cliente_id"] = demo["customer"]
    result = client.post("/api/admin/reservas", json=body, headers=headers)
    assert result.status_code == 201, result.text
    assert client.get("/api/admin/reservas", headers=headers).status_code == 200
    assert client.post(f"/api/admin/reservas/{result.json()['id']}/cancelar",
                       headers=headers).status_code == 200


def test_config_rejects_invalid_expiry(client, demo, monkeypatch):
    monkeypatch.setenv("RESERVATION_TTL_HOURS", "0")
    result = client.post(demo["base"], json=request(demo), headers=demo["headers"])
    assert result.status_code == 503



def test_offline_origin_is_recorded_without_double_hold(client, demo, session_factory):
    payload = request(demo)
    payload.update({"origen": "WEB_OFFLINE", "solicitado_en": "2026-11-07T15:30:00Z"})
    first = client.post(demo["base"], json=payload, headers=demo["headers"])
    second = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with session_factory() as db:
        events = db.get(online.ReservationRecord, payload["id"]).eventos
        assert len(events) == 1
        assert events[0]["origen"] == "WEB_OFFLINE"
    assert balance(session_factory, demo).cantidad_comprometida == 2


def test_multiple_variants_share_one_reservation_and_hold_atomically(client, demo, session_factory):
    with session_factory() as db:
        variant = VarianteProducto(
            empresa_id=demo["company"],
            producto_id=db.get(VarianteProducto, demo["variant"]).producto_id,
            talla="L", color="Blanco", activo=True,
        )
        db.add(variant)
        db.flush()
        variant_id = variant.id
        db.add(Existencia(empresa_id=demo["company"], sucursal_id=demo["branch"],
                         variante_id=variant_id, cantidad=3, cantidad_comprometida=0))
        db.commit()
    payload = request(demo, quantity=2)
    payload["lineas"].append({"variante_id": variant_id, "cantidad": 3})
    result = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert result.status_code == 201, result.text
    assert len(result.json()["lineas"]) == 2
    with session_factory() as db:
        other = db.get(Existencia, (demo["company"], demo["branch"], variant_id))
        assert other.cantidad == 3 and other.cantidad_comprometida == 3
    assert balance(session_factory, demo).cantidad_comprometida == 2
    canceled = client.post(f'{demo["base"]}/{payload["id"]}/cancelar', headers=demo["headers"])
    assert canceled.status_code == 200
    with session_factory() as db:
        assert db.get(Existencia, (demo["company"], demo["branch"], variant_id)).cantidad_comprometida == 0
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_multiple_variants_rejected_all_or_nothing(client, demo, session_factory):
    with session_factory() as db:
        variant = VarianteProducto(
            empresa_id=demo["company"],
            producto_id=db.get(VarianteProducto, demo["variant"]).producto_id,
            talla="XL", color="Blanco", activo=True,
        )
        db.add(variant)
        db.flush()
        variant_id = variant.id
        db.add(Existencia(empresa_id=demo["company"], sucursal_id=demo["branch"],
                         variante_id=variant_id, cantidad=1, cantidad_comprometida=0))
        db.commit()
    payload = request(demo, quantity=2)
    payload["lineas"].append({"variante_id": variant_id, "cantidad": 2})
    result = client.post(demo["base"], json=payload, headers=demo["headers"])
    assert result.status_code == 409
    assert result.json()["detail"]["disponibilidades"] == [
        {"variante_id": variant_id, "disponible": 1, "solicitado": 2}
    ]
    with session_factory() as db:
        assert db.get(Existencia, (demo["company"], demo["branch"], variant_id)).cantidad_comprometida == 0
    assert balance(session_factory, demo).cantidad_comprometida == 0


def test_background_expiry_without_list_call_and_idempotent_retry(client, demo, session_factory):
    created = client.post(demo["base"], json=request(demo), headers=demo["headers"])
    assert created.status_code == 201
    with session_factory() as db:
        db.get(online.ReservationRecord, created.json()["id"]).vence_en = (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        db.commit()
    assert online.expire_all_due(session_factory) == 1
    assert online.expire_all_due(session_factory) == 0
    assert balance(session_factory, demo).cantidad_comprometida == 0
    with session_factory() as db:
        row = db.get(online.ReservationRecord, created.json()["id"])
        assert row.estado == "VENCIDA"
        assert [event["estado"] for event in row.eventos] == ["CONFIRMADA", "VENCIDA"]
