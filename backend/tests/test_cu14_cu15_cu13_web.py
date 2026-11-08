"""Pruebas de CU14, CU15 y CU13 sobre DB aislada sin cobros reales."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.models import (
    AccesoSucursal, Administrador, Cliente, Empresa, Existencia,
    MembresiaEmpresa, MovimientoInventario, Producto, Sucursal, VarianteProducto,
)
from app.security import hash_password
from app.compras_reservas.reservas.online import ReservationRecord
from app.operacion_sin_conexion.caja.online import CashSale, SyncIncident

PASSWORD = "Clave para pruebas de caja 2026"
ADMIN_PASSWORD = " Clave de prueba local 2026 "


@pytest.fixture
def escenario(client, administrator, session_factory):
    with session_factory() as db:
        company = db.scalar(select(Empresa).where(Empresa.slug == "empresa-prueba"))
        branch = Sucursal(empresa_id=company.id, codigo="C14", nombre="Caja Centro", activo=True)
        product = Producto(empresa_id=company.id, slug="prenda-caja-pruebas",
                           nombre="Polera de caja", precio=Decimal("80.10"), activo=True)
        customer = Cliente(empresa_id=company.id, nombre="Cliente Caja",
                           correo="cliente-caja@vestinova.test",
                           password_hash=hash_password(PASSWORD), activo=True)
        db.add_all([branch, product, customer])
        db.flush()
        variant = VarianteProducto(empresa_id=company.id, producto_id=product.id,
                                   talla="M", color="Rojo", activo=True)
        db.add(variant)
        db.flush()
        db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id,
                         variante_id=variant.id, cantidad=5, cantidad_comprometida=0))
        cashier = Administrador(nombre="Cajero de prueba",
                                correo="cash-cu15@vestinova.test",
                                password_hash=hash_password(PASSWORD), activo=True)
        manager = Administrador(nombre="Encargado de prueba",
                                correo="manager-cu13@vestinova.test",
                                password_hash=hash_password(PASSWORD), activo=True)
        db.add_all([cashier, manager])
        db.flush()
        # Las membresías son la clave foránea compuesta de accesos_sucursal.
        # SQLAlchemy no garantiza el orden de INSERT sin una relación ORM explícita.
        # Persistir las membresías antes de crear los accesos evita errores de FK.
        for staff, role in [(cashier, "CAJERO"), (manager, "ENCARGADO_SUCURSAL")]:
            db.add(MembresiaEmpresa(administrador_id=staff.id, empresa_id=company.id,
                                    rol=role, activo=True))
        db.flush()
        for staff in (cashier, manager):
            db.add(AccesoSucursal(administrador_id=staff.id, empresa_id=company.id,
                                  sucursal_id=branch.id))
        db.commit()
        ids = dict(company=company.id, branch=branch.id, variant=variant.id,
                   customer=customer.id)
    login = client.post("/api/tiendas/empresa-prueba/cuenta/login",
                        json={"correo": "cliente-caja@vestinova.test", "password": PASSWORD})
    assert login.status_code == 200, login.text
    ids["customer_headers"] = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for role in ("cashier", "manager"):
        correo = f"{'cash' if role == 'cashier' else 'manager'}-cu{'15' if role == 'cashier' else '13'}@vestinova.test"
        token = client.post("/api/auth/login", json={"correo": correo, "password": PASSWORD})
        assert token.status_code == 200, token.text
        ids[role + "_headers"] = {
            "Authorization": f"Bearer {token.json()['access_token']}",
            "X-Empresa-Id": str(ids["company"]),
        }
    admin = client.post("/api/auth/login", json={
        "correo": administrator.correo, "password": ADMIN_PASSWORD})
    assert admin.status_code == 200, admin.text
    ids["admin_headers"] = {
        "Authorization": f"Bearer {admin.json()['access_token']}",
        "X-Empresa-Id": str(ids["company"]),
    }
    return ids


def stock(factory, setup):
    with factory() as db:
        row = db.get(Existencia, (setup["company"], setup["branch"], setup["variant"]))
        return row.cantidad, row.cantidad_comprometida


def reserva(client, setup, *, quantity=2, offline=False):
    body = {"id": str(uuid4()), "sucursal_id": setup["branch"],
            "lineas": [{"variante_id": setup["variant"], "cantidad": quantity}]}
    if offline:
        body.update({"origen": "WEB_OFFLINE", "solicitado_en": datetime.now(timezone.utc).isoformat()})
    return body


def venta(setup, *, qty=2, unit="80.10", received="200.00", offline=False, ident=None):
    return {"id": ident or str(uuid4()), "sucursal_id": setup["branch"],
            "cliente_id": setup["customer"],
            "lineas": [{"variante_id": setup["variant"], "cantidad": qty,
                        "precio_unitario": unit}],
            "efectivo": received, "origen": "WEB_OFFLINE" if offline else "EN_LINEA",
            "efectivo_cobrado": offline, "entrega_local": False,
            "creada_local_en": datetime.now(timezone.utc).isoformat() if offline else None}


def test_cu14_entrega_descuenta_fisico_y_libera_compromiso_una_vez(client, escenario, session_factory):
    setup = escenario
    created = client.post("/api/tiendas/empresa-prueba/reservas", json=reserva(client, setup),
                          headers=setup["customer_headers"])
    assert created.status_code == 201, created.text
    reservation = created.json()
    assert stock(session_factory, setup) == (5, 2)
    path = f"/api/admin/atencion-reservas/{reservation['id']}/entregar"
    rejected = client.post(path, json={"identidad_verificada": False, "comprobacion": "No verificado"},
                           headers=setup["cashier_headers"])
    assert rejected.status_code == 422
    delivered = client.post(path, json={"identidad_verificada": True,
                                        "comprobacion": "Código confirmado presencialmente"},
                            headers=setup["cashier_headers"])
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["estado"] == "ATENDIDA"
    assert stock(session_factory, setup) == (3, 0)
    repeated = client.post(path, json={"identidad_verificada": True,
                                       "comprobacion": "Código confirmado presencialmente"},
                           headers=setup["cashier_headers"])
    assert repeated.status_code == 200
    assert stock(session_factory, setup) == (3, 0)
    with session_factory() as db:
        row = db.get(ReservationRecord, reservation["id"])
        assert [event["estado"] for event in row.eventos] == ["CONFIRMADA", "ATENDIDA"]
        movements = db.scalars(select(MovimientoInventario).where(
            MovimientoInventario.empresa_id == setup["company"],
            MovimientoInventario.motivo.like("CU14:%"))).all()
        assert len(movements) == 1 and movements[0].delta == -2


def test_cu14_cancelacion_con_motivo_y_denegacion_otras_acciones(client, escenario, session_factory):
    setup = escenario
    create = client.post("/api/tiendas/empresa-prueba/reservas",
                         json=reserva(client, setup), headers=setup["customer_headers"])
    assert create.status_code == 201
    reservation_id = create.json()["id"]
    path = f"/api/admin/atencion-reservas/{reservation_id}/cancelar"
    canceled = client.post(path, json={"motivo": "Cliente no podrá retirar en el plazo"},
                           headers=setup["manager_headers"])
    assert canceled.status_code == 200, canceled.text
    assert stock(session_factory, setup) == (5, 0)
    with session_factory() as db:
        row = db.get(ReservationRecord, reservation_id)
        assert row.eventos[-1]["motivo"] == "Cliente no podrá retirar en el plazo"
    second = client.post(path, json={"motivo": "Otro motivo de cancelación"},
                         headers=setup["manager_headers"])
    assert second.status_code == 409
    denied = client.post(f"/api/admin/atencion-reservas/{reservation_id}/entregar",
                         json={"identidad_verificada": True, "comprobacion": "Código correcto"},
                         headers=setup["admin_headers"])
    assert denied.status_code == 403
    assert stock(session_factory, setup) == (5, 0)


def test_cu15_venta_efectivo_movimiento_y_uuid_idempotente(client, escenario, session_factory):
    setup = escenario
    payload = venta(setup)
    first = client.post("/api/admin/caja/ventas", json=payload,
                        headers=setup["cashier_headers"])
    assert first.status_code == 201, first.text
    assert first.json()["estado"] == "CONFIRMADA"
    assert first.json()["total"] == "160.20"
    assert first.json()["cambio"] == "39.80"
    assert stock(session_factory, setup) == (3, 0)
    duplicate = client.post("/api/admin/caja/ventas", json=payload,
                            headers=setup["cashier_headers"])
    assert duplicate.status_code == 200
    assert duplicate.json()["codigo"] == first.json()["codigo"]
    assert stock(session_factory, setup) == (3, 0)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CashSale)) == 1
        movements = db.scalars(select(MovimientoInventario).where(
            MovimientoInventario.motivo.like("CU15:%"))).all()
        assert len(movements) == 1 and movements[0].delta == -2


def test_cu15_offline_stock_conflict_keeps_cash_original_and_allows_reconciliation(
    client, escenario, session_factory,
):
    setup = escenario
    payload = venta(setup, qty=6, received="500.00", offline=True)
    first = client.post("/api/admin/caja/ventas", json=payload,
                        headers=setup["cashier_headers"])
    assert first.status_code == 409, first.text
    incident_id = first.json()["detail"]["incidencia_id"]
    assert stock(session_factory, setup) == (5, 0)
    duplicate = client.post("/api/admin/caja/ventas", json=payload,
                            headers=setup["cashier_headers"])
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["incidencia_id"] == incident_id
    with session_factory() as db:
        row = db.get(SyncIncident, incident_id)
        assert row.estado == "CONFLICTO"
        assert row.datos_originales["efectivo"] == "500.00"
        assert row.datos_originales["lineas"][0]["cantidad"] == 6
        assert db.scalar(select(func.count()).select_from(CashSale)) == 0
    path = f"/api/admin/conciliacion/{incident_id}/resolver"
    resolution = {"decision": "DEVOLUCION_DOCUMENTADA",
                  "referencia_constancia": "RECIBO-2026-01",
                  "observacion": "El cliente recibió devolución de efectivo según recibo firmado."}
    assert client.post(path, json=resolution, headers=setup["cashier_headers"]).status_code == 403
    solved = client.post(path, json=resolution, headers=setup["manager_headers"])
    assert solved.status_code == 200, solved.text
    assert solved.json()["estado"] == "RESUELTO"
    repeated = client.post(path, json=resolution, headers=setup["manager_headers"])
    assert repeated.status_code == 200
    assert stock(session_factory, setup) == (5, 0)


def test_cu15_price_mismatch_offline_remains_conflict(client, escenario, session_factory):
    setup = escenario
    payload = venta(setup, unit="70.00", offline=True)
    failure = client.post("/api/admin/caja/ventas", json=payload,
                          headers=setup["cashier_headers"])
    assert failure.status_code == 409, failure.text
    assert "precios" in failure.json()["detail"]["mensaje"]
    assert stock(session_factory, setup) == (5, 0)


def test_cu13_conflicto_reserva_cliente_aparece_solo_en_sucursal_autorizada(
    client, escenario, session_factory,
):
    setup = escenario
    payload = reserva(client, setup, quantity=8, offline=True)
    rejected = client.post("/api/tiendas/empresa-prueba/reservas",
                           json=payload, headers=setup["customer_headers"])
    assert rejected.status_code == 409, rejected.text
    incident_id = rejected.json()["detail"]["incidencia_id"]
    assert stock(session_factory, setup) == (5, 0)
    manager = client.get("/api/admin/conciliacion", headers=setup["manager_headers"])
    assert manager.status_code == 200
    assert any(r["id"] == incident_id and r["tipo"] == "RESERVA" for r in manager.json())
    assert client.get("/api/admin/conciliacion", headers=setup["cashier_headers"]).status_code == 403


def test_cu15_uuid_reused_with_different_cash_rejected(client, escenario, session_factory):
    payload = venta(escenario)
    url = "/api/admin/caja/ventas"
    assert client.post(url, json=payload, headers=escenario["cashier_headers"]).status_code == 201
    payload["efectivo"] = "300.00"
    denied = client.post(url, json=payload, headers=escenario["cashier_headers"])
    assert denied.status_code == 409
    assert stock(session_factory, escenario) == (3, 0)


def test_cu15_insufficient_cash_rejected_without_physical_output(client, escenario, session_factory):
    payload = venta(escenario, received="50.00")
    denied = client.post("/api/admin/caja/ventas", json=payload,
                         headers=escenario["cashier_headers"])
    assert denied.status_code == 422
    assert stock(session_factory, escenario) == (5, 0)


def test_cu14_expired_reservation_cannot_be_delivered(client, escenario, session_factory):
    payload = reserva(client, escenario)
    created = client.post("/api/tiendas/empresa-prueba/reservas", json=payload,
                          headers=escenario["customer_headers"])
    assert created.status_code == 201
    with session_factory() as db:
        db.get(ReservationRecord, payload["id"]).vence_en = (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        db.commit()
    response = client.post(
        f"/api/admin/atencion-reservas/{payload['id']}/entregar",
        json={"identidad_verificada": True, "comprobacion": "Código validado"},
        headers=escenario["cashier_headers"])
    assert response.status_code == 409
    assert stock(session_factory, escenario) == (5, 0)


def test_cu13_resolution_requires_evidence_and_is_immutable(client, escenario):
    payload = venta(escenario, qty=8, received="700.00", offline=True)
    result = client.post("/api/admin/caja/ventas", json=payload,
                         headers=escenario["cashier_headers"])
    assert result.status_code == 409
    incident = result.json()["detail"]["incidencia_id"]
    path = f"/api/admin/conciliacion/{incident}/resolver"
    invalid = client.post(path, json={
        "decision": "DEVOLUCION_DOCUMENTADA",
        "referencia_constancia": "x",
        "observacion": "devolución",
    }, headers=escenario["manager_headers"])
    assert invalid.status_code == 422
    accepted = {
        "decision": "ACUERDO_DOCUMENTADO",
        "referencia_constancia": "ACTA-CU13-001",
        "observacion": "El cliente aceptó la fecha alternativa registrada en acta.",
    }
    assert client.post(path, json=accepted,
                       headers=escenario["manager_headers"]).status_code == 200
    accepted["decision"] = "ENTREGA_ALTERNATIVA_DOCUMENTADA"
    assert client.post(path, json=accepted,
                       headers=escenario["manager_headers"]).status_code == 409


def test_cu14_busqueda_trae_confirmadas_y_detalle_humano_por_sucursal(client, escenario):
    """La atención se abre desde una lista filtrada, con nombres y estado central."""
    setup = escenario
    first = client.post("/api/tiendas/empresa-prueba/reservas",
                        json=reserva(client, setup),
                        headers=setup["customer_headers"])
    second = client.post("/api/tiendas/empresa-prueba/reservas",
                         json=reserva(client, setup, quantity=1),
                         headers=setup["customer_headers"])
    assert first.status_code == 201 and second.status_code == 201
    cancelled_id = second.json()["id"]
    cancelled = client.post(
        f"/api/tiendas/empresa-prueba/reservas/{cancelled_id}/cancelar",
        headers=setup["customer_headers"])
    assert cancelled.status_code == 200

    base = "/api/admin/atencion-reservas"
    active = client.get(base, headers=setup["cashier_headers"])
    assert active.status_code == 200, active.text
    assert len(active.json()) == 1
    item = active.json()[0]
    assert item["id"] == first.json()["id"]
    assert item["cliente_nombre"] == "Cliente Caja"
    assert item["sucursal_nombre"] == "Caja Centro"
    assert item["lineas"][0]["producto_nombre"] == "Polera de caja"
    assert item["lineas"][0]["talla"] == "M"

    detail = client.get(f"{base}/{item['id']}", headers=setup["cashier_headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["codigo"] == item["codigo"]
    assert detail.json()["lineas"][0]["cantidad"] == 2
    assert detail.json()["eventos"][0]["estado"] == "CONFIRMADA"

    history = client.get(f"{base}?estado=TODAS", headers=setup["cashier_headers"])
    assert history.status_code == 200
    assert {r["estado"] for r in history.json()} == {"CONFIRMADA", "CANCELADA"}

    cancelled_only = client.get(f"{base}?estado=CANCELADA", headers=setup["cashier_headers"])
    assert cancelled_only.status_code == 200
    assert [r["id"] for r in cancelled_only.json()] == [cancelled_id]

    by_code = client.get(
        f"{base}?codigo={item['codigo']}&cliente_id={setup['customer']}&sucursal_id={setup['branch']}",
        headers=setup["cashier_headers"])
    assert by_code.status_code == 200
    assert len(by_code.json()) == 1
    assert by_code.json()[0]["id"] == item["id"]
