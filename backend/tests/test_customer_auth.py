"""Flujos de cuenta reales contra FastAPI/SQLAlchemy; SQLite aislado, no servidor HTTP."""
from datetime import timedelta

import jwt
import pytest
from sqlalchemy import func, select

from app.customer_auth import CLIENT_JWT_AUDIENCE
from app.models import Administrador, Cliente, Empresa, SesionCliente, utc_now
from app.password_policy import PASSWORD_POLICY_MESSAGE
from app.security import JWT_ISSUER, hash_password, verify_password
from tests.conftest import TEST_SECRET


PASSWORD = "UnaClave!2026"


@pytest.fixture
def stores(session_factory):
    with session_factory() as db:
        first = Empresa(slug="tienda-uno", nombre="Tienda Uno", activo=True)
        second = Empresa(slug="tienda-dos", nombre="Tienda Dos", activo=True)
        inactive = Empresa(slug="tienda-inactiva", nombre="Tienda inactiva", activo=False)
        db.add_all([first, second, inactive])
        db.commit()
        return first, second, inactive


def register(client, slug="tienda-uno", **changes):
    return client.post(f"/api/tiendas/{slug}/cuenta/registro",
                       json={"nombre": "Cliente de prueba", "correo": "cliente@vestinova.test", "password": PASSWORD, **changes})


def token_headers(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_store_context_is_public_minimal_and_requires_active_company(client, stores):
    assert client.get("/api/tiendas/tienda-uno").json() == {"slug": "tienda-uno", "nombre": "Tienda Uno"}
    assert client.get("/api/tiendas/tienda-uno").headers["cache-control"] == "no-store"
    for slug in ["no-existe", "tienda-inactiva"]:
        assert client.get(f"/api/tiendas/{slug}").status_code == 404
        assert register(client, slug).status_code == 404
        assert client.post(f"/api/tiendas/{slug}/cuenta/login", json={"correo": "x@x.test", "password": PASSWORD}).status_code == 404


def test_register_assigns_only_customer_role_argon2_and_persisted_session(client, stores, session_factory):
    response = register(client, nombre="  Cliente nuevo  ", correo=" CLIENTE@VESTINOVA.TEST ")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["cliente"] == {"id": data["cliente"]["id"], "nombre": "Cliente nuevo", "correo": "cliente@vestinova.test",
                               "rol": "CLIENTE", "empresa": {"slug": "tienda-uno", "nombre": "Tienda Uno"}}
    assert "password" not in str(data["cliente"])
    assert response.headers["cache-control"] == "no-store"
    claims = jwt.decode(data["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=CLIENT_JWT_AUDIENCE)
    assert claims["tipo"] == "cliente" and claims["empresa_id"] == stores[0].id
    with session_factory() as db:
        stored = db.get(Cliente, data["cliente"]["id"])
        assert stored.empresa_id == stores[0].id and stored.password_hash.startswith("$argon2id$")
        assert verify_password(PASSWORD, stored.password_hash)
        assert db.get(SesionCliente, claims["jti"]).cliente_id == stored.id
        assert db.scalar(select(func.count()).select_from(Administrador)) == 0
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers=token_headers(response)).json() == data["cliente"]


def test_email_uniqueness_is_per_company_and_personnel_identity_is_independent(client, stores, administrator, session_factory):
    first = register(client, correo=administrator.correo)
    assert first.status_code == 201
    assert register(client, correo=f" {administrator.correo.upper()} ").status_code == 409
    second = register(client, "tienda-dos", correo=administrator.correo, password="OtraClave!2026")
    assert second.status_code == 201
    assert first.json()["cliente"]["id"] != second.json()["cliente"]["id"]
    assert client.post("/api/tiendas/tienda-dos/cuenta/login", json={"correo": administrator.correo, "password": PASSWORD}).status_code == 401
    assert client.post("/api/tiendas/tienda-dos/cuenta/login", json={"correo": administrator.correo, "password": "OtraClave!2026"}).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Cliente)) == 2
        assert db.scalar(select(func.count()).select_from(SesionCliente)) == 3
        assert db.get(Administrador, administrator.id).password_hash == administrator.password_hash


@pytest.mark.parametrize("field,value", [("rol", "ADMINISTRADOR"), ("empresa_id", 2), ("es_superadministrador", True), ("sucursal_ids", [1]), ("permisos", ["todos"])])
def test_public_registration_rejects_personnel_authority_and_company_override(client, stores, session_factory, field, value):
    assert register(client, **{field: value}).status_code == 422
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Cliente)) == 0
        assert db.scalar(select(func.count()).select_from(SesionCliente)) == 0
        assert db.scalar(select(func.count()).select_from(Administrador)) == 0


@pytest.mark.parametrize("password", ["Aa1!aaa", "Aa1!" + "a" * 125, "aa1!aaaa", "AA1!AAAA", "Aaa!aaaa", "Aa12aaaa", "Aa12aa a"])
def test_registration_enforces_every_password_condition_without_reflecting_secret(client, stores, session_factory, password):
    result = register(client, password=password)
    assert result.status_code == 422
    assert result.json() == {"detail": PASSWORD_POLICY_MESSAGE}
    assert password not in result.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Cliente)) == 0


@pytest.mark.parametrize("password", ["Aa1!aaaa", "Aa1!" + "a" * 124, " Aa1!aaa "])
def test_password_boundaries_and_spaces_are_preserved(client, stores, password):
    registered = register(client, password=password)
    assert registered.status_code == 201
    assert client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": "cliente@vestinova.test", "password": password}).status_code == 200
    if password != password.strip():
        assert client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": "cliente@vestinova.test", "password": password.strip()}).status_code == 401


@pytest.mark.parametrize("changes", [{"nombre": "  "}, {"nombre": "x"}, {"nombre": "n" * 121}, {"correo": "sin-arroba"}, {"correo": "a b@correo.test"}])
def test_register_validates_profile_fields(client, stores, changes):
    assert register(client, **changes).status_code == 422


def test_customer_login_does_not_impose_new_policy_on_existing_password(client, stores, session_factory):
    old_hash = hash_password("abc")
    with session_factory() as db:
        old = Cliente(empresa_id=stores[0].id, nombre="Cuenta anterior", correo="anterior@vestinova.test", password_hash=old_hash, activo=True)
        db.add(old)
        db.commit()
        account_id = old.id
    result = client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": " ANTERIOR@VESTINOVA.TEST ", "password": "abc"})
    assert result.status_code == 200
    with session_factory() as db:
        assert db.get(Cliente, account_id).password_hash == old_hash


def test_bad_customer_credentials_do_not_disclose_account_existence(client, stores):
    assert register(client).status_code == 201
    for correo, password in [("cliente@vestinova.test", "incorrecta"), ("no-existe@vestinova.test", PASSWORD)]:
        result = client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": correo, "password": password})
        assert result.status_code == 401
        assert result.json() == {"detail": "Correo o contraseña incorrectos."}


def test_customer_session_cannot_be_reassigned_to_another_existing_account_in_same_store(client, stores):
    first = register(client)
    second = register(client, correo="otro@vestinova.test")
    claims = jwt.decode(first.json()["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=CLIENT_JWT_AUDIENCE)
    claims["sub"] = str(second.json()["cliente"]["id"])
    forged = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


@pytest.mark.parametrize("path,method", [("/api/auth/me", "get"), ("/api/auth/contexto", "get"), ("/api/auth/logout", "post"),
                                          ("/api/empresas", "get"), ("/api/admin/productos", "get"), ("/api/admin/productos", "post"),
                                          ("/api/admin/sucursales", "get"), ("/api/admin/pertenencias", "get"), ("/api/movil/descarga", "get"),
                                          ("/api/plataforma/empresas", "post")])
def test_customer_token_never_grants_personnel_access(client, stores, path, method):
    headers = token_headers(register(client))
    result = getattr(client, method)(path, headers=headers, **({"json": {}} if method == "post" else {}))
    assert result.status_code == 401, result.text


def test_customer_session_cannot_move_between_stores_or_use_personnel_token(client, stores, auth):
    own = register(client)
    headers = token_headers(own)
    assert client.get("/api/tiendas/tienda-dos/cuenta/me", headers=headers).status_code == 401
    assert client.post("/api/tiendas/tienda-dos/cuenta/logout", headers=headers).status_code == 401
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers={**headers, "X-Empresa-Id": str(stores[1].id)}).status_code == 200
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers=auth).status_code == 401
    assert client.get("/api/tiendas/tienda-uno/cuenta/me").status_code == 401


def test_logout_revokes_only_own_session_and_same_email_other_store_is_independent(client, stores, session_factory):
    own = register(client)
    other_store = register(client, "tienda-dos")
    same_store = client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": "cliente@vestinova.test", "password": PASSWORD})
    headers = token_headers(own)
    assert client.post("/api/tiendas/tienda-uno/cuenta/logout", headers=headers).status_code == 204
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers=headers).status_code == 401
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers=token_headers(same_store)).status_code == 200
    assert client.get("/api/tiendas/tienda-dos/cuenta/me", headers=token_headers(other_store)).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(SesionCliente).where(SesionCliente.revocada.is_(True))) == 1


@pytest.mark.parametrize("mutation,expected", [("inactive_customer", 401), ("inactive_company", 404), ("expired_session", 401), ("revoked_session", 401)])
def test_every_restore_rechecks_account_store_and_persisted_session(client, stores, session_factory, mutation, expected):
    registered = register(client)
    with session_factory() as db:
        if mutation == "inactive_customer":
            db.get(Cliente, registered.json()["cliente"]["id"]).activo = False
        elif mutation == "inactive_company":
            db.get(Empresa, stores[0].id).activo = False
        elif mutation == "expired_session":
            db.scalar(select(SesionCliente)).expira_en = utc_now() - timedelta(seconds=1)
        else:
            db.scalar(select(SesionCliente)).revocada = True
        db.commit()
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers=token_headers(registered)).status_code == expected
    if mutation == "inactive_customer":
        denied = client.post("/api/tiendas/tienda-uno/cuenta/login", json={"correo": "cliente@vestinova.test", "password": PASSWORD})
        assert denied.json() == {"detail": "Correo o contraseña incorrectos."}


@pytest.mark.parametrize("modification", [{"tipo": "administrador"}, {"aud": "vestinova-administracion"}, {"empresa_id": 999}, {"sub": "999"}, {"jti": "ausente"}, {"exp": 0}])
def test_signed_claims_still_require_customer_company_and_live_session(client, stores, modification):
    registered = register(client)
    claims = jwt.decode(registered.json()["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=CLIENT_JWT_AUDIENCE)
    claims.update(modification)
    forged = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
    assert client.get("/api/tiendas/tienda-uno/cuenta/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
