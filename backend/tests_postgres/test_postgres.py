"""Solo para scripts.test_postgres y su instancia temporal, jamás para la base operativa."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import socket
from threading import Barrier, Thread
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.config import BACKEND_ROOT, Settings, validate_local_database_url
from app.db import Base, build_session_factory
from app.main import create_app
from app.mobile_download import download_db
from app.models import AccesoSucursal, Administrador, Cliente, Empresa, Existencia, MembresiaEmpresa, MovimientoInventario, Producto, SesionAdministrador, SesionCliente, Sucursal, VarianteProducto, utc_now
from app.security import hash_password


LEGACY = {}
PG_PASSWORD = "Clave aislada PostgreSQL!2026"


@pytest.fixture(scope="module")
def engine():
    if os.environ.get("MVP_ISOLATED_POSTGRES") != "1":
        pytest.skip("Ejecutar mediante python -m scripts.test_postgres, con PostgreSQL aislado.")
    database_url = os.environ.get("DATABASE_URL", "")
    validate_local_database_url(database_url)
    if make_url(database_url).port in {None, 5432}:
        pytest.fail("La prueba exige un puerto temporal diferente de 5432.")
    database_engine = create_engine(database_url)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    with database_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_base")
        # Datos previos reales de prueba: usar SQL del esquema viejo, sin modelos nuevos.
        legacy_hash = hash_password(PG_PASSWORD)
        administrator_id = connection.scalar(text("INSERT INTO administradores(nombre, correo, password_hash) VALUES (:n, :c, :h) RETURNING id"),
                                               {"n": "Administrador previo", "c": "anterior@vestinova.test", "h": legacy_hash})
        product_id = connection.scalar(text("INSERT INTO productos(slug,nombre,precio) VALUES (:s,:n,:p) RETURNING id"),
                                       {"s": "producto-anterior", "n": "Producto previo", "p": "89.70"})
        session_id = str(uuid4())
        connection.execute(text("INSERT INTO sesiones_administrador(id,administrador_id,expira_en) VALUES (:s,:a,:e)"),
                           {"s": session_id, "a": administrator_id, "e": utc_now() + timedelta(hours=1)})
        LEGACY.update(administrador_id=administrator_id, product_id=product_id,
                      session_id=session_id, password_hash=legacy_hash)
        command.upgrade(config, "head")
    yield database_engine
    database_engine.dispose()


@pytest.fixture
def factory(engine):
    return build_session_factory(engine)


@pytest.fixture
def client(engine):
    settings = Settings(database_url=os.environ["DATABASE_URL"], jwt_secret=os.environ.get("JWT_SECRET", "solo-test-postgres-aislado-nunca-servidor-real-1234"))
    # Cada cliente usa el mismo motor, las consultas abren sesiones independientes.
    with TestClient(create_app(settings, engine=engine)) as test_client:
        yield test_client


def administrator_credentials(client, factory):
    email = f"admin-{uuid4().hex}@vestinova.test"
    with factory() as session:
        administrator = Administrador(nombre="Prueba aislada", correo=email, password_hash=hash_password(PG_PASSWORD), activo=True)
        company = Empresa(slug=f"empresa-{uuid4().hex}", nombre="Empresa aislada", activo=True)
        session.add(administrator)
        session.add(company)
        session.flush()
        session.add(MembresiaEmpresa(administrador_id=administrator.id, empresa_id=company.id, rol="ADMINISTRADOR", activo=True))
        session.commit()
    response = client.post("/api/auth/login", json={"correo": email, "password": PG_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_alembic_initialization_is_complete_and_repeatable(engine):
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_revision() == "0003_cuentas_clientes"


def test_upgrade_preserves_accounts_hashes_products_and_live_sessions(factory):
    with factory() as db:
        administrator = db.get(Administrador, LEGACY["administrador_id"])
        product = db.get(Producto, LEGACY["product_id"])
        session = db.get(SesionAdministrador, LEGACY["session_id"])
        assert administrator.correo == "anterior@vestinova.test"
        assert administrator.password_hash == LEGACY["password_hash"]
        assert administrator.es_superadministrador is True
        assert str(product.precio) == "89.70" and product.slug == "producto-anterior"
        assert session.administrador_id == administrator.id and session.revocada is False
        company = db.get(Empresa, product.empresa_id)
        assert company.slug == "vestinova-inicial"
        membership = db.get(MembresiaEmpresa, (administrator.id, company.id))
        assert membership.rol == "ADMINISTRADOR" and membership.activo is True
        assert db.scalar(select(VarianteProducto.id).where(VarianteProducto.producto_id == product.id)) is None
        assert db.scalar(select(func.count()).select_from(Existencia)) == 0


def test_logout_revokes_persisted_session(client, factory):
    headers = administrator_credentials(client, factory)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/admin/productos", headers=headers).status_code == 401
    with factory() as independent:
        assert independent.scalar(select(SesionAdministrador.id).where(SesionAdministrador.revocada.is_(True))) is not None


def test_products_persist_between_requests_and_sessions(client, factory):
    headers = administrator_credentials(client, factory)
    slug = f"prueba-{uuid4().hex}"
    created = client.post("/api/admin/productos", headers=headers, json={"nombre": "Prueba de persistencia", "slug": slug, "precio": "45.90"})
    assert created.status_code == 201
    product_id = created.json()["id"]
    with factory() as independent:
        stored = independent.get(Producto, product_id)
        assert str(stored.precio) == "45.90"
        assert stored.moneda == "BOB"
    changed = client.patch(f"/api/admin/productos/{product_id}", headers=headers, json={"precio": "55.50", "activo": False})
    assert changed.status_code == 200
    with factory() as another:
        assert str(another.get(Producto, product_id).precio) == "55.50"
    assert client.get(f"/api/catalogo/productos/{slug}").status_code == 404
    assert client.get(f"/api/admin/productos/{product_id}", headers=headers).json()["activo"] is False


def prepare_inventory(client, factory):
    headers = administrator_credentials(client, factory)
    company_id = client.get("/api/empresas", headers=headers).json()[0]["id"]
    branch = client.post("/api/admin/sucursales", headers=headers,
                         json={"codigo": "PRINCIPAL", "nombre": "Sucursal de prueba"})
    assert branch.status_code == 201, branch.text
    product = client.post("/api/admin/productos", headers=headers,
                          json={"nombre": "Prenda de concurrencia", "slug": f"prenda-{uuid4().hex}", "precio": "20.90"})
    assert product.status_code == 201, product.text
    variant = client.post(f"/api/admin/productos/{product.json()['id']}/variantes", headers=headers,
                          json={"talla": "M", "color": "AZUL"})
    assert variant.status_code == 201, variant.text
    return headers, company_id, branch.json()["id"], variant.json()["id"]


def concurrent_movements(engine, headers, payloads):
    barrier = Barrier(len(payloads))
    settings = Settings(database_url=os.environ["DATABASE_URL"], jwt_secret=os.environ["JWT_SECRET"])

    def send(payload):
        # Cada worker mantiene su propio cliente y su propia sesión/transacción SQL.
        with TestClient(create_app(settings, engine=engine)) as independent:
            barrier.wait(timeout=15)
            response = independent.post("/api/admin/inventario/movimientos", headers=headers, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        return list(executor.map(send, payloads))


def test_concurrent_withdrawals_cannot_overdraw_and_ledger_matches_balance(engine, client, factory):
    headers, company, branch, variant = prepare_inventory(client, factory)
    base = {"sucursal_id": branch, "variante_id": variant, "motivo": "Conteo físico aislado"}
    initial = client.post("/api/admin/inventario/movimientos", headers=headers,
                          json={**base, "id": str(uuid4()), "tipo": "ENTRADA", "cantidad": 5})
    assert initial.status_code == 201, initial.text
    operations = [{**base, "id": str(uuid4()), "tipo": "SALIDA", "cantidad": 4} for _ in range(2)]
    results = concurrent_movements(engine, headers, operations)
    assert sorted(code for code, _ in results) == [201, 409], results
    with factory() as db:
        assert db.get(Existencia, (company, branch, variant)).cantidad == 1
        ledger = db.scalars(select(MovimientoInventario).where(MovimientoInventario.variante_id == variant)).all()
        assert len(ledger) == 2 and sum(row.delta for row in ledger) == 1


def test_concurrent_same_operation_id_creates_one_movement_and_one_balance(engine, client, factory):
    headers, company, branch, variant = prepare_inventory(client, factory)
    operation = {"id": str(uuid4()), "sucursal_id": branch, "variante_id": variant,
                 "tipo": "ENTRADA", "cantidad": 9, "motivo": "Entrada única con reintento"}
    results = concurrent_movements(engine, headers, [operation, operation])
    assert sorted(code for code, _ in results) == [200, 201], results
    assert results[0][1] == results[1][1]
    with factory() as db:
        assert db.get(Existencia, (company, branch, variant)).cantidad == 9
        assert db.scalar(select(func.count()).select_from(MovimientoInventario).where(MovimientoInventario.id == operation["id"])) == 1


def test_postgres_composite_foreign_key_refuses_cross_tenant_variant(client, factory):
    first_headers, first_company, _, _ = prepare_inventory(client, factory)
    other_headers, other_company, _, _ = prepare_inventory(client, factory)
    foreign_product = client.get("/api/admin/productos", headers=other_headers).json()["items"][0]
    with factory() as db:
        invalid = VarianteProducto(empresa_id=first_company, producto_id=foreign_product["id"], talla="XL", color="NEGRO")
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    assert client.get(f"/api/admin/productos/{foreign_product['id']}", headers=first_headers).status_code == 404


def test_private_download_in_postgres_enforces_company_and_branch_grants(client, factory):
    headers, company, branch, variant = prepare_inventory(client, factory)
    other_headers, _, other_branch, _ = prepare_inventory(client, factory)
    second_branch = client.post("/api/admin/sucursales", headers=headers,
                                json={"codigo": "SEGUNDA", "nombre": "Otra sucursal propia"}).json()["id"]
    owner_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with factory() as db:
        owner = db.get(Administrador, owner_id)
        operator = Administrador(nombre="Operador PostgreSQL", correo=f"operador-{uuid4().hex}@vestinova.test",
                                 password_hash=owner.password_hash, activo=True)
        db.add(operator)
        db.flush()
        db.add(MembresiaEmpresa(administrador_id=operator.id, empresa_id=company, rol="OPERADOR", activo=True))
        db.flush()
        db.add(AccesoSucursal(administrador_id=operator.id, empresa_id=company, sucursal_id=branch))
        db.commit()
        email = operator.correo
    login = client.post("/api/auth/login", json={"correo": email, "password": PG_PASSWORD})
    assert login.status_code == 200
    operator_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    entry = client.post("/api/admin/inventario/movimientos", headers=headers,
                        json={"id": str(uuid4()), "sucursal_id": branch, "variante_id": variant,
                              "tipo": "ENTRADA", "cantidad": 3, "motivo": "Entrada para descarga autorizada"})
    assert entry.status_code == 201, entry.text
    response = client.get("/api/movil/descarga", headers=operator_headers)
    assert response.status_code == 200, response.text
    download = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert download["empresa"]["id"] == company
    assert [item["id"] for item in download["sucursales"]] == [branch]
    assert download["productos"][0]["precio"] == "20.90"
    assert download["productos"][0]["moneda"] == "BOB"
    assert download["productos"][0]["variantes"][0]["id"] == variant
    known = download["productos"][0]["variantes"][0]["existencias"][0]
    assert known["cantidad"] == 3 and known["registrada"] is True
    assert known["actualizado_en"].endswith("+00:00")
    assert download["generado_en"].endswith("+00:00")
    for denied in [second_branch, other_branch]:
        assert client.get(f"/api/movil/descarga?sucursal_ids={denied}", headers=operator_headers).status_code == 404
    foreign_product = client.get("/api/admin/productos", headers=other_headers).json()["items"][0]["id"]
    assert client.get(f"/api/movil/descarga?producto_ids={foreign_product}", headers=headers).status_code == 404
    with factory() as db:
        db.get(MembresiaEmpresa, (operator.id, company)).activo = False
        db.commit()
    assert client.get("/api/movil/descarga", headers=operator_headers).status_code == 403


def test_download_connection_is_read_only_repeatable_read_and_does_not_change_pool_defaults(engine):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(engine=engine)))
    dependency = download_db(request)
    session = next(dependency)
    try:
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
    finally:
        dependency.close()
    with engine.connect() as ordinary:
        assert ordinary.scalar(text("SHOW transaction_read_only")) == "off"
        assert ordinary.scalar(text("SHOW transaction_isolation")) == "read committed"


def test_variant_correction_persists_and_keeps_history_identity_in_postgres(client, factory):
    headers, company, branch, variant = prepare_inventory(client, factory)
    before = client.get("/api/admin/productos", headers=headers).json()["items"][0]
    original = client.get(f"/api/admin/productos/{before['id']}/variantes", headers=headers).json()[0]
    changed = client.patch(f"/api/admin/variantes/{variant}", headers=headers,
                           json={"talla": " l ", "color": " verde ", "activo": False})
    assert changed.status_code == 200, changed.text
    assert changed.json() == {**original, "talla": "L", "color": "VERDE", "activo": False}
    with factory() as independent:
        stored = independent.get(VarianteProducto, variant)
        assert (stored.empresa_id, stored.producto_id, stored.talla, stored.color) == (company, before["id"], "L", "VERDE")
        assert stored.activo is False
    assert client.patch(f"/api/admin/variantes/{variant}", headers=headers, json={"activo": True}).status_code == 200
    entry = client.post("/api/admin/inventario/movimientos", headers=headers,
                        json={"id": str(uuid4()), "sucursal_id": branch, "variante_id": variant,
                              "tipo": "ENTRADA", "cantidad": 1, "motivo": "Fixture de identidad histórica"})
    assert entry.status_code == 201, entry.text
    blocked = client.patch(f"/api/admin/variantes/{variant}", headers=headers, json={"color": "ROJO"})
    assert blocked.status_code == 409 and "movimientos registrados" in blocked.json()["detail"]
    state_only = client.patch(f"/api/admin/variantes/{variant}", headers=headers, json={"activo": False})
    assert state_only.status_code == 200
    with factory() as independent:
        assert independent.get(VarianteProducto, variant).color == "VERDE"
        assert independent.get(Existencia, (company, branch, variant)).cantidad == 1
        assert independent.scalar(select(func.count()).select_from(MovimientoInventario).where(MovimientoInventario.variante_id == variant)) == 1
    assert client.get(f"/api/catalogo/productos/{before['slug']}").json() == before


def test_duplicate_variant_correction_rolls_back_all_fields_in_postgres(client, factory):
    headers, company, _, first_id = prepare_inventory(client, factory)
    garment = client.get("/api/admin/productos", headers=headers).json()["items"][0]
    second = client.post(f"/api/admin/productos/{garment['id']}/variantes", headers=headers,
                         json={"talla": "L", "color": "VERDE"})
    assert second.status_code == 201
    second_id = second.json()["id"]
    duplicate = client.patch(f"/api/admin/variantes/{second_id}", headers=headers,
                             json={"talla": " m ", "color": " azul ", "activo": False})
    assert duplicate.status_code == 409
    with factory() as independent:
        assert independent.get(VarianteProducto, second_id).talla == "L"
        assert independent.get(VarianteProducto, second_id).color == "VERDE"
        assert independent.get(VarianteProducto, second_id).activo is True
        assert independent.scalar(select(func.count()).select_from(VarianteProducto).where(VarianteProducto.empresa_id == company)) == 2
    assert client.patch(f"/api/admin/variantes/{first_id}", headers=headers, json={"color": " NEGRO "}).status_code == 200


def test_customer_email_unique_constraint_is_per_company_and_sessions_persist(client, factory):
    slug_a, slug_b = f"tienda-{uuid4().hex}", f"tienda-{uuid4().hex}"
    with factory() as db:
        first, second = Empresa(slug=slug_a, nombre="Tienda A", activo=True), Empresa(slug=slug_b, nombre="Tienda B", activo=True)
        db.add_all([first, second])
        db.commit()
        first_id = first.id
    payload = {"nombre": "Cliente PostgreSQL", "correo": f"cliente-{uuid4().hex}@vestinova.test", "password": PG_PASSWORD}
    initial = client.post(f"/api/tiendas/{slug_a}/cuenta/registro", json=payload)
    independent = client.post(f"/api/tiendas/{slug_b}/cuenta/registro", json=payload)
    assert initial.status_code == independent.status_code == 201
    assert client.post(f"/api/tiendas/{slug_a}/cuenta/registro", json={**payload, "correo": payload["correo"].upper()}).status_code == 409
    with factory() as db:
        stored = db.get(Cliente, initial.json()["cliente"]["id"])
        assert stored.empresa_id == first_id and stored.password_hash.startswith("$argon2id$")
        assert db.scalar(select(SesionCliente.id).where(SesionCliente.cliente_id == stored.id)) is not None
        # La restricción existe en PostgreSQL, además de la normalización HTTP.
        db.add(Cliente(empresa_id=first_id, nombre="Duplicado directo", correo=payload["correo"], password_hash=stored.password_hash, activo=True))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    headers = {"Authorization": f"Bearer {initial.json()['access_token']}"}
    assert client.get(f"/api/tiendas/{slug_a}/cuenta/me", headers=headers).status_code == 200
    assert client.post(f"/api/tiendas/{slug_a}/cuenta/logout", headers=headers).status_code == 204
    with factory() as db:
        assert db.scalar(select(SesionCliente).where(SesionCliente.cliente_id == initial.json()["cliente"]["id"])).revocada is True


def test_concurrent_customer_registration_commits_one_account_and_session(engine, factory):
    slug = f"tienda-{uuid4().hex}"
    with factory() as db:
        company = Empresa(slug=slug, nombre="Tienda registro concurrente", activo=True)
        db.add(company)
        db.commit()
        company_id = company.id
    barrier = Barrier(2)
    payload = {"nombre": "Cliente concurrente", "correo": f"cliente-{uuid4().hex}@vestinova.test", "password": PG_PASSWORD}
    settings = Settings(database_url=os.environ["DATABASE_URL"], jwt_secret=os.environ["JWT_SECRET"])
    def send(_):
        with TestClient(create_app(settings, engine=engine)) as requester:
            barrier.wait(timeout=15)
            return requester.post(f"/api/tiendas/{slug}/cuenta/registro", json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, range(2))) == [201, 409]
    with factory() as db:
        customers = db.scalars(select(Cliente).where(Cliente.empresa_id == company_id)).all()
        assert len(customers) == 1
        assert db.scalar(select(func.count()).select_from(SesionCliente).where(SesionCliente.cliente_id == customers[0].id)) == 1


def test_cu01_http_real_staff_roles_and_customer_two_stores(engine, factory):
    """Uvicorn + HTTP real + PostgreSQL aislado; no son respuestas simuladas."""
    import uvicorn
    slug_a, slug_b = f"http-{uuid4().hex}", f"http-{uuid4().hex}"
    emails = {role: f"{role.lower()}-{uuid4().hex}@vestinova.test" for role in ["ADMINISTRADOR", "ENCARGADO_SUCURSAL", "CAJERO", "PLATAFORMA"]}
    encoded = hash_password(PG_PASSWORD)
    with factory() as db:
        first = Empresa(slug=slug_a, nombre="Tienda HTTP A", activo=True)
        second = Empresa(slug=slug_b, nombre="Tienda HTTP B", activo=True)
        db.add_all([first, second])
        db.flush()
        own = Sucursal(empresa_id=first.id, codigo="CENTRO", nombre="Sucursal HTTP Centro", activo=True)
        other = Sucursal(empresa_id=first.id, codigo="NORTE", nombre="Sucursal HTTP Norte", activo=True)
        db.add_all([own, other])
        db.flush()
        for role, email in emails.items():
            account = Administrador(nombre=f"Cuenta HTTP {role}", correo=email, password_hash=encoded, activo=True, es_superadministrador=role == "PLATAFORMA")
            db.add(account)
            db.flush()
            if role != "PLATAFORMA":
                db.add(MembresiaEmpresa(administrador_id=account.id, empresa_id=first.id, rol=role, activo=True))
                db.flush()
                if role != "ADMINISTRADOR":
                    db.add(AccesoSucursal(administrador_id=account.id, empresa_id=first.id, sucursal_id=own.id))
        db.commit()
        company_id, own_id, other_id = first.id, own.id, other.id

    settings = Settings(database_url=os.environ["DATABASE_URL"], jwt_secret=os.environ["JWT_SECRET"])
    server = uvicorn.Server(uvicorn.Config(create_app(settings, engine=engine), log_level="error", access_log=False))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = monotonic() + 10
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(.01)
        assert server.started, "Uvicorn aislado no inició."
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
            assert http.get("/api/health/db").status_code == 200
            for role, email in emails.items():
                signed_in = http.post("/api/auth/login", json={"correo": email, "password": PG_PASSWORD})
                assert signed_in.status_code == 200
                headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}", "X-Empresa-Id": str(company_id)}
                assert http.get("/api/auth/me", headers=headers).json()["es_superadministrador"] is (role == "PLATAFORMA")
                if role == "PLATAFORMA":
                    assert http.get("/api/empresas", headers=headers).json() == []
                    assert http.get("/api/auth/contexto", headers=headers).status_code == 403
                else:
                    context = http.get("/api/auth/contexto", headers=headers)
                    assert context.status_code == 200
                    assert context.json()["empresa"]["rol"] == role
                    assert {branch["id"] for branch in context.json()["sucursales"]} == ({own_id, other_id} if role == "ADMINISTRADOR" else {own_id})
                    write = http.post("/api/admin/productos", headers=headers, json={"nombre": "Prenda HTTP aislada", "precio": "49.90"})
                    assert write.status_code == (201 if role == "ADMINISTRADOR" else 403)
                assert http.post("/api/auth/logout", headers=headers).status_code == 204
                assert http.get("/api/auth/me", headers=headers).status_code == 401
            payload = {"nombre": "Cliente HTTP", "correo": f"http-{uuid4().hex}@vestinova.test", "password": PG_PASSWORD}
            assert http.get(f"/api/tiendas/{slug_a}").json() == {"slug": slug_a, "nombre": "Tienda HTTP A"}
            assert http.post(f"/api/tiendas/{slug_a}/cuenta/registro", json={**payload, "rol": "ADMINISTRADOR"}).status_code == 422
            registered = http.post(f"/api/tiendas/{slug_a}/cuenta/registro", json=payload)
            assert registered.status_code == 201 and registered.json()["cliente"]["rol"] == "CLIENTE"
            other_account = http.post(f"/api/tiendas/{slug_b}/cuenta/registro", json=payload)
            assert other_account.status_code == 201
            assert http.post(f"/api/tiendas/{slug_a}/cuenta/registro", json=payload).status_code == 409
            customer_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
            assert http.get(f"/api/tiendas/{slug_a}/cuenta/me", headers=customer_headers).json() == registered.json()["cliente"]
            assert http.get(f"/api/tiendas/{slug_b}/cuenta/me", headers=customer_headers).status_code == 401
            assert http.get("/api/admin/productos", headers=customer_headers).status_code == 401
            assert http.get("/api/auth/me", headers=customer_headers).status_code == 401
            assert http.post(f"/api/tiendas/{slug_a}/cuenta/logout", headers=customer_headers).status_code == 204
            assert http.get(f"/api/tiendas/{slug_a}/cuenta/me", headers=customer_headers).status_code == 401
            reopened = http.post(f"/api/tiendas/{slug_a}/cuenta/login", json={"correo": payload["correo"], "password": payload["password"]})
            assert reopened.status_code == 200
            assert http.get(f"/api/tiendas/{slug_a}/cuenta/me", headers={"Authorization": f"Bearer {reopened.json()['access_token']}"}).status_code == 200
            assert http.post(f"/api/tiendas/{slug_a}/cuenta/logout", headers={"Authorization": f"Bearer {reopened.json()['access_token']}"}).status_code == 204
            assert http.post(f"/api/tiendas/{slug_b}/cuenta/logout", headers={"Authorization": f"Bearer {other_account.json()['access_token']}"}).status_code == 204
            if os.environ.get('MVP_MOBILE_HTTP_CHECK') == '1':
                # Dart ejecuta HTTP real desde el host. El almacenamiento seguro
                # se sustituye por memoria; no acredita Android/iOS ni UI real.
                from pathlib import Path
                import subprocess
                flutter = os.environ['MVP_FLUTTER_BIN']
                invocation = [flutter, 'test', 'test/real_api_test.dart',
                              '--dart-define=REAL_API_TEST=true',
                              f'--dart-define=API_BASE_URL=http://127.0.0.1:{port}/api',
                              f'--dart-define=REAL_STORE_A={slug_a}', f'--dart-define=REAL_STORE_B={slug_b}',
                              f'--dart-define=REAL_STAFF_EMAIL={emails["ADMINISTRADOR"]}',
                              f'--dart-define=REAL_STAFF_PASSWORD={PG_PASSWORD}']
                if os.name == 'nt' and flutter.lower().endswith('.bat'):
                    invocation = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', *invocation]
                result = subprocess.run(invocation, cwd=Path(BACKEND_ROOT).parent / 'mobile',
                                        capture_output=True, text=True, encoding='utf-8',
                                        timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                (Path(BACKEND_ROOT) / '.runtime' / 'cu01-mobile-http.log').write_text(result.stdout + result.stderr, encoding='utf-8')
                assert result.returncode == 0, 'Falló Flutter HTTP real aislado:\n' + result.stdout + result.stderr
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "Revisa la parada del servidor HTTP aislado."
