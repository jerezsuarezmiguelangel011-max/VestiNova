r"""CU09: pruebas aisladas de checkout y webhook, sin tarjetas, red ni PostgreSQL real.

Ejecutar desde backend:
    .\.venv\Scripts\python.exe -m pytest -q tests/test_cu09_stripe_flujos_alternativos.py

Usa fixtures SQLite de tests/conftest.py, mock de Stripe y nunca lee .env.
No verifica la firma criptografica real: esa parte requiere Stripe Sandbox.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi import Depends
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import stripe

from app.autenticacion_usuarios.customer_auth import current_customer_session
from app.compras_reservas.compras import stripe_checkout as cu09
from app.compras_reservas.compras.persistence import PurchaseLineRecord, PurchaseRecord
from app.db import get_db
from app.models import (
    Cliente, Empresa, Existencia, MovimientoInventario, PlanSaaS,
    Producto, Sucursal, SuscripcionEmpresa, VarianteProducto,
)


def activate_test_subscription(db: Session, empresa_id: int) -> None:
    """Plan SaaS aislado en la base de pruebas, sin importar conftest."""
    plan = db.scalar(select(PlanSaaS).where(PlanSaaS.codigo == "BASICO"))
    if plan is None:
        plan = PlanSaaS(
            codigo="BASICO", nombre="Básico de pruebas",
            descripcion="Plan aislado para CU09", max_sucursales=1000,
            max_productos=1000, max_usuarios=1000, activo=True,
        )
        db.add(plan)
        db.flush()
    db.add(SuscripcionEmpresa(
        empresa_id=empresa_id, plan_id=plan.id, estado="ACTIVA",
        inicia_en=datetime.now(timezone.utc) - timedelta(days=1),
    ))


@pytest.fixture
def caso_cu09(client, session_factory, monkeypatch):
    """Crea dos tiendas aisladas y simula exclusivamente la API de Stripe."""
    with session_factory() as db:
        a = Empresa(slug="cu09-prueba-andina", nombre="Andina CU09", activo=True)
        b = Empresa(slug="cu09-prueba-urbana", nombre="Urbana CU09", activo=True)
        db.add_all([a, b])
        db.flush()
        activate_test_subscription(db, a.id)
        activate_test_subscription(db, b.id)
        cliente = Cliente(empresa_id=a.id, nombre="Cliente de prueba", correo="test-cu09@ejemplo.test",
                          password_hash="sin-login-en-fixture", activo=True)
        sucursal_a = Sucursal(empresa_id=a.id, codigo="CENTRO", nombre="Centro", activo=True)
        sucursal_b = Sucursal(empresa_id=b.id, codigo="URBANA", nombre="Urbana", activo=True)
        db.add_all([cliente, sucursal_a, sucursal_b])
        db.flush()
        producto_a = Producto(empresa_id=a.id, slug="polera-test-cu09", nombre="Polera clásica",
                              precio=Decimal("80.10"), moneda="BOB", activo=True)
        producto_b = Producto(empresa_id=b.id, slug="prenda-externa-cu09", nombre="Prenda externa",
                              precio=Decimal("90.00"), moneda="BOB", activo=True)
        db.add_all([producto_a, producto_b])
        db.flush()
        variante_a = VarianteProducto(empresa_id=a.id, producto_id=producto_a.id,
                                     talla="M", color="Blanco", activo=True)
        variante_b = VarianteProducto(empresa_id=b.id, producto_id=producto_b.id,
                                     talla="M", color="Negro", activo=True)
        db.add_all([variante_a, variante_b])
        db.flush()
        db.add_all([
            Existencia(empresa_id=a.id, sucursal_id=sucursal_a.id, variante_id=variante_a.id,
                       cantidad=12, cantidad_comprometida=0),
            Existencia(empresa_id=b.id, sucursal_id=sucursal_b.id, variante_id=variante_b.id,
                       cantidad=6, cantidad_comprometida=0),
        ])
        ids = dict(empresa=a.id, empresa_otra=b.id, cliente=cliente.id, sucursal=sucursal_a.id,
                   sucursal_otra=sucursal_b.id, producto=producto_a.id, producto_otro=producto_b.id,
                   variante=variante_a.id, variante_otra=variante_b.id)
        db.commit()

    def identidad_simulada(db: Session = Depends(get_db)):
        return db.get(Cliente, ids["cliente"]), None, db.get(Empresa, ids["empresa"])

    client.app.dependency_overrides[current_customer_session] = identidad_simulada
    monkeypatch.setattr(cu09, "_configuration", lambda: ("sk_test_falsa", "whsec_falso"))
    llamadas = []
    sesiones = {}

    def crear_sesion(**kwargs):
        llamadas.append(kwargs)
        sid = "cs_test_" + uuid4().hex
        sesion = SimpleNamespace(id=sid, url="https://checkout.stripe.com/c/pay/" + sid,
                                  status="open")
        sesiones[sid] = sesion
        return sesion

    def recuperar_sesion(sid, **_kwargs):
        return sesiones[sid]

    monkeypatch.setattr(cu09.stripe.checkout.Session, "create", crear_sesion)
    monkeypatch.setattr(cu09.stripe.checkout.Session, "retrieve", recuperar_sesion)
    evento = {"actual": None}

    def verificar_evento(_raw, firma, _secret):
        if firma != "firma-simulada-valida":
            raise stripe.SignatureVerificationError("Firma de prueba invalida", str(firma))
        return evento["actual"]

    monkeypatch.setattr(cu09.stripe.Webhook, "construct_event", verificar_evento)
    caso = SimpleNamespace(client=client, sf=session_factory, ids=ids, llamadas=llamadas,
                           sesiones=sesiones, evento=evento,
                           url=f"/api/tiendas/{a.slug}/compras")
    yield caso
    client.app.dependency_overrides.pop(current_customer_session, None)


def pedir_pago(caso, *, compra_id=None, cantidad=1, producto=None, variante=None, sucursal=None):
    payload = dict(
        id=compra_id or str(uuid4()),
        sucursal_id=sucursal if sucursal is not None else caso.ids["sucursal"],
        entrega="RETIRO", direccion="",
        items=[dict(producto_id=producto if producto is not None else caso.ids["producto"],
                    variante_id=variante if variante is not None else caso.ids["variante"],
                    cantidad=cantidad)],
    )
    return caso.client.post(caso.url + "/checkout", json=payload), payload


def evento_de(caso, payload, checkout, *, tipo="checkout.session.completed", pagado=True,
              monto=8010, session_id=None, referencia=None, moneda="bob", meta=None):
    caso.evento["actual"] = {
        "type": tipo,
        "data": {"object": {
            "id": session_id or checkout["id"],
            "client_reference_id": referencia or payload["id"],
            "payment_status": "paid" if pagado else "unpaid",
            "amount_total": monto, "currency": moneda,
            "metadata": meta if meta is not None else {"compra_id": payload["id"]},
            "payment_intent": "pi_ficticio",
        }},
    }
    return caso.client.post("/api/webhooks/stripe", content=b'{}',
                            headers={"stripe-signature": "firma-simulada-valida"})


def estado_db(caso, compra_id):
    with caso.sf() as db:
        saldo = db.get(Existencia, (caso.ids["empresa"], caso.ids["sucursal"], caso.ids["variante"]))
        intento = db.get(cu09.CheckoutAttempt, compra_id)
        compra = db.get(PurchaseRecord, compra_id)
        lineas = db.scalar(select(func.count()).select_from(PurchaseLineRecord).where(
            PurchaseLineRecord.compra_id == compra_id))
        movimientos = db.scalars(select(MovimientoInventario).where(
            MovimientoInventario.motivo == "Compra digital " + compra_id)).all()
        return dict(stock=saldo.cantidad, comprometido=saldo.cantidad_comprometida,
                    estado=intento.estado if intento else None,
                    total=compra.total if compra else None, lineas=lineas,
                    movimientos=[(mov.tipo, mov.delta, mov.saldo_resultante) for mov in movimientos])


def test_cu09_sin_stock_no_inicia_pago(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c, cantidad=13)
    assert respuesta.status_code == 409
    assert not c.llamadas
    assert estado_db(c, payload["id"])["estado"] is None


def test_cu09_no_cruza_productos_entre_empresas(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c, producto=c.ids["producto_otro"], variante=c.ids["variante_otra"])
    assert respuesta.status_code == 409
    assert not c.llamadas
    assert estado_db(c, payload["id"])["stock"] == 12


def test_cu09_sesion_abierta_o_cancelada_no_confirma_ni_descuenta(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "PAGO_PENDIENTE"
    assert respuesta.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert estado_db(c, payload["id"]) == dict(
        stock=12, comprometido=0, estado="PAGO_PENDIENTE",
        total=None, lineas=0, movimientos=[])
    # Volver desde cancel_url no confirma ni toca la base; solo eventos firmados cambian estados.


def test_cu09_reintento_mismo_uuid_reutiliza_sesion_sin_nuevo_cargo(caso_cu09):
    c = caso_cu09
    compra_id = str(uuid4())
    primera, payload = pedir_pago(c, compra_id=compra_id)
    segunda, _ = pedir_pago(c, compra_id=compra_id)
    assert primera.status_code == segunda.status_code == 201
    assert primera.json()["checkout_url"] == segunda.json()["checkout_url"]
    assert len(c.llamadas) == 1
    assert estado_db(c, payload["id"])["stock"] == 12


def test_cu09_mismo_uuid_con_carrito_modificado_se_rechaza(caso_cu09):
    c = caso_cu09
    compra_id = str(uuid4())
    primera, _ = pedir_pago(c, compra_id=compra_id, cantidad=1)
    segunda, _ = pedir_pago(c, compra_id=compra_id, cantidad=2)
    assert primera.status_code == 201
    assert segunda.status_code == 409
    assert len(c.llamadas) == 1


def test_cu09_webhook_pagado_y_repetido_solo_descontara_una_vez(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    evento = evento_de(c, payload, checkout)
    assert evento.status_code == 200, evento.text
    estado = estado_db(c, payload["id"])
    assert estado["estado"] == "CONFIRMADA"
    assert estado["total"] == Decimal("80.10")
    assert estado["stock"] == 11
    assert estado["lineas"] == 1
    assert estado["movimientos"] == [("SALIDA", -1, 11)]
    repetido = evento_de(c, payload, checkout)
    assert repetido.status_code == 200
    assert estado_db(c, payload["id"]) == estado


def test_cu09_webhook_firma_incorrecta_no_confirma(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    r = c.client.post("/api/webhooks/stripe", content=b'{}',
                      headers={"stripe-signature": "firma-mala"})
    assert r.status_code == 400
    assert estado_db(c, payload["id"])["estado"] == "PAGO_PENDIENTE"
    assert estado_db(c, payload["id"])["stock"] == 12


@pytest.mark.parametrize("tipo,estado", [
    ("checkout.session.expired", "EXPIRADA"),
    ("checkout.session.async_payment_failed", "RECHAZADA"),
])
def test_cu09_expirado_o_fallido_no_crea_venta(caso_cu09, tipo, estado):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    evento = evento_de(c, payload, checkout, tipo=tipo, pagado=False)
    assert evento.status_code == 200
    datos = estado_db(c, payload["id"])
    assert datos["estado"] == estado
    assert datos["stock"] == 12 and not datos["movimientos"] and datos["total"] is None


def test_cu09_evento_completado_no_pagado_no_descontara(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    evento = evento_de(c, payload, checkout, pagado=False)
    assert evento.status_code == 200
    assert estado_db(c, payload["id"])["estado"] == "PAGO_PENDIENTE"
    assert estado_db(c, payload["id"])["stock"] == 12


def test_cu09_webhook_otra_sesion_se_rechaza(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    evento = evento_de(c, payload, checkout, session_id="cs_test_otra_sesion")
    assert evento.status_code == 503
    assert estado_db(c, payload["id"])["estado"] == "PAGO_PENDIENTE"
    assert estado_db(c, payload["id"])["stock"] == 12


@pytest.mark.parametrize("modificacion", ["monto", "moneda", "metadata"])
def test_cu09_pago_con_datos_diferentes_se_marca_incidencia(caso_cu09, modificacion):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    extra = {"monto": {"monto": 8009},
             "moneda": {"moneda": "usd"},
             "metadata": {"meta": {"compra_id": str(uuid4())}}}[modificacion]
    evento = evento_de(c, payload, checkout, **extra)
    assert evento.status_code == 200
    datos = estado_db(c, payload["id"])
    assert datos["estado"] == "INCIDENCIA"
    assert datos["stock"] == 12 and not datos["movimientos"] and datos["total"] is None


def test_cu09_si_se_agota_stock_antes_del_webhook_queda_incidencia(caso_cu09):
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    checkout = c.sesiones[next(iter(c.sesiones))].__dict__
    with c.sf() as db:
        stock = db.get(Existencia, (c.ids["empresa"], c.ids["sucursal"], c.ids["variante"]))
        stock.cantidad = 0
        db.commit()
    evento = evento_de(c, payload, checkout)
    assert evento.status_code == 200
    datos = estado_db(c, payload["id"])
    assert datos["estado"] == "INCIDENCIA"
    assert datos["stock"] == 0 and not datos["movimientos"] and datos["total"] is None


def test_cu09_sin_configuracion_rechaza_checkout(caso_cu09, monkeypatch):
    c = caso_cu09
    monkeypatch.setattr(cu09, "_configuration", lambda: None)
    capacidades = c.client.get(c.url + "/capacidades")
    assert capacidades.status_code == 200 and capacidades.json()["habilitado"] is False
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 503
    assert estado_db(c, payload["id"])["estado"] is None


def test_cu09_no_permita_checkout_anonimo(caso_cu09):
    c = caso_cu09
    c.client.app.dependency_overrides.pop(current_customer_session, None)
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 401
    assert estado_db(c, payload["id"])["estado"] is None


def test_cu09_conciliacion_pago_confirmado_sin_webhook(caso_cu09):
    """Reconciliar no crea un nuevo cobro ni descuenta dos veces."""
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    sesion = next(iter(c.sesiones.values()))
    sesion.mode = "payment"
    sesion.status = "complete"
    sesion.payment_status = "paid"
    sesion.client_reference_id = payload["id"]
    sesion.currency = "bob"
    sesion.amount_total = 8010
    sesion.metadata = {"compra_id": payload["id"]}
    sesion.payment_intent = "pi_test_solo_fixture"

    url = c.url + "/" + payload["id"]
    # El GET no debe producir movimientos aunque Stripe indique pagado.
    assert c.client.get(url + "/estado").json()["estado"] == "PAGO_PENDIENTE"
    assert c.client.post(url + "/reconciliar").json()["estado"] == "CONFIRMADA"
    assert estado_db(c, payload["id"])["stock"] == 11
    assert c.client.post(url + "/reconciliar").json()["estado"] == "CONFIRMADA"
    assert estado_db(c, payload["id"])["movimientos"] == [("SALIDA", -1, 11)]


def test_cu09_conciliacion_rechaza_pago_no_verificado(caso_cu09):
    """Nunca confirma un pago unpaid o con metadatos de otro pedido."""
    c = caso_cu09
    respuesta, payload = pedir_pago(c)
    assert respuesta.status_code == 201
    sesion = next(iter(c.sesiones.values()))
    sesion.mode = "payment"
    sesion.status = "complete"
    sesion.payment_status = "unpaid"
    sesion.client_reference_id = payload["id"]
    sesion.currency = "bob"
    sesion.amount_total = 8010
    sesion.metadata = {"compra_id": payload["id"]}
    url = c.url + "/" + payload["id"] + "/reconciliar"
    assert c.client.post(url).json()["estado"] == "PAGO_PENDIENTE"
    sesion.payment_status = "paid"
    sesion.metadata = {"compra_id": str(uuid4())}
    assert c.client.post(url).json()["estado"] == "PAGO_PENDIENTE"
    assert estado_db(c, payload["id"])["stock"] == 12
    assert estado_db(c, payload["id"])["movimientos"] == []
