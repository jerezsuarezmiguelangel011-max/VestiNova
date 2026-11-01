"""Solo para scripts.test_postgres y su instancia temporal, jamás para la base operativa."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

from app.config import BACKEND_ROOT, Settings, validate_local_database_url
from app.db import build_session_factory
from app.main import create_app
from app.models import Administrador, Producto, SesionAdministrador
from app.inventory.domain import InventoryKey
from app.purchases.domain import Purchase, PurchaseCommand, PurchaseContext, PurchaseItem, PurchaseLine, identifier_token
from app.purchases.persistence import PurchaseLineRecord, PurchaseRecord, add_purchase, find_purchase
from app.security import hash_password


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
    password = "Clave aislada PostgreSQL!2026"
    with factory() as session:
        administrator = Administrador(nombre="Prueba aislada", correo=email, password_hash=hash_password(password), activo=True)
        session.add(administrator)
        session.commit()
    response = client.post("/api/auth/login", json={"correo": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_alembic_initialization_is_complete_and_repeatable(engine):
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version", "administradores", "sesiones_administrador", "productos",
        "compras_digitales", "compras_digitales_lineas",
    }
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_revision() == "cu10_01_compras"


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


def postgres_purchase():
    identifier = uuid4()
    context = PurchaseContext("actor-pg", f"empresa-{uuid4().hex}", "cliente-pg", "sucursal-pg")
    item = PurchaseItem(7, 2147483647)
    line = PurchaseLine(
        InventoryKey(context.empresa_id, context.sucursal_id, "variante-pg"),
        item.producto_id, "Snapshot de precio PostgreSQL", item.cantidad, Decimal("99999999.99"),
    )
    return Purchase(identifier, context, PurchaseCommand(identifier, (item,)).fingerprint, (line,), datetime.now(timezone.utc))


def test_purchase_snapshot_precision_and_context_persist_across_postgres_sessions(factory):
    original = postgres_purchase()
    with factory() as session:
        add_purchase(session, original)
        session.commit()
    with factory() as session:
        restored = find_purchase(session, original.context, original.id)
        assert restored == original
        assert restored.total == original.lines[0].precio_unitario * original.lines[0].cantidad
        assert session.get(PurchaseRecord, str(original.id)).total == original.total


def test_purchase_composite_foreign_key_and_rollback_are_enforced_in_postgres(factory):
    original = postgres_purchase()
    with factory() as session:
        add_purchase(session, original)
        session.commit()
    with factory() as session:
        session.add(PurchaseLineRecord(
            compra_id=str(original.id), posicion=1, empresa_clave=identifier_token("otra-empresa"),
            producto_id=9, variante_ref="otra-variante", nombre="Referencia cruzada", cantidad=1,
            precio_unitario=Decimal("10.00"),
        ))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    with factory() as session:
        assert find_purchase(session, original.context, original.id) == original


def test_purchase_rollback_does_not_persist_uncommitted_header_or_lines_in_postgres(factory):
    original = postgres_purchase()
    with factory() as session:
        add_purchase(session, original)
        session.flush()
        session.rollback()
    with factory() as session:
        assert find_purchase(session, original.context, original.id) is None
        assert session.scalar(select(PurchaseLineRecord).where(PurchaseLineRecord.compra_id == str(original.id))) is None
