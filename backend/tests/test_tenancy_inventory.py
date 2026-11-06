"""Seguridad, trazabilidad y descarga; datos propios aislados de la base operativa."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AccesoSucursal, Administrador, Empresa, Existencia, MembresiaEmpresa,
    MovimientoInventario, Producto, Sucursal, VarianteProducto,
)
from tests.conftest import TEST_PASSWORD, activate_test_subscription


def login(client, account):
    result = client.post("/api/auth/login", json={"correo": account.correo, "password": TEST_PASSWORD})
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


@pytest.fixture
def scope(client, administrator, auth, session_factory):
    with session_factory() as db:
        a = db.scalar(select(Empresa).join(MembresiaEmpresa).where(MembresiaEmpresa.administrador_id == administrator.id))
        b = Empresa(slug="empresa-b", nombre="Empresa B", activo=True)
        db.add(b)
        owner_b = Administrador(nombre="Administrador B", correo="b@vestinova.test", password_hash=administrator.password_hash, activo=True)
        operator = Administrador(nombre="Operador A", correo="operador@vestinova.test", password_hash=administrator.password_hash, activo=True)
        platform = Administrador(nombre="Solo plataforma", correo="plataforma@vestinova.test", password_hash=administrator.password_hash, activo=True, es_superadministrador=True)
        db.add_all([owner_b, operator, platform])
        db.flush()
        activate_test_subscription(db, b.id)
        db.add_all([
            MembresiaEmpresa(administrador_id=owner_b.id, empresa_id=b.id, rol="ADMINISTRADOR", activo=True),
            MembresiaEmpresa(administrador_id=operator.id, empresa_id=a.id, rol="OPERADOR", activo=True),
        ])
        a1 = Sucursal(empresa_id=a.id, codigo="A1", nombre="Sucursal A1", activo=True)
        a2 = Sucursal(empresa_id=a.id, codigo="A2", nombre="Sucursal A2", activo=True)
        b1 = Sucursal(empresa_id=b.id, codigo="B1", nombre="Sucursal B1", activo=True)
        db.add_all([a1, a2, b1])
        db.flush()
        db.add(AccesoSucursal(administrador_id=operator.id, empresa_id=a.id, sucursal_id=a1.id))
        db.commit()
    return SimpleNamespace(a=a, b=b, a1=a1, a2=a2, b1=b1, owner_a=administrator,
                           owner_b=owner_b, operator=operator, platform=platform,
                           ah=auth, bh=login(client, owner_b), oh=login(client, operator),
                           ph=login(client, platform))


def product(client, headers, name="Camisa propia", **extra):
    response = client.post("/api/admin/productos", headers=headers,
                           json={"nombre": name, "precio": "150.90", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def variant(client, headers, product_id, **extra):
    response = client.post(f"/api/admin/productos/{product_id}/variantes", headers=headers,
                           json={"talla": " m ", "color": " verde ", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def movement(branch, variant_id, quantity=7, kind="ENTRADA", **extra):
    return {"id": str(uuid4()), "sucursal_id": branch.id, "variante_id": variant_id,
            "tipo": kind, "cantidad": quantity, "motivo": "Conteo inicial documentado", **extra}


def post_movement(client, headers, payload, expected=201):
    response = client.post("/api/admin/inventario/movimientos", headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_company_products_are_scoped_and_foreign_resources_are_not_editable(client, scope):
    a = product(client, scope.ah, "Camisa empresa A")
    b = product(client, scope.bh, "Camisa empresa B")
    assert client.get("/api/admin/productos", headers=scope.ah).json()["items"] == [a]
    assert client.get("/api/admin/productos", headers=scope.bh).json()["items"] == [b]
    assert client.get(f"/api/admin/productos/{b['id']}", headers=scope.ah).status_code == 404
    assert client.patch(f"/api/admin/productos/{b['id']}", headers=scope.ah,
                        json={"precio": "1.00"}).status_code == 404
    assert client.post("/api/admin/productos", headers=scope.ah,
                       json={"nombre": "Inyección empresa", "precio": "12.00", "empresa_id": scope.b.id}).status_code == 422
    assert client.get(f"/api/admin/productos/{b['id']}", headers=scope.bh).json() == b


def test_public_catalog_shape_and_slug_contract_remain_compatible(client, scope):
    a = product(client, scope.ah, "Visible A")
    b = product(client, scope.bh, "Visible B")
    product(client, scope.bh, "Privado B", activo=False)
    page = client.get("/api/catalogo/productos?limit=1&offset=1").json()
    assert page == {"items": [a], "total": 2, "limit": 1, "offset": 1}
    assert set(a) == {"id", "slug", "nombre", "categoria_id", "categoria_nombre", "descripcion",
                      "material", "medidas", "temporada", "precio", "precio_promocional", "promocion_nombre", "moneda", "imagen_url",
                      "activo", "creado_en", "actualizado_en"}
    assert a["precio"] == "150.90" and a["moneda"] == "BOB"
    assert client.get(f"/api/catalogo/productos/{b['slug']}").json() == b


def test_company_membership_is_checked_from_database_on_every_request(client, scope, session_factory):
    assert [x["id"] for x in client.get("/api/empresas", headers=scope.ah).json()] == [scope.a.id]
    assert client.get("/api/admin/productos", headers={**scope.ah, "X-Empresa-Id": str(scope.b.id)}).status_code == 403
    with session_factory() as db:
        db.get(MembresiaEmpresa, (scope.owner_a.id, scope.a.id)).activo = False
        db.commit()
    assert client.get("/api/admin/productos", headers=scope.ah).status_code == 403
    assert client.get("/api/auth/me", headers=scope.ah).status_code == 200


def test_multiple_memberships_require_explicit_selection_and_superadmin_has_no_data_bypass(client, scope, session_factory):
    with session_factory() as db:
        db.add(MembresiaEmpresa(administrador_id=scope.owner_a.id, empresa_id=scope.b.id, rol="OPERADOR", activo=True))
        db.commit()
    assert client.get("/api/admin/productos", headers=scope.ah).status_code == 409
    assert client.get("/api/admin/productos", headers={**scope.ah, "X-Empresa-Id": str(scope.a.id)}).status_code == 200
    assert client.get("/api/admin/productos", headers=scope.ph).status_code == 403
    assert client.get("/api/empresas", headers=scope.ph).json() == []


def test_platform_company_creation_assigns_only_explicit_owner(client, scope):
    body = {"slug": "empresa-nueva", "nombre": "Empresa Nueva", "administrador_id": scope.owner_b.id}
    assert client.post("/api/plataforma/empresas", headers=scope.ah, json=body).status_code == 403
    response = client.post("/api/plataforma/empresas", headers=scope.ph, json=body)
    assert response.status_code == 201, response.text
    company_id = response.json()["id"]
    assert client.get("/api/admin/productos", headers={**scope.bh, "X-Empresa-Id": str(company_id)}).status_code == 200
    assert client.get("/api/admin/productos", headers={**scope.ph, "X-Empresa-Id": str(company_id)}).status_code == 403


def test_branch_read_restrictions_and_operator_cannot_administer(client, scope):
    assert {s["id"] for s in client.get("/api/admin/sucursales", headers=scope.ah).json()} == {scope.a1.id, scope.a2.id}
    assert [s["id"] for s in client.get("/api/admin/sucursales", headers=scope.oh).json()] == [scope.a1.id]
    assert client.post("/api/admin/sucursales", headers=scope.oh,
                       json={"codigo": "NUEVA", "nombre": "Sucursal nueva"}).status_code == 403
    assert client.post("/api/admin/productos", headers=scope.oh,
                       json={"nombre": "No autorizado", "precio": "15.00"}).status_code == 403
    assert client.patch(f"/api/admin/sucursales/{scope.b1.id}", headers=scope.ah,
                        json={"nombre": "Sucursal ajena"}).status_code == 404
    for branch in [scope.a2, scope.b1]:
        assert client.get(f"/api/admin/inventario/existencias?sucursal_id={branch.id}", headers=scope.oh).status_code == 404


def test_last_company_administrator_cannot_be_removed(client, scope):
    response = client.post("/api/admin/pertenencias", headers=scope.ah, json={
        "administrador_id": scope.owner_a.id, "rol": "OPERADOR", "activo": True,
        "sucursal_ids": [scope.a1.id],
    })
    assert response.status_code == 409
    assert client.get("/api/admin/empresa", headers=scope.ah).status_code == 200


def test_branch_grants_replace_atomically_and_revoke_live_download_access(client, scope):
    forbidden = {"administrador_id": scope.operator.id, "rol": "OPERADOR", "activo": True, "sucursal_ids": [scope.b1.id]}
    assert client.post("/api/admin/pertenencias", headers=scope.ah, json=forbidden).status_code == 404
    assert [s["id"] for s in client.get("/api/admin/sucursales", headers=scope.oh).json()] == [scope.a1.id]
    updated = {**forbidden, "sucursal_ids": [scope.a2.id]}
    assert client.post("/api/admin/pertenencias", headers=scope.oh, json=updated).status_code == 403
    changed = client.post("/api/admin/pertenencias", headers=scope.ah, json=updated)
    assert changed.status_code in {200, 201}, changed.text
    assert client.get(f"/api/movil/descarga?sucursal_ids={scope.a1.id}", headers=scope.oh).status_code == 404
    assert client.get(f"/api/movil/descarga?sucursal_ids={scope.a2.id}", headers=scope.oh).status_code == 200


def test_inactive_company_or_branch_cannot_be_used_for_operations(client, scope, session_factory):
    with session_factory() as db:
        db.get(Sucursal, scope.a1.id).activo = False
        db.commit()
    assert client.get("/api/movil/descarga", headers=scope.oh).status_code == 403
    assert client.get(f"/api/movil/descarga?sucursal_ids={scope.a1.id}", headers=scope.ah).status_code == 404
    with session_factory() as db:
        db.get(Empresa, scope.a.id).activo = False
        db.commit()
    assert client.get("/api/admin/productos", headers=scope.ah).status_code == 403


def test_variants_are_normalized_unique_and_scoped(client, scope):
    a = product(client, scope.ah)
    b = product(client, scope.bh, "Camisa B")
    av = variant(client, scope.ah, a["id"])
    bv = variant(client, scope.bh, b["id"])
    assert av["talla"] == "M" and av["color"] == "VERDE"
    duplicate = client.post(f"/api/admin/productos/{a['id']}/variantes", headers=scope.ah,
                            json={"talla": "M", "color": "VERDE"})
    assert duplicate.status_code == 409
    assert client.get(f"/api/admin/productos/{b['id']}/variantes", headers=scope.ah).status_code == 404
    assert client.post(f"/api/admin/productos/{b['id']}/variantes", headers=scope.ah,
                       json={"talla": "L", "color": "AZUL"}).status_code == 404
    assert client.patch(f"/api/admin/variantes/{bv['id']}", headers=scope.ah, json={"activo": False}).status_code == 404
    assert client.patch(f"/api/admin/variantes/{av['id']}", headers=scope.oh, json={"activo": False}).status_code == 403
    assert client.patch(f"/api/admin/variantes/{av['id']}", headers=scope.ah, json={"activo": False}).status_code == 200


def test_movements_persist_balances_and_auditable_signed_history(client, scope, session_factory):
    p = product(client, scope.ah)
    v = variant(client, scope.ah, p["id"])
    entry = post_movement(client, scope.ah, movement(scope.a1, v["id"], 10))
    exit_ = post_movement(client, scope.ah, movement(scope.a1, v["id"], 4, "SALIDA", motivo="Ajuste por conteo físico"))
    assert entry["delta"] == 10 and entry["saldo_resultante"] == 10
    assert exit_["delta"] == -4 and exit_["saldo_resultante"] == 6
    assert entry["usuario_id"] == scope.owner_a.id
    page = client.get(f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}", headers=scope.ah).json()
    assert page["total"] == 1 and page["items"][0]["cantidad"] == 6
    history = client.get(f"/api/admin/inventario/movimientos?sucursal_id={scope.a1.id}&variante_id={v['id']}&limit=1", headers=scope.ah).json()
    assert history["total"] == 2 and len(history["items"]) == 1
    with session_factory() as db:
        balance = db.get(Existencia, (scope.a.id, scope.a1.id, v["id"]))
        total = db.scalar(select(func.sum(MovimientoInventario.delta)).where(MovimientoInventario.variante_id == v["id"]))
        assert balance.cantidad == total == 6


def test_inventory_replay_is_idempotent_and_negative_adjustment_rolls_back(client, scope, session_factory):
    p = product(client, scope.ah)
    v = variant(client, scope.ah, p["id"])
    payload = movement(scope.a1, v["id"], 5)
    first = post_movement(client, scope.ah, payload)
    assert post_movement(client, scope.ah, payload, 200) == first
    assert client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                       json={**payload, "cantidad": 6}).status_code == 409
    assert client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                       json=movement(scope.a1, v["id"], 6, "SALIDA")).status_code == 409
    with session_factory() as db:
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad == 5
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 1


def test_inventory_does_not_accept_foreign_branch_variant_or_spoofed_responsible(client, scope):
    a = product(client, scope.ah)
    b = product(client, scope.bh, "Camisa ajena")
    av = variant(client, scope.ah, a["id"])
    bv = variant(client, scope.bh, b["id"])
    assert client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                       json=movement(scope.b1, av["id"])).status_code == 404
    assert client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                       json=movement(scope.a1, bv["id"])).status_code == 404
    assert client.post("/api/admin/inventario/movimientos", headers=scope.oh,
                       json=movement(scope.a1, av["id"])).status_code == 403
    assert client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                       json=movement(scope.a1, av["id"], usuario_id=scope.owner_b.id)).status_code == 422
    assert client.get(f"/api/admin/inventario/movimientos?sucursal_id={scope.b1.id}", headers=scope.ah).status_code == 404


@pytest.mark.parametrize("change", [{"cantidad": 0}, {"cantidad": -1}, {"cantidad": 1.5}, {"cantidad": 1000000001}, {"cantidad": True}, {"sucursal_id": True}, {"variante_id": True}, {"tipo": "VENTA"}, {"motivo": " "}, {"id": "no-es-un-uuid"}])
def test_invalid_movement_is_not_recorded(client, scope, session_factory, change):
    p = product(client, scope.ah)
    v = variant(client, scope.ah, p["id"])
    response = client.post("/api/admin/inventario/movimientos", headers=scope.ah,
                           json=movement(scope.a1, v["id"], **change))
    assert response.status_code == 422
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 0
        assert db.scalar(select(func.count()).select_from(Existencia)) == 0


def test_download_is_authorized_bounded_and_preserves_prices_without_fabricating_stock(client, scope):
    p = product(client, scope.ah)
    v = variant(client, scope.ah, p["id"])
    hidden_variant = variant(client, scope.ah, p["id"], talla="L", activo=False)
    product(client, scope.ah, "Producto no publicado", activo=False)
    b = product(client, scope.bh, "Producto empresa B")
    variant(client, scope.bh, b["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 8))
    response = client.get("/api/movil/descarga?limit=1&offset=0", headers=scope.oh)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["version_contrato"] == "1.0"
    assert data["empresa"]["id"] == scope.a.id and data["moneda"] == "BOB"
    assert data["total"] == 1 and data["limit"] == 1 and data["offset"] == 0
    assert data["generado_en"]
    assert [s["id"] for s in data["sucursales"]] == [scope.a1.id]
    downloaded = data["productos"][0]
    assert downloaded["id"] == p["id"] and downloaded["precio"] == "150.90"
    assert downloaded["moneda"] == "BOB"
    assert [item["id"] for item in downloaded["variantes"]] == [v["id"]]
    known = downloaded["variantes"][0]["existencias"][0]
    assert known["sucursal_id"] == scope.a1.id and known["cantidad"] == 8
    assert known["registrada"] is True and known["actualizado_en"]
    data_admin = client.get(f"/api/movil/descarga?sucursal_ids={scope.a2.id}", headers=scope.ah).json()
    empty = data_admin["productos"][0]["variantes"][0]["existencias"][0]
    assert empty == {"sucursal_id": scope.a2.id, "cantidad": 0, "registrada": False, "actualizado_en": None}
    assert str(hidden_variant["id"]) not in [str(x["id"]) for x in downloaded["variantes"]]
    assert "password_hash" not in response.text and "correo" not in response.text


def test_download_rejects_foreign_selection_in_full_and_has_explicit_pagination(client, scope):
    a = product(client, scope.ah, "Producto A uno")
    product(client, scope.ah, "Producto A dos")
    b = product(client, scope.bh, "Producto B")
    for query in [f"sucursal_ids={scope.b1.id}", f"sucursal_ids={scope.a1.id}&sucursal_ids={scope.b1.id}",
                  f"producto_ids={b['id']}", f"producto_ids={a['id']}&producto_ids={b['id']}"]:
        assert client.get(f"/api/movil/descarga?{query}", headers=scope.ah).status_code == 404
    page = client.get("/api/movil/descarga?limit=1&offset=1", headers=scope.ah).json()
    assert page["total"] == 2 and len(page["productos"]) == 1
    selected = client.get(f"/api/movil/descarga?producto_ids={a['id']}", headers=scope.ah).json()
    assert selected["total"] == 1 and [p["id"] for p in selected["productos"]] == [a["id"]]
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert client.get(f"/api/movil/descarga?{query}", headers=scope.ah).status_code == 422


def test_database_foreign_keys_prevent_cross_company_variant_stock_and_grants(client, scope, session_factory):
    a = product(client, scope.ah)
    b = product(client, scope.bh, "Producto B")
    av = variant(client, scope.ah, a["id"])
    bv = variant(client, scope.bh, b["id"])
    records = [
        VarianteProducto(empresa_id=scope.a.id, producto_id=b["id"], talla="S", color="AZUL", activo=True),
        Existencia(empresa_id=scope.a.id, sucursal_id=scope.b1.id, variante_id=bv["id"], cantidad=0),
        AccesoSucursal(administrador_id=scope.operator.id, empresa_id=scope.a.id, sucursal_id=scope.b1.id),
        MovimientoInventario(id=str(uuid4()), empresa_id=scope.a.id, sucursal_id=scope.a1.id,
                             variante_id=av["id"], usuario_id=scope.owner_b.id, tipo="ENTRADA",
                             delta=2, saldo_resultante=2, motivo="Usuario de empresa ajena"),
    ]
    for record in records:
        with session_factory() as db:
            db.add(record)
            with pytest.raises(IntegrityError):
                db.flush()
            db.rollback()


@pytest.mark.parametrize("method,path", [
    ("get", "/api/empresas"), ("get", "/api/admin/empresa"), ("get", "/api/admin/sucursales"),
    ("get", "/api/admin/pertenencias"), ("get", "/api/admin/productos/1/variantes"),
    ("get", "/api/admin/inventario/existencias?sucursal_id=1"),
    ("get", "/api/admin/inventario/movimientos?sucursal_id=1"), ("get", "/api/movil/descarga"),
    ("post", "/api/admin/inventario/movimientos"), ("post", "/api/plataforma/empresas"),
])
def test_new_private_endpoints_reject_missing_session(client, method, path):
    response = getattr(client, method)(path, json={}) if method == "post" else client.get(path)
    assert response.status_code == 401


def test_inventory_filters_scope_product_category_variant_and_name(client, scope):
    def category(headers, name):
        response = client.post("/api/admin/categorias", headers=headers,
                               json={"nombre": name, "descripcion": "Filtro para inventario"})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    shirts = category(scope.ah, "Camisas")
    dresses = category(scope.ah, "Vestidos")
    foreign_category = category(scope.bh, "Exclusivo empresa B")
    shirt_blue = product(client, scope.ah, "Camisa Azul", categoria_id=shirts)
    shirt_green = product(client, scope.ah, "Camisa Verde", categoria_id=shirts)
    dress = product(client, scope.ah, "Vestido Rojo", categoria_id=dresses)
    foreign = product(client, scope.bh, "Camisa Ajena", categoria_id=foreign_category)

    blue = variant(client, scope.ah, shirt_blue["id"], talla="S", color="AZUL")
    green = variant(client, scope.ah, shirt_green["id"], talla="L", color="VERDE")
    red = variant(client, scope.ah, dress["id"], talla="M", color="ROJO")
    foreign_variant = variant(client, scope.bh, foreign["id"], talla="XL", color="NEGRO")
    for item in (blue, green, red):
        post_movement(client, scope.ah, movement(scope.a1, item["id"], 5))
    post_movement(client, scope.bh, movement(scope.b1, foreign_variant["id"], 7))
    post_movement(client, scope.ah, movement(scope.a2, blue["id"], 2))

    endpoint = f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}"

    def result(extra=""):
        response = client.get(endpoint + extra, headers=scope.ah)
        assert response.status_code == 200, response.text
        return response.json()

    complete = result()
    assert complete["total"] == 3
    assert [row["variante_id"] for row in complete["items"]] == [blue["id"], green["id"], red["id"]]
    assert complete["items"][0]["producto_nombre"] == "Camisa Azul"
    assert complete["items"][0]["producto_id"] == shirt_blue["id"]
    assert complete["items"][0]["categoria_id"] == shirts
    assert complete["items"][0]["talla"] == "S"
    assert complete["items"][0]["color"] == "AZUL"

    assert result(f"&categoria_id={shirts}")["total"] == 2
    assert [row["variante_id"] for row in result(f"&producto_id={shirt_blue['id']}")["items"]] == [blue["id"]]
    assert [row["variante_id"] for row in result(f"&variante_id={red['id']}")["items"]] == [red["id"]]
    assert result("&q=CAMISA")["total"] == 2
    assert result("&q=azul")["total"] == 1
    assert result(f"&categoria_id={dresses}&q=camisa")["total"] == 0
    assert client.get(endpoint + f"&categoria_id={foreign_category}", headers=scope.ah).status_code == 404
    assert client.get(endpoint + f"&producto_id={foreign['id']}", headers=scope.ah).status_code == 404
    assert client.get(endpoint + f"&variante_id={foreign_variant['id']}", headers=scope.ah).status_code == 404
    assert result(f"&categoria_id={shirts}&limit=1&offset=1")["total"] == 2
    assert len(result(f"&categoria_id={shirts}&limit=1&offset=1")["items"]) == 1
    assert client.get(
        f"/api/admin/inventario/existencias?sucursal_id={scope.a2.id}&q=camisa",
        headers=scope.oh,
    ).status_code == 404


@pytest.mark.parametrize("query", [
    "producto_id=0", "producto_id=-1", "categoria_id=0", "categoria_id=-1",
    "variante_id=0", "variante_id=-1", "variante_id=texto", "q=" + "a" * 121,
])
def test_inventory_filters_reject_invalid_parameters(client, scope, query):
    response = client.get(
        f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}&{query}",
        headers=scope.ah,
    )
    assert response.status_code == 422, response.text


def adjustment(branch, variant_id, quantity, kind="DISMINUCION", **extra):
    return {
        "id": str(uuid4()), "sucursal_id": branch.id,
        "variante_id": variant_id, "tipo": kind,
        "cantidad": quantity, "motivo": "Recuento físico documentado", **extra,
    }


def test_cu07_stock_physical_reserved_available_and_adjustment_is_atomic(client, scope, session_factory):
    item = product(client, scope.ah, "Stock comprometido")
    v = variant(client, scope.ah, item["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 10))
    with session_factory() as db:
        balance = db.get(Existencia, (scope.a.id, scope.a1.id, v["id"]))
        balance.cantidad_comprometida = 6
        db.commit()

    url = f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}"
    before = client.get(url, headers=scope.ah).json()["items"][0]
    assert (before["cantidad"], before["cantidad_comprometida"], before["cantidad_disponible"]) == (10, 6, 4)

    invalid = adjustment(scope.a1, v["id"], 5)
    rejected = client.post("/api/admin/inventario/ajustes", json=invalid, headers=scope.ah)
    assert rejected.status_code == 409
    assert "comprometidas" in rejected.json()["detail"]

    valid = adjustment(scope.a1, v["id"], 4)
    result = client.post("/api/admin/inventario/ajustes", json=valid, headers=scope.ah)
    assert result.status_code == 201, result.text
    assert result.json()["clase"] == "AJUSTE"
    assert result.json()["tipo"] == "SALIDA"
    assert result.json()["delta"] == -4
    assert result.json()["saldo_resultante"] == 6

    after = client.get(url, headers=scope.ah).json()["items"][0]
    assert (after["cantidad"], after["cantidad_comprometida"], after["cantidad_disponible"]) == (6, 6, 0)
    with session_factory() as db:
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad_comprometida == 6
        assert db.scalar(
            select(func.count()).select_from(MovimientoInventario)
            .where(MovimientoInventario.clase == "AJUSTE")
        ) == 1


def test_cu07_adjustment_replay_changes_and_read_only_kardex(client, scope, session_factory):
    item = product(client, scope.ah, "Ajustes trazables")
    v = variant(client, scope.ah, item["id"])
    payload = adjustment(scope.a1, v["id"], 8, "INCREMENTO")
    first = client.post("/api/admin/inventario/ajustes", json=payload, headers=scope.ah)
    assert first.status_code == 201, first.text
    repeated = client.post("/api/admin/inventario/ajustes", json=payload, headers=scope.ah)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    changed = client.post("/api/admin/inventario/ajustes", json={**payload, "cantidad": 9}, headers=scope.ah)
    assert changed.status_code == 409
    cross_endpoint = client.post("/api/admin/inventario/movimientos", headers=scope.ah, json={
        **payload, "tipo": "ENTRADA",
    })
    assert cross_endpoint.status_code == 409
    history = f"/api/admin/inventario/movimientos?sucursal_id={scope.a1.id}&variante_id={v['id']}"
    for _ in range(2):
        page = client.get(history, headers=scope.ah)
        assert page.status_code == 200
        assert page.json()["total"] == 1
        assert page.json()["items"][0]["usuario_id"] == scope.owner_a.id
        assert page.json()["items"][0]["clase"] == "AJUSTE"
    with session_factory() as db:
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad == 8


@pytest.mark.parametrize("change", [
    {"cantidad": 0}, {"cantidad": -1}, {"cantidad": 1.5},
    {"cantidad": True}, {"motivo": " "}, {"tipo": "SALIDA"},
    {"id": "identificador-invalido"}, {"variante_id": -1},
])
def test_cu07_adjustment_invalid_inputs_have_no_effect(client, scope, session_factory, change):
    item = product(client, scope.ah, "Variante valida")
    v = variant(client, scope.ah, item["id"])
    result = client.post(
        "/api/admin/inventario/ajustes", headers=scope.ah,
        json=adjustment(scope.a1, v["id"], 3, **change),
    )
    assert result.status_code == 422, result.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 0
        assert db.scalar(select(func.count()).select_from(Existencia)) == 0


def test_cu07_readonly_operator_cannot_adjust_but_encargado_can(client, scope, session_factory):
    item = product(client, scope.ah, "Prenda de encargado")
    v = variant(client, scope.ah, item["id"])
    data = adjustment(scope.a1, v["id"], 2, "INCREMENTO")
    denied = client.post("/api/admin/inventario/ajustes", headers=scope.oh, json=data)
    assert denied.status_code == 403
    assert client.get(
        f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}",
        headers=scope.oh,
    ).status_code == 200
    with session_factory() as db:
        member = db.get(MembresiaEmpresa, (scope.operator.id, scope.a.id))
        member.rol = "ENCARGADO_SUCURSAL"
        member.rol_empresa_id = None
        db.commit()
    allowed = client.post("/api/admin/inventario/ajustes", headers=scope.oh, json=data)
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["usuario_id"] == scope.operator.id
    outside = client.post(
        "/api/admin/inventario/ajustes", headers=scope.oh,
        json=adjustment(scope.a2, v["id"], 1, "INCREMENTO"),
    )
    assert outside.status_code == 404
    assert client.post(
        "/api/admin/inventario/ajustes", headers=scope.ah,
        json=adjustment(scope.b1, v["id"], 1, "INCREMENTO"),
    ).status_code == 404
    foreign = product(client, scope.bh, "Producto de otra empresa")
    foreign_v = variant(client, scope.bh, foreign["id"])
    assert client.post(
        "/api/admin/inventario/ajustes", headers=scope.oh,
        json=adjustment(scope.a1, foreign_v["id"], 1, "INCREMENTO"),
    ).status_code == 404


def test_cu07_adjustments_revalidate_after_intervening_stock_change(client, scope, session_factory):
    item = product(client, scope.ah, "Actualizacion entre consultas")
    v = variant(client, scope.ah, item["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 5))
    previous = client.get(
        f"/api/admin/inventario/existencias?sucursal_id={scope.a1.id}",
        headers=scope.ah,
    )
    assert previous.status_code == 200 and previous.json()["items"][0]["cantidad"] == 5
    spent = adjustment(scope.a1, v["id"], 4, "DISMINUCION")
    assert client.post("/api/admin/inventario/ajustes", headers=scope.ah, json=spent).status_code == 201
    stale = adjustment(scope.a1, v["id"], 3, "DISMINUCION")
    assert client.post("/api/admin/inventario/ajustes", headers=scope.ah, json=stale).status_code == 409
    with session_factory() as db:
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad == 1


def test_cu07_generic_stock_exit_also_respects_existing_commitments(client, scope, session_factory):
    item = product(client, scope.ah, "Stock protegido")
    v = variant(client, scope.ah, item["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 6))
    with session_factory() as db:
        row = db.get(Existencia, (scope.a.id, scope.a1.id, v["id"]))
        row.cantidad_comprometida = 5
        db.commit()
    assert client.post(
        "/api/admin/inventario/movimientos", headers=scope.ah,
        json=movement(scope.a1, v["id"], 2, "SALIDA"),
    ).status_code == 409
    with session_factory() as db:
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad == 6


def test_cu07_reentry_rejects_invalid_or_unknown_origin_without_stock(client, scope, session_factory):
    item = product(client, scope.ah, "Devolucion")
    v = variant(client, scope.ah, item["id"])
    payload = {
        "id": str(uuid4()), "solicitud_id": str(uuid4()),
        "sucursal_id": scope.a1.id, "variante_id": v["id"], "cantidad": 2,
        "motivo": "Reingreso apto para venta", "apta_para_venta": True,
    }
    assert client.post(
        "/api/admin/inventario/reingresos", headers=scope.ah,
        json=payload,
    ).status_code == 404
    assert client.post(
        "/api/admin/inventario/reingresos", headers=scope.ah,
        json={**payload, "apta_para_venta": False},
    ).status_code == 422
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 0


def test_cu07_reentry_is_linked_to_completed_postventa_exactly_once(client, scope, session_factory):
    from decimal import Decimal
    from app.models import Cliente, utc_now
    from app.compras_reservas.compras.domain import identifier_token
    from app.compras_reservas.compras.persistence import PurchaseRecord
    from app.compras_reservas.postventa.persistence import SolicitudPostventa, LineaSolicitudPostventa

    item = product(client, scope.ah, "Prenda devuelta")
    v = variant(client, scope.ah, item["id"])
    purchase_id = str(uuid4())
    request_id = str(uuid4())
    with session_factory() as db:
        customer = Cliente(
            empresa_id=scope.a.id, nombre="Cliente CU07",
            correo="devolucion.cu07@vestinova.test",
            password_hash=scope.owner_a.password_hash, activo=True,
        )
        db.add(customer)
        db.flush()
        company_key = identifier_token(scope.a.id)
        db.add(PurchaseRecord(
            id=purchase_id, empresa_clave=company_key,
            cliente_clave=identifier_token(customer.id),
            sucursal_clave=identifier_token(scope.a1.id),
            contexto={
                "actor_id": customer.id, "empresa_id": scope.a.id,
                "cliente_id": customer.id, "sucursal_id": scope.a1.id,
            },
            huella="a" * 64, creado_en=utc_now(),
            total=Decimal("300.00"), moneda="BOB",
        ))
        db.flush()
        request = SolicitudPostventa(
            id=request_id, empresa_id=scope.a.id, empresa_clave=company_key,
            cliente_id=customer.id, compra_id=purchase_id,
            sucursal_id=scope.a1.id, tipo="DEVOLUCION",
            estado="COMPLETADA", motivo="Cambio aprobado y completado",
            line_records=[
                LineaSolicitudPostventa(
                    empresa_clave=company_key, producto_id=item["id"],
                    compra_posicion=0, nombre=item["nombre"],
                    variante_ref=v["id"], cantidad=3,
                    precio_unitario=Decimal("100.00"),
                )
            ],
        )
        db.add(request)
        db.commit()
    payload = {
        "id": str(uuid4()), "solicitud_id": request_id,
        "sucursal_id": scope.a1.id, "variante_id": v["id"], "cantidad": 3,
        "motivo": "Prenda inspeccionada apta para venta", "apta_para_venta": True,
    }
    first = client.post("/api/admin/inventario/reingresos", json=payload, headers=scope.ah)
    assert first.status_code == 201, first.text
    assert first.json()["clase"] == "REINGRESO"
    assert first.json()["origen_tipo"] == "POSTVENTA"
    assert first.json()["origen_id"] == request_id
    repeated = client.post("/api/admin/inventario/reingresos", json=payload, headers=scope.ah)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    duplicate = client.post(
        "/api/admin/inventario/reingresos",
        json={**payload, "id": str(uuid4())}, headers=scope.ah,
    )
    assert duplicate.status_code == 409
    with session_factory() as db:
        row = db.get(Existencia, (scope.a.id, scope.a1.id, v["id"]))
        assert row.cantidad == 3 and row.cantidad_comprometida == 0
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 1


def test_cu07_transaction_rollback_on_audit_failure(client, scope, session_factory, monkeypatch):
    from app.inventario import api

    item = product(client, scope.ah, "Rollback de ajuste")
    v = variant(client, scope.ah, item["id"])

    def fail_audit(*args, **kwargs):
        raise RuntimeError("Fallo simulado al preparar auditoría")

    monkeypatch.setattr(api, "record_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        client.post(
            "/api/admin/inventario/ajustes", headers=scope.ah,
            json=adjustment(scope.a1, v["id"], 3, "INCREMENTO"),
        )
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 0
        assert db.scalar(select(func.count()).select_from(Existencia)) == 0

def test_cu08_catalog_scoped_search_filters_and_public_directory(client, scope):
    a = product(client, scope.ah, "Camisa lino", precio="120.00")
    another = product(client, scope.ah, "Vestido rojo", precio="250.00")
    other_tenant = product(client, scope.bh, "Camisa de empresa B", precio="90.00")
    variant(client, scope.ah, a["id"], talla="M", color="AZUL")
    variant(client, scope.ah, another["id"], talla="L", color="ROJO")
    variant(client, scope.bh, other_tenant["id"], talla="M", color="AZUL")

    stores = client.get("/api/catalogo/tiendas")
    assert stores.status_code == 200
    public_stores = {row["slug"] for row in stores.json()}
    assert {scope.a.slug, scope.b.slug}.issubset(public_stores)
    assert all(set(row) == {"slug", "nombre"} for row in stores.json())

    endpoint = f"/api/catalogo/productos?tienda={scope.a.slug}"
    page = client.get(endpoint)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 2
    assert {row["slug"] for row in page.json()["items"]} == {a["slug"], another["slug"]}
    assert client.get(endpoint + "&q=CAMISA").json()["total"] == 1
    assert client.get(endpoint + "&talla=m&color=azul").json()["items"][0]["id"] == a["id"]
    assert client.get(endpoint + "&talla=M&color=rojo").json()["total"] == 0
    assert client.get(endpoint + "&precio_min=100&precio_max=200").json()["items"][0]["id"] == a["id"]
    assert client.get(endpoint + f"&categoria_id={a['categoria_id']}").json()["total"] == 2
    assert client.get(endpoint + "&precio_min=400&precio_max=100").status_code == 422
    assert client.get(endpoint + "&categoria_id=0").status_code == 422
    assert client.get(endpoint + "&talla=" + "x" * 31).status_code == 422
    assert client.get("/api/catalogo/productos?tienda=tienda-no-existente").status_code == 404
    assert client.get(f"/api/catalogo/productos/{other_tenant['slug']}?tienda={scope.a.slug}").status_code == 404
    assert client.get(f"/api/catalogo/productos/{a['slug']}?tienda={scope.b.slug}").status_code == 404

    categories = client.get(f"/api/catalogo/categorias?tienda={scope.a.slug}")
    assert categories.status_code == 200, categories.text
    assert any(category["id"] == a["categoria_id"] for category in categories.json())
    assert all(set(category) == {"id", "nombre"} for category in categories.json())


def test_cu08_public_variants_and_availability_do_not_cross_tenants(client, scope):
    own = product(client, scope.ah, "Prenda de consulta")
    foreign = product(client, scope.bh, "Prenda ajena")
    v = variant(client, scope.ah, own["id"], talla="S", color="VERDE")
    hidden = variant(client, scope.ah, own["id"], talla="XL", color="NEGRO", activo=False)
    variant(client, scope.bh, foreign["id"], talla="S", color="VERDE")
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 4))

    base = f"/api/catalogo/productos/{own['slug']}"
    detail = client.get(base + f"?tienda={scope.a.slug}")
    assert detail.status_code == 200 and detail.json()["id"] == own["id"]
    listed = client.get(base + f"/variantes?tienda={scope.a.slug}")
    assert listed.status_code == 200
    assert listed.json() == [{"id": v["id"], "talla": "S", "color": "VERDE"}]
    assert hidden["id"] not in [row["id"] for row in listed.json()]
    assert client.get(base + f"/variantes?tienda={scope.b.slug}").status_code == 404

    variants = client.get(f"/api/catalogo/variantes?tienda={scope.a.slug}&limit=1&offset=0")
    assert variants.status_code == 200, variants.text
    assert variants.json()["total"] == 1
    assert variants.json()["items"][0] == {
        "id": v["id"], "producto_slug": own["slug"], "talla": "S", "color": "VERDE",
    }
    assert client.get(f"/api/catalogo/variantes?tienda={scope.b.slug}").json()["total"] == 1
    assert client.get("/api/catalogo/variantes?tienda=desconocida").status_code == 404

    available = client.get(base + f"/disponibilidad?tienda={scope.a.slug}&sucursal_id={scope.a1.id}&variante_id={v['id']}")
    assert available.status_code == 200
    assert available.json()["alcance"] == "STOCK_FISICO_REFERENCIAL"
    assert len(available.json()["items"]) == 1
    assert available.json()["items"][0]["saldo_registrado"] is True
    assert available.json()["items"][0]["hay_existencias_fisicas"] is True
    assert client.get(base + f"/disponibilidad?tienda={scope.b.slug}").status_code == 404


def test_cu08_accepts_cu07_migrated_role_without_bypassing_unknown_permissions(client, scope, session_factory):
    """Una base ya migrada para CU07 no debe ocultar los tenants en CU08."""
    from app.autenticacion_usuarios.permissions import ensure_company_roles, effective_role
    from app.models import PermisoRol

    with session_factory() as db:
        roles = ensure_company_roles(db, scope.a.id)
        member = db.get(MembresiaEmpresa, (scope.owner_a.id, scope.a.id))
        assert member is not None
        member.rol_empresa_id = roles["ADMINISTRADOR"].id
        manager = db.get(MembresiaEmpresa, (scope.operator.id, scope.a.id))
        assert manager is not None
        manager.rol = "ENCARGADO_SUCURSAL"
        manager.rol_empresa_id = roles["ENCARGADO_SUCURSAL"].id
        db.commit()
        assert effective_role(db, member) is not None
        assert effective_role(db, manager) is not None

    for headers, expected_role in (
        (scope.ah, "ADMINISTRADOR"),
        (scope.oh, "ENCARGADO_SUCURSAL"),
    ):
        response = client.get("/api/empresas", headers=headers)
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1
        company = response.json()[0]
        assert company["id"] == scope.a.id
        assert company["rol"] == expected_role
        assert "inventario.ajustar" in company["permisos"]

    # Conserva el comportamiento seguro frente a permisos verdaderamente desconocidos.
    with session_factory() as db:
        db.add(PermisoRol(
            rol_empresa_id=roles["ADMINISTRADOR"].id,
            codigo="permiso.desconocido",
        ))
        db.commit()
    invalid = client.get("/api/empresas", headers=scope.ah)
    assert invalid.status_code == 200
    assert invalid.json() == []


def test_cu08_optional_material_measures_and_season_filters(client, scope):
    own = product(
        client, scope.ah, "Abrigo de lana",
        material="Lana 80 %", medidas="M: 100 cm de pecho",
        temporada="Invierno",
    )
    other = product(client, scope.ah, "Camiseta ligera", temporada="Verano")
    external = product(client, scope.bh, "Abrigo ajeno", temporada="Invierno")
    assert own["material"] == "Lana 80 %"
    assert own["medidas"] == "M: 100 cm de pecho"
    assert own["temporada"] == "Invierno"
    page = client.get(f"/api/catalogo/productos?tienda={scope.a.slug}&temporada=invierno")
    assert page.status_code == 200
    assert [row["id"] for row in page.json()["items"]] == [own["id"]]
    assert all(row["id"] not in [other["id"], external["id"]] for row in page.json()["items"])
    assert client.get(
        f"/api/catalogo/productos?tienda={scope.a.slug}&temporada=" + "x" * 61
    ).status_code == 422
    edited = client.patch(
        f"/api/admin/productos/{own['id']}", headers=scope.ah,
        json={"material": "Algodón", "temporada": "Otoño", "medidas": "Largo 70 cm"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["material"] == "Algodón"
    assert edited.json()["temporada"] == "Otoño"
    assert client.get(f"/api/catalogo/productos?tienda={scope.a.slug}&temporada=invierno").json()["total"] == 0
    assert client.get(f"/api/catalogo/productos?tienda={scope.a.slug}&temporada=otoño").json()["total"] == 1


def test_cu08_availability_subtracts_committed_stock_and_marks_unknown(client, scope, session_factory):
    own = product(client, scope.ah, "Prenda comprometida")
    v = variant(client, scope.ah, own["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 5))
    url = (f"/api/catalogo/productos/{own['slug']}/disponibilidad"
           f"?tienda={scope.a.slug}&sucursal_id={scope.a1.id}&variante_id={v['id']}")
    first = client.get(url)
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["hay_disponibilidad"] is True
    assert first.json()["items"][0]["actualizado_en"] is not None
    with session_factory() as db:
        row = db.scalar(select(Existencia).where(
            Existencia.empresa_id == scope.a.id,
            Existencia.sucursal_id == scope.a1.id,
            Existencia.variante_id == v["id"],
        ))
        assert row is not None
        row.cantidad_comprometida = 5
        db.commit()
    committed = client.get(url)
    assert committed.status_code == 200
    state = committed.json()["items"][0]
    assert state["saldo_registrado"] is True
    assert state["hay_existencias_fisicas"] is True
    assert state["hay_disponibilidad"] is False

    not_recorded = client.get(
        f"/api/catalogo/productos/{own['slug']}/disponibilidad"
        f"?tienda={scope.a.slug}&sucursal_id={scope.a2.id}&variante_id={v['id']}"
    )
    unknown = not_recorded.json()["items"][0]
    assert unknown["saldo_registrado"] is False
    assert unknown["hay_disponibilidad"] is False
    assert unknown["actualizado_en"] is None
    assert client.get(url.replace(f"tienda={scope.a.slug}", f"tienda={scope.b.slug}")).status_code == 404


def test_cu08_public_branches_are_scoped_and_only_active(client, scope, session_factory):
    response = client.get(f"/api/catalogo/sucursales?tienda={scope.a.slug}")
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()} == {scope.a1.id, scope.a2.id}
    assert all(set(row) == {"id", "nombre"} for row in response.json())
    assert scope.b1.id not in {row["id"] for row in response.json()}
    assert client.get(f"/api/catalogo/sucursales?tienda={scope.b.slug}").json() == [
        {"id": scope.b1.id, "nombre": scope.b1.nombre}
    ]
    with session_factory() as db:
        db.get(Sucursal, scope.a2.id).activo = False
        db.commit()
    changed = client.get(f"/api/catalogo/sucursales?tienda={scope.a.slug}")
    assert {row["id"] for row in changed.json()} == {scope.a1.id}
    assert client.get("/api/catalogo/sucursales?tienda=desconocida").status_code == 404
    assert client.get("/api/catalogo/sucursales").status_code == 422


def test_cu09_stripe_checkout_paid_webhook_and_kardex_idempotent(
    client, scope, session_factory, monkeypatch,
):
    """El cobro de prueba no confirma una venta sin firma y stock revalidado."""
    import hashlib
    import hmac
    import json
    import time
    import stripe

    from app.models import Cliente
    from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_integracion_segura_para_pruebas")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_integracion_segura_para_pruebas")
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kwargs: SimpleNamespace(
        id="cs_test_compra_09", url="https://checkout.stripe.com/c/test", status="open"))
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", lambda *args, **kwargs:
                        SimpleNamespace(id="cs_test_compra_09", url="https://checkout.stripe.com/c/test", status="open"))

    item = product(client, scope.ah, "Prenda CU09", precio="120.00")
    selected = variant(client, scope.ah, item["id"], talla="M", color="AZUL")
    post_movement(client, scope.ah, movement(scope.a1, selected["id"], 4))
    with session_factory() as db:
        customer = Cliente(empresa_id=scope.a.id, nombre="Cliente para checkout",
                           correo="checkout@vestinova.test",
                           password_hash=scope.owner_a.password_hash, activo=True)
        db.add(customer)
        db.commit()
    token_result = client.post(f"/api/tiendas/{scope.a.slug}/cuenta/login",
                               json={"correo": "checkout@vestinova.test", "password": TEST_PASSWORD})
    assert token_result.status_code == 200
    auth_customer = {"Authorization": f"Bearer {token_result.json()['access_token']}"}
    purchase_id = str(uuid4())
    url = f"/api/tiendas/{scope.a.slug}/compras"
    payload = {
        "id": purchase_id, "sucursal_id": scope.a1.id,
        "entrega": "RETIRO", "items": [
            {"producto_id": item["id"], "variante_id": selected["id"], "cantidad": 2}
        ],
    }
    assert client.get(url + "/capacidades").json()["habilitado"] is True
    unauthorized = client.post(url + "/checkout", json=payload)
    assert unauthorized.status_code == 401
    created = client.post(url + "/checkout", json=payload, headers=auth_customer)
    assert created.status_code == 201, created.text
    assert created.json()["estado"] == "PAGO_PENDIENTE"
    assert created.json()["total"] == "240.00"
    replay = client.post(url + "/checkout", json=payload, headers=auth_customer)
    assert replay.status_code == 201
    assert replay.json()["checkout_url"] == created.json()["checkout_url"]
    altered = client.post(url + "/checkout", json={**payload, "sucursal_id": scope.a2.id}, headers=auth_customer)
    assert altered.status_code == 409

    initial = client.get(url + f"/{purchase_id}/estado", headers=auth_customer)
    assert initial.json()["estado"] == "PAGO_PENDIENTE"
    assert "comprobante" not in initial.json()
    with session_factory() as db:
        balance = db.get(Existencia, (scope.a.id, scope.a1.id, selected["id"]))
        assert balance.cantidad == 4

    event = {"id": "evt_test_001", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_test_compra_09", "client_reference_id": purchase_id,
        "payment_status": "paid", "currency": "bob", "amount_total": 24000,
        "metadata": {"compra_id": purchase_id}, "payment_intent": "pi_test_001",
    }}}
    raw = json.dumps(event, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = hmac.new(b"whsec_integracion_segura_para_pruebas",
                         str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    signed = {"stripe-signature": f"t={timestamp},v1={signature}",
              "content-type": "application/json"}
    assert client.post("/api/webhooks/stripe", content=raw).status_code == 400
    first = client.post("/api/webhooks/stripe", content=raw, headers=signed)
    assert first.status_code == 200, first.text
    second = client.post("/api/webhooks/stripe", content=raw, headers=signed)
    assert second.status_code == 200, second.text
    finished = client.get(url + f"/{purchase_id}/estado", headers=auth_customer)
    assert finished.status_code == 200
    assert finished.json()["estado"] == "CONFIRMADA"
    assert finished.json()["comprobante"]["entrega"] == "PENDIENTE"
    with session_factory() as db:
        balance = db.get(Existencia, (scope.a.id, scope.a1.id, selected["id"]))
        assert balance.cantidad == 2
        events = db.scalars(select(MovimientoInventario).where(
            MovimientoInventario.motivo == f"Compra digital {purchase_id}")).all()
        assert len(events) == 1
        assert events[0].usuario_id is None
        assert events[0].cliente_id is not None
        assert events[0].delta == -2
        assert db.get(CheckoutAttempt, purchase_id).estado == "CONFIRMADA"

    # Un cliente distinto no puede consultar un comprobante de otra cuenta.
    foreign = client.get(f"/api/tiendas/{scope.b.slug}/compras/{purchase_id}/estado", headers=auth_customer)
    assert foreign.status_code in (401, 404)


def test_cu09_webhook_payment_with_insufficient_stock_keeps_financial_incident(
    client, scope, session_factory, monkeypatch,
):
    import hashlib
    import hmac
    import json
    import time
    import stripe

    from app.models import Cliente
    from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_integracion_segura_para_pruebas")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_integracion_segura_para_pruebas")
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kwargs: SimpleNamespace(
        id="cs_test_sin_stock", url="https://checkout.stripe.com/c/test", status="open"))

    item = product(client, scope.ah, "Prenda sin saldo", precio="100.00")
    v = variant(client, scope.ah, item["id"])
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 1))
    with session_factory() as db:
        db.add(Cliente(empresa_id=scope.a.id, nombre="Cliente de incidencia",
                       correo="incidencia@vestinova.test",
                       password_hash=scope.owner_a.password_hash, activo=True))
        db.commit()
    credentials = client.post(f"/api/tiendas/{scope.a.slug}/cuenta/login", json={
        "correo": "incidencia@vestinova.test", "password": TEST_PASSWORD}).json()
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    pid = str(uuid4())
    url = f"/api/tiendas/{scope.a.slug}/compras"
    payload = {"id": pid, "sucursal_id": scope.a1.id,
               "entrega": "RETIRO", "items": [{"producto_id": item["id"], "variante_id": v["id"], "cantidad": 1}]}
    assert client.post(url + "/checkout", headers=headers, json=payload).status_code == 201
    # Otra operación retira la última unidad antes de la acreditación.
    post_movement(client, scope.ah, movement(scope.a1, v["id"], 1, "SALIDA"))
    event = {"id": "evt_test_002", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_test_sin_stock", "client_reference_id": pid, "payment_status": "paid",
        "currency": "bob", "amount_total": 10000,
        "metadata": {"compra_id": pid}, "payment_intent": "pi_test_002",
    }}}
    raw = json.dumps(event).encode()
    stamp = int(time.time())
    signature = hmac.new(b"whsec_integracion_segura_para_pruebas",
                         str(stamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    result = client.post("/api/webhooks/stripe", content=raw, headers={
        "stripe-signature": f"t={stamp},v1={signature}"})
    assert result.status_code == 200, result.text
    state = client.get(url + f"/{pid}/estado", headers=headers)
    assert state.json()["estado"] == "INCIDENCIA"
    assert "reembolso" in state.json()["detalle"]
    with session_factory() as db:
        assert db.get(CheckoutAttempt, pid).stripe_payment_id == "pi_test_002"
        assert db.get(Existencia, (scope.a.id, scope.a1.id, v["id"])).cantidad == 0
        assert db.scalar(select(func.count()).select_from(MovimientoInventario).where(
            MovimientoInventario.motivo == f"Compra digital {pid}")) == 0


def test_cu09_payment_gateway_missing_fails_closed(client, scope, monkeypatch):
    """4A: sin Stripe ninguna solicitud produce cobro ni registro."""
    from app.compras_reservas.compras import stripe_checkout
    monkeypatch.setattr(stripe_checkout, "_configuration", lambda: None)
    assert client.get(f"/api/tiendas/{scope.a.slug}/compras/capacidades").json()["habilitado"] is False
    order = client.post(f"/api/tiendas/{scope.a.slug}/compras/checkout", json={
        "id": str(uuid4()), "sucursal_id": scope.a1.id, "entrega": "RETIRO",
        "items": [{"producto_id": 1, "variante_id": 1, "cantidad": 1}],
    })
    # Sin sesión se exige autenticación, aun si el proveedor está caído.
    assert order.status_code == 401
    assert client.post("/api/webhooks/stripe", content=b"{}").status_code == 503
