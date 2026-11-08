"""CU19/CU20/CU23: catálogo cruzado, deseos privados y reportes acotados."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    CategoriaProducto, Cliente, Empresa, Existencia, Producto, Sucursal,
    VarianteProducto,
)
from app.security import hash_password
from app.operacion_sin_conexion.caja.online import CashSale

CUSTOMER_PASSWORD = "Clave de prueba lista deseos 2026"


@pytest.fixture
def first_group(client, administrator, session_factory, auth):
    with session_factory() as db:
        company = db.scalar(select(Empresa).where(Empresa.slug == "empresa-prueba"))
        other = Empresa(slug="empresa-externa", nombre="Empresa externa", activo=True)
        db.add(other)
        db.flush()
        branch = Sucursal(empresa_id=company.id, codigo="REPORTES", nombre="Sucursal reportes", activo=True)
        category = CategoriaProducto(empresa_id=company.id, nombre="Poleras",
                                     nombre_clave="poleras", activo=True)
        db.add_all([branch, category])
        db.flush()
        products = [
            Producto(empresa_id=company.id, categoria_id=category.id,
                     slug="recomendada-algodon", nombre="Polera algodón A",
                     material="algodón", temporada="verano",
                     precio=Decimal("100.00"), activo=True),
            Producto(empresa_id=company.id, categoria_id=category.id,
                     slug="similar-algodon", nombre="Polera algodón B",
                     material="algodón", temporada="verano",
                     precio=Decimal("105.00"), activo=True),
            Producto(empresa_id=company.id, categoria_id=category.id,
                     slug="prenda-no-publicada", nombre="Polera oculta",
                     precio=Decimal("80.00"), activo=False),
            Producto(empresa_id=other.id, slug="externa", nombre="Polera externa",
                     precio=Decimal("30.00"), activo=True),
        ]
        db.add_all(products)
        db.flush()
        variants = [VarianteProducto(empresa_id=p.empresa_id, producto_id=p.id,
                                     talla="M", color="Azul", activo=True) for p in products]
        db.add_all(variants)
        db.flush()
        db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id,
                         variante_id=variants[1].id, cantidad=5, cantidad_comprometida=2))
        customer = Cliente(empresa_id=company.id, nombre="Cliente deseos",
                           correo="deseos@vestinova.test",
                           password_hash=hash_password(CUSTOMER_PASSWORD), activo=True)
        db.add(customer)
        db.commit()
        keys = {"company": company.id, "branch": branch.id,
                "reference": products[0].slug, "similar": variants[1].id,
                "inactive": variants[2].id, "other_variant": variants[3].id}
    login = client.post("/api/tiendas/empresa-prueba/cuenta/login", json={
        "correo": "deseos@vestinova.test", "password": CUSTOMER_PASSWORD,
    })
    assert login.status_code == 200, login.text
    keys["customer_headers"] = {"Authorization": "Bearer " + login.json()["access_token"]}
    keys["admin_headers"] = {**auth, "X-Empresa-Id": str(keys["company"])}
    return keys


def test_cu19_sugiere_prendas_de_la_misma_empresa_sin_pretender_ia(client, first_group):
    s = first_group
    response = client.get("/api/catalogo/recomendaciones", params={
        "tienda": "empresa-prueba", "producto_slug": s["reference"],
        "talla": "M", "color": "Azul", "sucursal_id": s["branch"],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["criterio"] == "REGLAS_SIMILITUD_CATALOGO"
    assert [item["slug"] for item in body["items"]] == ["similar-algodon"]
    assert body["items"][0]["disponibilidad"] == "DISPONIBLE_REFERENCIAL"
    assert "Categoría similar" in body["items"][0]["motivos"]
    assert client.get("/api/catalogo/recomendaciones", params={
        "tienda": "empresa-prueba", "producto_slug": "externa",
    }).status_code == 404


def test_cu23_wishlist_es_privada_e_idempotente(client, first_group):
    s = first_group
    route = "/api/tiendas/empresa-prueba/cuenta/deseos"
    assert client.get(route).status_code == 401
    assert client.post(route, json={"variante_id": s["other_variant"]},
                       headers=s["customer_headers"]).status_code == 404
    assert client.post(route, json={"variante_id": s["inactive"]},
                       headers=s["customer_headers"]).status_code == 404
    first = client.post(route, json={"variante_id": s["similar"]},
                        headers=s["customer_headers"])
    assert first.status_code == 201, first.text
    again = client.post(route, json={"variante_id": s["similar"]},
                        headers=s["customer_headers"])
    assert again.status_code == 200 and not again.json()["agregado"]
    items = client.get(route, headers=s["customer_headers"])
    assert items.status_code == 200 and items.headers["cache-control"] == "no-store"
    assert items.json()["total"] == 1
    item = items.json()["items"][0]
    assert item["variante_id"] == s["similar"]
    assert item["precio_vigente"] == "105.00"
    assert item["publicada"] is True
    assert item["disponibilidad"] == "DISPONIBLE_REFERENCIAL"
    assert client.delete(route + "/" + str(s["similar"]),
                         headers=s["customer_headers"]).status_code == 204
    assert client.get(route, headers=s["customer_headers"]).json()["items"] == []


def test_cu20_informa_corte_actual_y_respeta_roles(client, first_group):
    s = first_group
    report = client.get("/api/admin/reportes-comerciales",
                        params={"tipo": "resumen", "sucursal_id": s["branch"]},
                        headers=s["admin_headers"])
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["totales"]["stock_fisico_actual"] == 5
    assert body["totales"]["stock_comprometido_actual"] == 2
    assert body["totales"]["stock_disponible_actual"] == 3
    assert body["totales"]["ventas_confirmadas"] == 0
    assert body["por_sucursal"][0]["sucursal"] == "Sucursal reportes"
    assert "pendientes" in body["nota"]
    assert client.get("/api/admin/reportes-comerciales", params={
        "desde": "2026-11-30", "hasta": "2026-11-01",
    }, headers=s["admin_headers"]).status_code == 422
    assert client.get("/api/admin/reportes-comerciales").status_code == 401
    assert client.get("/api/admin/reportes-comerciales",
                      headers=s["customer_headers"]).status_code in (401, 403)


def test_cu20_cuenta_solo_ventas_centrales_confirmadas(
    client, first_group, session_factory, administrator,
):
    data = first_group
    with session_factory() as db:
        db.add(CashSale(
            id=str(uuid4()), empresa_id=data["company"],
            sucursal_id=data["branch"], usuario_id=administrator.id,
            cliente_id=None, huella="a" * 64, lineas=[],
            total=Decimal("80.00"), efectivo=Decimal("100.00"),
            cambio=Decimal("20.00"), codigo="VN-DEMO-CU20-" + uuid4().hex[:10],
            origen="EN_LINEA", creada_local_en=None,
            entrega_local=False, confirmada_en=datetime.now(timezone.utc),
        ))
        db.commit()
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get("/api/admin/reportes-comerciales", params={
        "tipo": "ventas", "sucursal_id": data["branch"],
        "desde": today, "hasta": today,
    }, headers=data["admin_headers"])
    assert response.status_code == 200, response.text
    values = response.json()["totales"]
    assert values["ventas_confirmadas"] == 1
    assert values["ventas_efectivo"] == 1
    assert values["ventas_digitales"] == 0
    assert values["ingresos_confirmados"] == "80.00"


def test_cu19_visitas_solo_con_consentimiento_y_borrado(client, first_group, session_factory):
    s = first_group
    base = "/api/tiendas/empresa-prueba/cuenta/recomendaciones"
    headers = s["customer_headers"]
    initial = client.get(base + "/preferencias", headers=headers)
    assert initial.status_code == 200 and initial.json()["habilitado"] is False
    assert client.post(base + "/visitas", json={"producto_slug": s["reference"]},
                       headers=headers).status_code == 403
    enabled = client.put(base + "/preferencias", json={"habilitado": True},
                         headers=headers)
    assert enabled.status_code == 200 and enabled.json()["habilitado"] is True
    for _ in range(4):
        result = client.post(base + "/visitas",
                             json={"producto_slug": s["reference"]},
                             headers=headers)
        assert result.status_code == 202, result.text
    recommended = client.get(base + "/sugerencias", headers=headers)
    assert recommended.status_code == 200, recommended.text
    data = recommended.json()
    assert data["criterio"] == "REGLAS_HISTORIAL_CONSENTIDO"
    assert data["items"][0]["slug"] == "similar-algodon"
    assert all(item["slug"] != s["reference"] for item in data["items"])
    assert "categorías que has consultado" in " ".join(data["items"][0]["motivos"])

    # Una cuenta no puede utilizar su token en otra tienda.
    assert client.get("/api/tiendas/empresa-externa/cuenta/recomendaciones/sugerencias",
                      headers=headers).status_code in (401, 404)
    disabled = client.put(base + "/preferencias", json={"habilitado": False},
                          headers=headers)
    assert disabled.status_code == 200 and disabled.json()["historial_borrado"]
    assert client.get(base + "/sugerencias", headers=headers).status_code == 403
    from app.catalogo_publico.historial_recomendaciones import VistaCU19
    with session_factory() as db:
        assert not db.query(VistaCU19).filter_by(
            empresa_id=s["company"]).count()


def test_cu20_detalle_color_y_talla_en_comprobante(client, first_group, session_factory, administrator):
    s = first_group
    from app.operacion_sin_conexion.caja.online import CashSale
    with session_factory() as db:
        db.add(CashSale(
            id=str(uuid4()), empresa_id=s["company"], sucursal_id=s["branch"],
            usuario_id=administrator.id, cliente_id=None,
            huella="f" * 64,
            lineas=[{"variante_id": s["similar"], "producto_id": 1,
                     "nombre": "Polera algodón B", "cantidad": 2,
                     "precio_unitario": "105.00", "subtotal": "210.00"}],
            total=Decimal("210.00"), efectivo=Decimal("210.00"),
            cambio=Decimal("0.00"), codigo="VN-DEMO-CU20-TEST-"+str(uuid4())[:7],
            origen="EN_LINEA", creada_local_en=None,
            entrega_local=False, confirmada_en=datetime.now(timezone.utc),
        ))
        db.commit()
    today = datetime.now(timezone.utc).date().isoformat()
    result = client.get("/api/admin/reportes-comerciales", params={
        "tipo": "ventas", "desde": today, "hasta": today,
        "sucursal_id": s["branch"],
    }, headers=s["admin_headers"])
    assert result.status_code == 200, result.text
    details = result.json()["ventas_por_prenda"]
    assert len(details) == 1
    assert details[0]["color"] == "Azul"
    assert details[0]["categoria"] == "Poleras"
    assert details[0]["talla"] == "M"
    assert details[0]["unidades"] == 2
    assert details[0]["importe"] == "210.00"
    assert details[0]["es_demo"] is True
    assert result.json()["totales"]["ventas_demo"] == 1
