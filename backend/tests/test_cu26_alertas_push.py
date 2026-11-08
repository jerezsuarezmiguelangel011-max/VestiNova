"""CU26: suscripción exclusiva, transición real de stock y entrega deduplicada."""
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select

from app.compras_reservas import alertas_push as cu26
from app.models import Cliente, Empresa, Existencia, Producto, Sucursal, VarianteProducto
from app.security import hash_password
from decimal import Decimal


def test_cu26_alertas_cola_y_cancelacion(client, session_factory, auth, monkeypatch):
    password = "Clave-CU26-fixture-2026"
    with session_factory() as db:
        company = db.scalar(select(Empresa).where(Empresa.slug == "empresa-prueba"))
        buyer = Cliente(empresa_id=company.id, nombre="Cliente CU26",
                        correo="cu26.cliente@vestinova.test", password_hash=hash_password(password), activo=True)
        branch = Sucursal(empresa_id=company.id, codigo="CU26", nombre="Sucursal CU26", activo=True)
        db.add_all([buyer, branch])
        db.flush()
        product = Producto(empresa_id=company.id, slug="camisa-cu26-hombre",
                           nombre="Camisa de hombre", precio=Decimal("95.00"), moneda="BOB", activo=True)
        db.add(product)
        db.flush()
        variant = VarianteProducto(empresa_id=company.id, producto_id=product.id,
                                  talla="L", color="Gris", activo=True)
        db.add(variant)
        db.flush()
        db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id, variante_id=variant.id,
                          cantidad=0, cantidad_comprometida=0))
        company_id, branch_id, variant_id = company.id, branch.id, variant.id
        db.commit()
    login = client.post("/api/tiendas/empresa-prueba/cuenta/login",
                        json={"correo": "cu26.cliente@vestinova.test", "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    base = "/api/tiendas/empresa-prueba/cuenta/alertas-push"
    alert_data = {"variante_id": variant_id, "sucursal_id": branch_id}
    assert client.post(base + "/avisos", json=alert_data, headers=headers).status_code == 409
    unsafe = client.post(base + "/canales", json={"endpoint": "http://127.0.0.1/push",
                        "keys": {"auth": "A" * 22, "p256dh": "B" * 87}}, headers=headers)
    assert unsafe.status_code == 422
    channel = client.post(base + "/canales", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/vestinova-cu26-prueba",
        "keys": {"auth": "A" * 22, "p256dh": "B" * 87},
    }, headers=headers)
    assert channel.status_code == 201, channel.text
    assert client.post(base + "/canales", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/vestinova-cu26-prueba",
        "keys": {"auth": "A" * 22, "p256dh": "B" * 87},
    }, headers=headers).status_code == 200
    created = client.post(base + "/avisos", json=alert_data, headers=headers)
    assert created.status_code == 201, created.text
    alert_id = created.json()["id"]
    assert client.post(base + "/avisos", json=alert_data, headers=headers).status_code == 409
    listed = client.get(base + "/avisos", headers=headers).json()["items"]
    assert len(listed) == 1
    assert listed[0]["producto_nombre"] == "Camisa de hombre"
    assert listed[0]["producto_slug"] == "camisa-cu26-hombre"
    assert listed[0]["talla"] == "L" and listed[0]["color"] == "Gris"
    assert listed[0]["sucursal_nombre"] == "Sucursal CU26"
    auth_staff = {**auth, "X-Empresa-Id": str(company_id)}
    movement_base = "/api/admin/inventario/movimientos"
    first = client.post(movement_base, json={
        "id": str(uuid4()), "sucursal_id": branch_id, "variante_id": variant_id,
        "tipo": "ENTRADA", "cantidad": 2, "motivo": "Reposición de CU26",
    }, headers=auth_staff)
    assert first.status_code == 201, first.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(cu26.PushOutbox)) == 1

    sent = []
    monkeypatch.setattr(cu26, "_send_webpush", lambda channel, payload, settings: sent.append(payload))
    settings = SimpleNamespace(vapid_public_key="clave-publica-prueba",
                               vapid_private_key="clave-privada-prueba",
                               vapid_contact="mailto:test@vestinova.test")
    cu26.dispatch_pending(session_factory, settings)
    cu26.dispatch_pending(session_factory, settings)
    assert len(sent) == 1
    assert sent[0]["notification"]["title"].startswith("VestiNova")
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(cu26.PushOutbox).where(
            cu26.PushOutbox.estado == "ENVIADO")) == 1
    more = client.post(movement_base, json={
        "id": str(uuid4()), "sucursal_id": branch_id, "variante_id": variant_id,
        "tipo": "ENTRADA", "cantidad": 1, "motivo": "Nueva caja de CU26",
    }, headers=auth_staff)
    assert more.status_code == 201, more.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(cu26.PushOutbox)) == 1
    assert client.post(base + "/avisos", json=alert_data, headers=headers).status_code == 409
    assert client.delete(base + "/avisos/" + str(alert_id), headers=headers).status_code == 204
    assert client.get(base + "/avisos", headers=headers).json()["items"] == []
    with session_factory() as db:
        assert db.get(cu26.AlertaReposicion, alert_id).estado == "CANCELADA"
