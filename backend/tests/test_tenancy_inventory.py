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
from tests.conftest import TEST_PASSWORD


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
    assert set(a) == {"id", "slug", "nombre", "descripcion", "precio", "moneda", "imagen_url", "activo", "creado_en", "actualizado_en"}
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
