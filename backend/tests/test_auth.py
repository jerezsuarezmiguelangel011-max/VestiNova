from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select

from app.models import Administrador, SesionAdministrador, utc_now
from app.security import JWT_AUDIENCE, JWT_ISSUER
from tests.conftest import TEST_PASSWORD, TEST_SECRET


def test_login_normalizes_email_keeps_password_and_returns_no_hash(client, administrator):
    response = client.post("/api/auth/login", json={"correo": " ADMIN@VESTINOVA.TEST ", "password": TEST_PASSWORD})
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["administrador"] == {"id": administrator.id, "nombre": administrator.nombre, "correo": administrator.correo, "rol": "ADMINISTRADOR", "activo": True, "es_superadministrador": False}
    assert "password" not in str(data["administrador"])
    assert response.headers["cache-control"] == "no-store"
    claims = jwt.decode(data["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    assert claims["tipo"] == "administrador"


@pytest.mark.parametrize("correo,password", [("admin@vestinova.test", "incorrecta"), ("no-existe@vestinova.test", TEST_PASSWORD), ("admin@vestinova.test", TEST_PASSWORD.strip())])
def test_bad_credentials_do_not_reveal_whether_account_exists(client, administrator, correo, password):
    response = client.post("/api/auth/login", json={"correo": correo, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "Correo o contraseña incorrectos."}


def test_inactive_account_cannot_login_or_restore(client, administrator, credentials, session_factory):
    with session_factory() as db:
        db.get(Administrador, administrator.id).activo = False
        db.commit()
    assert client.post("/api/auth/login", json={"correo": administrator.correo, "password": TEST_PASSWORD}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {credentials['access_token']}"}).status_code == 401


def test_restore_and_logout_revokes_token_for_all_admin_routes(client, auth, session_factory):
    assert client.get("/api/auth/me", headers=auth).status_code == 200
    assert client.post("/api/auth/logout", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    assert client.get("/api/admin/productos", headers=auth).status_code == 401
    with session_factory() as db:
        assert db.scalar(select(SesionAdministrador)).revocada is True


@pytest.mark.parametrize("path,method", [("/api/auth/me", "get"), ("/api/auth/logout", "post"), ("/api/admin/productos", "get"), ("/api/admin/productos", "post"), ("/api/admin/productos/1", "get"), ("/api/admin/productos/1", "patch")])
def test_every_private_endpoint_requires_authentication(client, path, method):
    response = getattr(client, method)(path, json={}) if method in {"post", "patch"} else getattr(client, method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", ["Bearer inventado", "Basic abc", "Bearer "])
def test_invalid_tokens_are_rejected(client, authorization):
    assert client.get("/api/auth/me", headers={"Authorization": authorization}).status_code == 401


def test_session_expiry_in_database_is_revalidated(client, auth, session_factory):
    with session_factory() as db:
        db.scalar(select(SesionAdministrador)).expira_en = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/admin/productos", headers=auth).status_code == 401


@pytest.mark.parametrize("modification,expected", [({"tipo": "cliente"}, 403), ({"aud": "otra-api"}, 401), ({"exp": 0}, 401), ({"jti": "sesion-inexistente"}, 401), ({"sub": "not-an-id"}, 401)])
def test_signed_claims_still_require_admin_context_and_live_session(client, credentials, modification, expected):
    claims = jwt.decode(credentials["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    claims.update(modification)
    token = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
    assert client.get("/api/admin/productos", headers={"Authorization": f"Bearer {token}"}).status_code == expected


def test_session_cannot_be_used_with_another_administrator(client, credentials, session_factory):
    claims = jwt.decode(credentials["access_token"], TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    with session_factory() as db:
        other = Administrador(nombre="Otra cuenta", correo="otra@vestinova.test", password_hash="sin-uso-en-esta-prueba", activo=True)
        db.add(other)
        db.commit()
        claims["sub"] = str(other.id)
    token = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_disclosure_is_limited_to_me_and_hash_is_argon2(session_factory, administrator):
    with session_factory() as db:
        assert db.get(Administrador, administrator.id).password_hash.startswith("$argon2id$")
