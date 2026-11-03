from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, build_session_factory
from app.main import create_app
from app.models import Administrador, Empresa, MembresiaEmpresa, PlanSaaS, SuscripcionEmpresa
from app.security import hash_password


TEST_PASSWORD = " Clave de prueba local 2026 "
TEST_SECRET = "solo-pruebas-aisladas-no-usar-para-la-api-real-123456"


def activate_test_subscription(db, empresa_id: int) -> None:
    """Asigna un plan de prueba activo respetando las reglas SaaS reales."""
    plan = db.scalar(select(PlanSaaS).where(PlanSaaS.codigo == "BASICO"))
    if plan is None:
        plan = PlanSaaS(codigo="BASICO", nombre="Básico de pruebas",
                        descripcion="Plan aislado para pruebas automatizadas",
                        max_sucursales=1000, max_productos=1000, max_usuarios=1000,
                        activo=True)
        db.add(plan)
        db.flush()
    db.add(SuscripcionEmpresa(empresa_id=empresa_id, plan_id=plan.id,
                              estado="ACTIVA", inicia_en=datetime.now(timezone.utc) - timedelta(days=1)))


@pytest.fixture
def engine():
    database_engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(database_engine, "connect")
    def enforce_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    # create_all es solo para estas pruebas unitarias; la instalación usa Alembic.
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture
def session_factory(engine):
    return build_session_factory(engine)


@pytest.fixture
def administrator(session_factory):
    with session_factory() as db:
        administrator = Administrador(nombre="Administrador de prueba", correo="admin@vestinova.test", password_hash=hash_password(TEST_PASSWORD), activo=True)
        db.add(administrator)
        empresa = Empresa(slug="empresa-prueba", nombre="Empresa de prueba", activo=True)
        db.add(empresa)
        db.flush()
        activate_test_subscription(db, empresa.id)
        db.add(MembresiaEmpresa(administrador_id=administrator.id, empresa_id=empresa.id, rol="ADMINISTRADOR", activo=True))
        db.commit()
        return administrator


@pytest.fixture
def app(engine):
    return create_app(Settings(database_url="sqlite://", jwt_secret=TEST_SECRET), engine=engine)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def credentials(client, administrator):
    response = client.post("/api/auth/login", json={"correo": administrator.correo, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def auth(credentials):
    return {"Authorization": f"Bearer {credentials['access_token']}"}
