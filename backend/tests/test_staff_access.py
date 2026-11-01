"""Diferenciación de actores y pertenencia empresarial de CU01."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa, Sucursal
from scripts import create_admin, list_access_contexts
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def access_scope(administrator, session_factory):
    with session_factory() as db:
        company = db.scalar(select(Empresa).join(MembresiaEmpresa).where(MembresiaEmpresa.administrador_id == administrator.id))
        other = Empresa(slug="otra-empresa", nombre="Otra empresa", activo=True)
        db.add(other)
        db.flush()
        own = Sucursal(empresa_id=company.id, codigo="CENTRO", nombre="Sucursal Centro", activo=True)
        ungranted = Sucursal(empresa_id=company.id, codigo="NORTE", nombre="Sucursal Norte", activo=True)
        inactive = Sucursal(empresa_id=company.id, codigo="SUR", nombre="Sucursal Sur", activo=False)
        foreign = Sucursal(empresa_id=other.id, codigo="OTRA", nombre="Sucursal ajena", activo=True)
        db.add_all([own, ungranted, inactive, foreign])
        db.flush()
        accounts = {}
        for role in ["ENCARGADO_SUCURSAL", "CAJERO", "OPERADOR"]:
            account = Administrador(nombre=f"Cuenta {role}", correo=f"{role.lower()}@vestinova.test",
                                    password_hash=administrator.password_hash, activo=True)
            db.add(account)
            db.flush()
            db.add(MembresiaEmpresa(administrador_id=account.id, empresa_id=company.id, rol=role, activo=True))
            db.flush()
            db.add_all([AccesoSucursal(administrador_id=account.id, empresa_id=company.id, sucursal_id=own.id),
                        AccesoSucursal(administrador_id=account.id, empresa_id=company.id, sucursal_id=inactive.id)])
            accounts[role] = account
        platform = Administrador(nombre="Plataforma", correo="plataforma@vestinova.test", password_hash=administrator.password_hash,
                                 activo=True, es_superadministrador=True)
        db.add(platform)
        db.commit()
        return SimpleNamespace(company=company, other=other, own=own, ungranted=ungranted, inactive=inactive,
                               foreign=foreign, accounts=accounts, platform=platform)


def staff_login(client, account):
    login = client.post("/api/auth/login", json={"correo": account.correo, "password": TEST_PASSWORD})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.parametrize("role", ["ENCARGADO_SUCURSAL", "CAJERO", "OPERADOR"])
def test_staff_actor_context_uses_database_membership_and_only_authorized_active_branches(client, access_scope, role):
    account = access_scope.accounts[role]
    headers = staff_login(client, account)
    identity = client.get("/api/auth/me", headers=headers).json()
    assert identity["es_superadministrador"] is False
    assert identity["rol"] == "ADMINISTRADOR"  # Etiqueta técnica compatible, nunca autorización de empresa.
    companies = client.get("/api/empresas", headers=headers).json()
    assert companies == [{"id": access_scope.company.id, "slug": access_scope.company.slug, "nombre": access_scope.company.nombre, "activo": True, "rol": role}]
    context = client.get("/api/auth/contexto", headers={**headers, "X-Empresa-Id": str(access_scope.company.id)})
    assert context.status_code == 200 and context.headers["cache-control"] == "no-store"
    assert context.json()["empresa"] == companies[0]
    assert [branch["id"] for branch in context.json()["sucursales"]] == [access_scope.own.id]
    assert client.get("/api/auth/contexto", headers={**headers, "X-Empresa-Id": str(access_scope.other.id)}).status_code == 403
    assert client.get("/api/admin/productos", headers=headers).status_code == 200
    assert client.post("/api/admin/productos", headers=headers, json={"nombre": "No permitido", "precio": "10.00"}).status_code == 403
    assert client.post("/api/admin/sucursales", headers=headers, json={"codigo": "X", "nombre": "No permitido"}).status_code == 403
    assert client.get("/api/admin/pertenencias", headers=headers).status_code == 403
    assert client.post("/api/admin/inventario/movimientos", headers=headers,
                       json={"id": str(uuid4()), "sucursal_id": access_scope.own.id, "variante_id": 1, "tipo": "ENTRADA", "cantidad": 1, "motivo": "No ampliar CU08"}).status_code == 403
    assert client.post("/api/plataforma/empresas", headers=headers,
                       json={"nombre": "No permitido", "slug": "sin-acceso", "administrador_id": account.id}).status_code == 403


def test_company_administrator_context_has_all_active_own_branches(client, auth, access_scope):
    response = client.get("/api/auth/contexto", headers=auth)
    assert response.status_code == 200
    assert response.json()["empresa"]["rol"] == "ADMINISTRADOR"
    assert {branch["id"] for branch in response.json()["sucursales"]} == {access_scope.own.id, access_scope.ungranted.id}


def test_superadministrator_identity_does_not_bypass_company_membership(client, access_scope):
    headers = staff_login(client, access_scope.platform)
    assert client.get("/api/auth/me", headers=headers).json()["es_superadministrador"] is True
    assert client.get("/api/empresas", headers=headers).json() == []
    assert client.get("/api/auth/contexto", headers=headers).status_code == 403
    assert client.get("/api/auth/contexto", headers={**headers, "X-Empresa-Id": str(access_scope.company.id)}).status_code == 403


def test_context_requires_selection_when_ambiguous_and_rechecks_membership_grants(client, auth, access_scope, administrator, session_factory):
    with session_factory() as db:
        db.add(MembresiaEmpresa(administrador_id=administrator.id, empresa_id=access_scope.other.id, rol="CAJERO", activo=True))
        db.commit()
    assert client.get("/api/auth/contexto", headers=auth).status_code == 409
    second = {**auth, "X-Empresa-Id": str(access_scope.other.id)}
    assert client.get("/api/auth/contexto", headers=second).json()["empresa"]["rol"] == "CAJERO"
    with session_factory() as db:
        db.get(MembresiaEmpresa, (administrator.id, access_scope.other.id)).activo = False
        db.commit()
    assert client.get("/api/auth/contexto", headers=second).status_code == 403
    assert client.get("/api/auth/me", headers=auth).status_code == 200


@pytest.mark.parametrize("role", ["ENCARGADO_SUCURSAL", "CAJERO"])
def test_local_personnel_creation_uses_password_policy_argon2_and_explicit_branch_grants(monkeypatch, capsys, client, engine, session_factory, access_scope, role):
    password = "CuentaLocal!2026"
    email = f"nueva-{role.lower()}@vestinova.test"
    answers = iter(["Nueva cuenta personal", email])
    secrets = iter([password, password])
    monkeypatch.setattr(create_admin.Settings, "from_env", lambda: Settings("sqlite://", "configuracion-solo-prueba-aislada"))
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(create_admin, "getpass", lambda _: next(secrets))
    monkeypatch.setattr(create_admin, "build_engine", lambda _: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    create_admin.main(["--empresa-id", str(access_scope.company.id), "--rol", role, "--sucursal-id", str(access_scope.own.id)])
    assert password not in capsys.readouterr().out
    login = client.post("/api/auth/login", json={"correo": email, "password": password})
    assert login.status_code == 200
    assert login.json()["administrador"]["es_superadministrador"] is False
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    context = client.get("/api/auth/contexto", headers=headers).json()
    assert context["empresa"]["rol"] == role
    assert [branch["id"] for branch in context["sucursales"]] == [access_scope.own.id]
    with session_factory() as db:
        assert db.scalar(select(Administrador).where(Administrador.correo == email)).password_hash.startswith("$argon2id$")


def test_local_context_list_is_read_only_and_does_not_disclose_accounts_or_credentials(monkeypatch, capsys, engine, session_factory, access_scope):
    monkeypatch.setattr(list_access_contexts.Settings, "from_env", lambda: Settings("sqlite://", "no-imprimir-este-secreto"))
    monkeypatch.setattr(list_access_contexts, "build_engine", lambda _: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    list_access_contexts.main()
    output = capsys.readouterr().out
    assert f"Empresa ID {access_scope.company.id}" in output
    assert f"Sucursal ID {access_scope.own.id}" in output
    assert "no-imprimir-este-secreto" not in output and "@vestinova.test" not in output and "argon2" not in output
