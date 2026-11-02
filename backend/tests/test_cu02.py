"""CU02: aislamiento de personal, roles reales y autorización de sesiones existentes."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.models import Administrador, Empresa, MembresiaEmpresa, RolEmpresa, Sucursal
from app.permissions import ensure_company_roles
from app.password_policy import PASSWORD_POLICY_MESSAGE
from app.security import verify_password
from tests.conftest import TEST_PASSWORD


NEW_PASSWORD = "  NuevaClave!2026  "
READ_PERMISSIONS = ["catalogo.consultar", "sucursales.consultar", "inventario.consultar", "descarga.consultar"]
MANAGEMENT_PERMISSIONS = ["usuarios.consultar", "usuarios.crear", "usuarios.editar", "roles.consultar", "roles.gestionar", "sucursales.consultar"]


def login(client, correo, password=NEW_PASSWORD):
    response = client.post("/api/auth/login", json={"correo": correo, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def role(client, headers, permissions=READ_PERMISSIONS, name="Consulta de prendas"):
    response = client.post("/api/admin/roles", headers=headers, json={
        "nombre": name, "descripcion": "Perfil local de prueba", "permisos": permissions,
    })
    assert response.status_code == 201, response.text
    return response.json()


def person(client, scope, role_id=None, email=None, name="Persona de prueba", **changes):
    response = client.post("/api/admin/usuarios", headers=scope.ah, json={
        "nombre": name, "correo": email or f"persona-{uuid4().hex}@vestinova.test",
        "password": NEW_PASSWORD, "rol_id": role_id or scope.roles["CAJERO"],
        "sucursal_ids": [scope.a1.id], "activo": True, **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def cu02(client, administrator, auth, session_factory):
    with session_factory() as db:
        a = db.scalar(select(Empresa).join(MembresiaEmpresa).where(MembresiaEmpresa.administrador_id == administrator.id))
        ensure_company_roles(db, a.id)
        own_roles = {entry.codigo_sistema: entry.id for entry in db.scalars(select(RolEmpresa).where(RolEmpresa.empresa_id == a.id)).all()}
        db.get(MembresiaEmpresa, (administrator.id, a.id)).rol_empresa_id = own_roles["ADMINISTRADOR"]
        b = Empresa(slug=f"empresa-b-{uuid4().hex}", nombre="Empresa B independiente", activo=True)
        owner_b = Administrador(nombre="Identidad B", correo=f"owner-b-{uuid4().hex}@vestinova.test", password_hash=administrator.password_hash, activo=True)
        platform = Administrador(nombre="Plataforma sin empresa", correo=f"platform-{uuid4().hex}@vestinova.test", password_hash=administrator.password_hash, activo=True, es_superadministrador=True)
        db.add_all([b, owner_b, platform])
        db.flush()
        ensure_company_roles(db, b.id)
        other_roles = {entry.codigo_sistema: entry.id for entry in db.scalars(select(RolEmpresa).where(RolEmpresa.empresa_id == b.id)).all()}
        db.add(MembresiaEmpresa(administrador_id=owner_b.id, empresa_id=b.id, rol="ADMINISTRADOR", rol_empresa_id=other_roles["ADMINISTRADOR"], activo=True))
        a1 = Sucursal(empresa_id=a.id, codigo="CENTRO", nombre="Sucursal Centro", activo=True)
        a2 = Sucursal(empresa_id=a.id, codigo="NORTE", nombre="Sucursal Norte", activo=True)
        inactive = Sucursal(empresa_id=a.id, codigo="SUR", nombre="Sucursal Sur", activo=False)
        b1 = Sucursal(empresa_id=b.id, codigo="CENTRO", nombre="Sucursal ajena", activo=True)
        db.add_all([a1, a2, inactive, b1])
        db.commit()
    return SimpleNamespace(a=a, b=b, a1=a1, a2=a2, inactive=inactive, b1=b1,
        owner=administrator, owner_b=owner_b, platform=platform, roles=own_roles, other_roles=other_roles,
        ah={**auth, "X-Empresa-Id": str(a.id)},
        bh={**login(client, owner_b.correo, TEST_PASSWORD), "X-Empresa-Id": str(b.id)},
        ph=login(client, platform.correo, TEST_PASSWORD))


@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/acceso"), ("get", "/api/admin/permisos"),
    ("get", "/api/admin/roles"), ("post", "/api/admin/roles"),
    ("patch", "/api/admin/roles/1"), ("get", "/api/admin/usuarios"),
    ("post", "/api/admin/usuarios"), ("get", "/api/admin/usuarios/1"),
    ("patch", "/api/admin/usuarios/1"),
])
def test_cu02_requires_a_staff_session(client, method, path):
    response = getattr(client, method)(path, json={}) if method != "get" else client.get(path)
    assert response.status_code == 401


def test_cu02_reads_do_not_seed_or_mutate_legacy_memberships(client, auth, administrator, engine, session_factory):
    statements = []
    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RolEmpresa)) == 0
    event.listen(engine, "before_cursor_execute", record)
    try:
        for path in ["/api/admin/acceso", "/api/admin/permisos", "/api/admin/roles", "/api/admin/usuarios"]:
            response = client.get(path, headers=auth)
            assert response.status_code == 200, response.text
        assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", record)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RolEmpresa)) == 0
        membership = db.scalar(select(MembresiaEmpresa).where(MembresiaEmpresa.administrador_id == administrator.id))
        assert membership.rol_empresa_id is None


def test_roles_are_local_and_presets_are_protected(client, cu02):
    presets = client.get("/api/admin/roles", headers=cu02.ah).json()
    assert {entry["codigo_sistema"] for entry in presets} == {"ADMINISTRADOR", "ENCARGADO_SUCURSAL", "CAJERO", "OPERADOR"}
    assert all(entry["protegido"] and entry["activo"] and entry["empresa_id"] == cu02.a.id for entry in presets)
    for entry in presets:
        for patch in [{"nombre": "Otro nombre"}, {"activo": False}, {"permisos": []}]:
            assert client.patch(f"/api/admin/roles/{entry['id']}", headers=cu02.ah, json=patch).status_code == 409
    created = role(client, cu02.ah)
    assert created["codigo_sistema"] is None and created["protegido"] is False
    assert created["empresa_id"] == cu02.a.id and set(created["permisos"]) == set(READ_PERMISSIONS)
    assert created["id"] not in {entry["id"] for entry in client.get("/api/admin/roles", headers=cu02.bh).json()}
    assert client.patch(f"/api/admin/roles/{created['id']}", headers=cu02.bh, json={"nombre": "Ajeno"}).status_code == 404


def test_permission_catalog_is_closed_and_declares_dependencies(client, cu02):
    response = client.get("/api/admin/permisos", headers=cu02.ah)
    assert response.status_code == 200
    catalog = {entry["codigo"]: entry for entry in response.json()}
    assert len(catalog) == len(response.json())
    assert set(catalog["catalogo.gestionar"]["requiere"]) >= {"catalogo.consultar"}
    assert set(catalog["roles.gestionar"]["requiere"]) >= {"roles.consultar"}
    assert all("SaaS" not in code and "plataforma" not in code for code in catalog)
    for permissions in [["plataforma.administrar"], ["catalogo.gestionar"], ["roles.gestionar"], ["usuarios.crear"]]:
        response = client.post("/api/admin/roles", headers=cu02.ah, json={"nombre": "Inválido", "permisos": permissions})
        assert response.status_code == 422, response.text
    assert client.post("/api/admin/roles", headers=cu02.ah, json={"nombre": "Inyección", "permisos": [], "codigo_sistema": "ADMINISTRADOR"}).status_code == 422


def test_new_staff_is_normalized_hashed_and_tenant_scoped(client, cu02, session_factory):
    created = person(client, cu02, email="  NUEVA@VESTINOVA.TEST  ")
    assert created["correo"] == "nueva@vestinova.test"
    assert created["empresa_id"] == cu02.a.id and created["activo"] is True
    assert created["sucursal_ids"] == [cu02.a1.id]
    assert created["rol_sistema"] == "CAJERO" and created["rol_id"] == cu02.roles["CAJERO"]
    assert "password" not in str(created) and "hash" not in str(created)
    with session_factory() as db:
        identity = db.get(Administrador, created["id"])
        assert identity.password_hash.startswith("$argon2id$") and verify_password(NEW_PASSWORD, identity.password_hash)
        assert identity.es_superadministrador is False
        assert db.get(MembresiaEmpresa, (identity.id, cu02.b.id)) is None
    headers = login(client, created["correo"])
    assert client.get("/api/auth/contexto", headers=headers).json()["empresa"]["id"] == cu02.a.id
    assert client.get("/api/admin/usuarios", headers=headers).status_code == 403
    assert client.get("/api/plataforma/empresas/1", headers=headers).status_code in {404, 405}
    assert client.post("/api/plataforma/empresas", headers=headers, json={"nombre": "No permitido", "slug": "no-permitido", "administrador_id": created["id"]}).status_code == 403


def test_global_existing_email_is_not_linked_or_changed(client, cu02, session_factory):
    with session_factory() as db:
        before = db.get(Administrador, cu02.owner_b.id)
        state = (before.nombre, before.correo, before.password_hash, before.activo, before.es_superadministrador)
    response = client.post("/api/admin/usuarios", headers=cu02.ah, json={
        "nombre": "Intento de asociación", "correo": cu02.owner_b.correo.upper(), "password": NEW_PASSWORD,
        "rol_id": cu02.roles["CAJERO"], "sucursal_ids": [cu02.a1.id],
    })
    assert response.status_code == 409
    assert cu02.b.nombre not in response.text and cu02.owner_b.nombre not in response.text
    with session_factory() as db:
        after = db.get(Administrador, cu02.owner_b.id)
        assert (after.nombre, after.correo, after.password_hash, after.activo, after.es_superadministrador) == state
        assert db.get(MembresiaEmpresa, (after.id, cu02.a.id)) is None
    legacy = client.post("/api/admin/pertenencias", headers=cu02.ah, json={
        "administrador_id": cu02.owner_b.id, "rol": "CAJERO", "activo": True, "sucursal_ids": [cu02.a1.id],
    })
    assert legacy.status_code == 404


@pytest.mark.parametrize("change", [
    {"password": "short"}, {"password": "A" * 129 + "a1!"},
    {"password": "SinNumero!"}, {"password": "sinmayuscula1!"},
    {"password": "SinSimbolo123"}, {"sucursal_ids": [True]},
    {"sucursal_ids": [1, 1]}, {"rol_id": True}, {"activo": "false"},
    {"empresa_id": 123}, {"es_superadministrador": True},
])
def test_invalid_staff_payload_does_not_create_an_identity_or_echo_password(client, cu02, session_factory, change):
    email = f"invalid-{uuid4().hex}@vestinova.test"
    response = client.post("/api/admin/usuarios", headers=cu02.ah, json={
        "nombre": "Personal inválido", "correo": email, "password": NEW_PASSWORD,
        "rol_id": cu02.roles["CAJERO"], "sucursal_ids": [cu02.a1.id], **change,
    })
    assert response.status_code == 422, response.text
    assert str(change.get("password", NEW_PASSWORD)) not in response.text
    if "password" in change:
        assert response.json()["detail"] == PASSWORD_POLICY_MESSAGE
    with session_factory() as db:
        assert db.scalar(select(Administrador.id).where(Administrador.correo == email)) is None


def test_unicode_password_uses_the_shared_policy_without_trimming(client, cu02):
    password = "  Ábcdef١!  "
    created = person(client, cu02, password=password)
    assert login(client, created["correo"], password)
    response = client.post("/api/auth/login", json={"correo": created["correo"], "password": password.strip()})
    assert response.status_code == 401


@pytest.mark.parametrize("target", ["role", "foreign_branch", "inactive_branch"])
def test_foreign_role_or_unavailable_branch_rolls_back_the_entire_create(client, cu02, session_factory, target):
    email = f"foreign-{uuid4().hex}@vestinova.test"
    payload = {"nombre": "No debe persistir", "correo": email, "password": NEW_PASSWORD,
        "rol_id": cu02.roles["CAJERO"], "sucursal_ids": [cu02.a1.id]}
    if target == "role":
        payload["rol_id"] = cu02.other_roles["CAJERO"]
    else:
        payload["sucursal_ids"] = [cu02.b1.id if target == "foreign_branch" else cu02.inactive.id]
    response = client.post("/api/admin/usuarios", headers=cu02.ah, json=payload)
    assert response.status_code == 404, response.text
    with session_factory() as db:
        assert db.scalar(select(Administrador.id).where(Administrador.correo == email)) is None


def test_personnel_listing_search_filters_and_pagination_are_server_side(client, cu02):
    first = person(client, cu02, name="Ana Álvarez")
    second = person(client, cu02, name="Ana Pérez", activo=False)
    person(client, cu02, name="Bruno Soto")
    page = client.get("/api/admin/usuarios?q=Ana&estado=todos&limit=1&offset=1", headers=cu02.ah)
    assert page.status_code == 200
    assert page.json()["total"] == 2 and page.json()["limit"] == 1 and page.json()["offset"] == 1
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0]["id"] in {first["id"], second["id"]}
    active = client.get("/api/admin/usuarios?q=Ana&estado=activo", headers=cu02.ah).json()
    assert [entry["id"] for entry in active["items"]] == [first["id"]]
    inactive = client.get("/api/admin/usuarios?estado=inactivo", headers=cu02.ah).json()
    assert [entry["id"] for entry in inactive["items"]] == [second["id"]]
    filtered = client.get(f"/api/admin/usuarios?rol_id={cu02.roles['ADMINISTRADOR']}", headers=cu02.ah).json()
    assert [entry["id"] for entry in filtered["items"]] == [cu02.owner.id]
    assert cu02.owner_b.correo not in client.get("/api/admin/usuarios", headers=cu02.ah).text
    for query in ["limit=0", "limit=101", "offset=-1", "estado=incorrecto", "rol_id=0"]:
        assert client.get(f"/api/admin/usuarios?{query}", headers=cu02.ah).status_code == 422


def test_membership_name_role_and_state_changes_do_not_change_global_identity_or_other_company(client, cu02, session_factory):
    created = person(client, cu02)
    with session_factory() as db:
        identity = db.get(Administrador, created["id"])
        before = (identity.nombre, identity.correo, identity.password_hash, identity.activo, identity.es_superadministrador)
        db.add(MembresiaEmpresa(administrador_id=identity.id, empresa_id=cu02.b.id, rol="CAJERO", rol_empresa_id=cu02.other_roles["CAJERO"], activo=True, nombre="Nombre de empresa B"))
        db.commit()
    headers = login(client, created["correo"])
    response = client.patch(f"/api/admin/usuarios/{created['id']}", headers=cu02.ah, json={"nombre": "Nombre propio A", "activo": False})
    assert response.status_code == 200, response.text
    assert response.json()["nombre"] == "Nombre propio A" and response.json()["activo"] is False
    assert client.get("/api/admin/acceso", headers={**headers, "X-Empresa-Id": str(cu02.a.id)}).status_code == 403
    other = client.get("/api/admin/acceso", headers={**headers, "X-Empresa-Id": str(cu02.b.id)})
    assert other.status_code == 200 and other.json()["nombre"] == "Nombre de empresa B"
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    with session_factory() as db:
        identity = db.get(Administrador, created["id"])
        assert (identity.nombre, identity.correo, identity.password_hash, identity.activo, identity.es_superadministrador) == before
        assert db.get(MembresiaEmpresa, (identity.id, cu02.b.id)).activo is True
    for patch in [{"correo": "otro@vestinova.test"}, {"password": NEW_PASSWORD}, {"es_superadministrador": True}, {"empresa_id": cu02.b.id}, {"activo_global": False}]:
        assert client.patch(f"/api/admin/usuarios/{created['id']}", headers=cu02.ah, json=patch).status_code == 422
    assert client.get(f"/api/admin/usuarios/{cu02.owner_b.id}", headers=cu02.ah).status_code == 404
    assert client.patch(f"/api/admin/usuarios/{cu02.owner_b.id}", headers=cu02.ah, json={"activo": False}).status_code == 404


def test_custom_permission_changes_affect_existing_sessions_and_keep_branch_scope(client, cu02):
    custom = role(client, cu02.ah)
    created = person(client, cu02, role_id=custom["id"])
    headers = login(client, created["correo"])
    access = client.get("/api/admin/acceso", headers=headers).json()
    assert access["rol_sistema"] is None and access["rol_id"] == custom["id"]
    assert set(access["permisos"]) == set(READ_PERMISSIONS)
    assert client.get("/api/admin/productos", headers=headers).status_code == 200
    assert client.get(f"/api/admin/inventario/existencias?sucursal_id={cu02.a1.id}", headers=headers).status_code == 200
    for branch_id in [cu02.a2.id, cu02.b1.id]:
        assert client.get(f"/api/admin/inventario/existencias?sucursal_id={branch_id}", headers=headers).status_code == 404
    assert client.post("/api/admin/productos", headers=headers, json={"nombre": "Sin permiso", "precio": "20.00"}).status_code == 403
    changed = client.patch(f"/api/admin/roles/{custom['id']}", headers=cu02.ah, json={"permisos": []})
    assert changed.status_code == 200, changed.text
    assert client.get("/api/admin/productos", headers=headers).status_code == 403
    assert client.get("/api/movil/descarga", headers=headers).status_code == 403
    assert client.get("/api/admin/acceso", headers=headers).json()["permisos"] == []
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.patch(f"/api/admin/roles/{custom['id']}", headers=cu02.ah, json={"activo": False}).status_code == 200
    assert client.get("/api/admin/acceso", headers=headers).status_code == 403


def test_custom_write_permission_is_enforced_by_the_existing_product_api(client, cu02):
    custom = role(client, cu02.ah, ["catalogo.consultar", "catalogo.gestionar"])
    created = person(client, cu02, role_id=custom["id"], sucursal_ids=[])
    headers = login(client, created["correo"])
    response = client.post("/api/admin/productos", headers=headers, json={"nombre": "Prenda autorizada", "precio": "19.90"})
    assert response.status_code == 201, response.text
    assert response.json()["precio"] == "19.90" and response.json()["moneda"] == "BOB"
    assert client.post("/api/admin/sucursales", headers=headers, json={"codigo": "NO", "nombre": "Sin permiso"}).status_code == 403


def test_delegated_role_manager_cannot_grant_permissions_it_does_not_have(client, cu02):
    manager = role(client, cu02.ah, MANAGEMENT_PERMISSIONS, "Gestión delegada")
    created = person(client, cu02, role_id=manager["id"])
    headers = login(client, created["correo"])
    allowed = client.post("/api/admin/roles", headers=headers, json={"nombre": "Subperfil", "permisos": ["roles.consultar"]})
    assert allowed.status_code == 201, allowed.text
    denied = client.post("/api/admin/roles", headers=headers, json={"nombre": "Escalamiento", "permisos": ["catalogo.consultar", "catalogo.gestionar"]})
    assert denied.status_code == 403, denied.text
    denied_update = client.patch(f"/api/admin/roles/{manager['id']}", headers=headers, json={"permisos": MANAGEMENT_PERMISSIONS + ["catalogo.consultar"]})
    assert denied_update.status_code == 403, denied_update.text
    denied_admin = client.patch(f"/api/admin/usuarios/{created['id']}", headers=headers, json={"rol_id": cu02.roles["ADMINISTRADOR"], "sucursal_ids": []})
    assert denied_admin.status_code == 403, denied_admin.text


def test_last_active_system_administrator_is_protected_from_role_and_state_changes(client, cu02):
    custom = role(client, cu02.ah, [entry["codigo"] for entry in client.get("/api/admin/permisos", headers=cu02.ah).json()], "Todos los permisos empresariales")
    person(client, cu02, role_id=custom["id"], sucursal_ids=[])
    for patch in [{"activo": False}, {"rol_id": custom["id"], "sucursal_ids": []}, {"rol_id": cu02.roles["CAJERO"], "sucursal_ids": [cu02.a1.id]}]:
        response = client.patch(f"/api/admin/usuarios/{cu02.owner.id}", headers=cu02.ah, json=patch)
        assert response.status_code == 409, response.text
    legacy = client.post("/api/admin/pertenencias", headers=cu02.ah, json={"administrador_id": cu02.owner.id, "rol": "CAJERO", "activo": True, "sucursal_ids": [cu02.a1.id]})
    assert legacy.status_code == 409
    second = person(client, cu02, role_id=cu02.roles["ADMINISTRADOR"], sucursal_ids=[])
    assert second["rol_sistema"] == "ADMINISTRADOR"
    assert client.patch(f"/api/admin/usuarios/{cu02.owner.id}", headers=cu02.ah, json={"activo": False}).status_code == 200
    assert client.get("/api/admin/usuarios", headers=cu02.ah).status_code == 403


def test_globally_inactive_administrator_cannot_satisfy_the_last_admin_invariant(client, cu02, session_factory):
    second = person(client, cu02, role_id=cu02.roles["ADMINISTRADOR"], sucursal_ids=[])
    with session_factory() as db:
        db.get(Administrador, second["id"]).activo = False
        db.commit()
    response = client.patch(f"/api/admin/usuarios/{cu02.owner.id}", headers=cu02.ah, json={"activo": False})
    assert response.status_code == 409


def test_platform_and_customer_accounts_do_not_receive_company_management_access(client, cu02):
    assert client.get("/api/admin/usuarios", headers=cu02.ph).status_code == 403
    customer = client.post(f"/api/tiendas/{cu02.a.slug}/cuenta/registro", json={"nombre": "Cliente independiente", "correo": "cliente-cu02@vestinova.test", "password": NEW_PASSWORD})
    assert customer.status_code == 201, customer.text
    headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}
    for path in ["/api/admin/usuarios", "/api/admin/roles", "/api/admin/permisos", "/api/admin/acceso"]:
        assert client.get(path, headers=headers).status_code in {401, 403}


def test_reactivation_cannot_regrant_a_branch_outside_the_managers_authority(client, cu02):
    capabilities = sorted(set(MANAGEMENT_PERMISSIONS + READ_PERMISSIONS))
    profile = role(client, cu02.ah, capabilities, "Gestor con sucursal limitada")
    manager = person(client, cu02, role_id=profile["id"], sucursal_ids=[cu02.a1.id])
    headers = login(client, manager["correo"])
    target = person(client, cu02, activo=False, sucursal_ids=[cu02.a2.id])
    explicit = client.patch(f"/api/admin/usuarios/{target['id']}", headers=headers,
                            json={"activo": True, "sucursal_ids": [cu02.a2.id]})
    assert explicit.status_code == 403
    implicit = client.patch(f"/api/admin/usuarios/{target['id']}", headers=headers, json={"activo": True})
    assert implicit.status_code == 403
    assert client.get(f"/api/admin/usuarios/{target['id']}", headers=cu02.ah).json()["activo"] is False
    owned = person(client, cu02, activo=False, sucursal_ids=[cu02.a1.id])
    assert client.patch(f"/api/admin/usuarios/{owned['id']}", headers=headers, json={"activo": True}).status_code == 200


def test_reactivation_preserves_historical_inactive_branches_within_authority(client, cu02):
    capabilities = sorted(set(MANAGEMENT_PERMISSIONS + READ_PERMISSIONS))
    profile = role(client, cu02.ah, capabilities, "Gestor de concesiones historicas")
    manager = person(client, cu02, role_id=profile["id"], sucursal_ids=[cu02.a1.id])
    headers = login(client, manager["correo"])
    own = person(client, cu02, activo=False, sucursal_ids=[cu02.a1.id])
    other = person(client, cu02, activo=False, sucursal_ids=[cu02.a2.id])
    for branch in (cu02.a1, cu02.a2):
        response = client.patch(f"/api/admin/sucursales/{branch.id}", headers=cu02.ah, json={"activo": False})
        assert response.status_code == 200, response.text
    response = client.patch(f"/api/admin/usuarios/{own['id']}", headers=headers, json={"activo": True})
    assert response.status_code == 200, response.text
    assert response.json()["sucursal_ids"] == [cu02.a1.id]
    assert client.patch(f"/api/admin/usuarios/{other['id']}", headers=headers, json={"activo": True}).status_code == 403
    response = client.patch(f"/api/admin/usuarios/{other['id']}", headers=cu02.ah, json={"activo": True})
    assert response.status_code == 200, response.text
    assert response.json()["sucursal_ids"] == [cu02.a2.id]
