"""El directorio público no expone empresas sin suscripción efectiva."""
from sqlalchemy import select

from app.models import Empresa, PlanSaaS, SuscripcionEmpresa
from scripts.seed_demo import seed_data


def test_directory_only_advertises_enabled_companies_with_active_plan(client, session_factory):
    with session_factory() as db, db.begin():
        db.add(PlanSaaS(codigo="BASICO", nombre="Básico demo", max_sucursales=2,
                        prestaciones=[], activo=True))
        db.add(PlanSaaS(codigo="PROFESIONAL", nombre="Profesional demo", max_sucursales=10,
                        prestaciones=[], activo=True))
        db.flush()
        seed_data(db, "Pruebas2026!")
        db.add(Empresa(slug="empresa-no-suscrita", nombre="Empresa no suscrita", activo=True))

    response = client.get("/api/catalogo/tiendas")
    assert response.status_code == 200
    assert {store["slug"] for store in response.json()} == {
        "demo-moda-andina", "demo-moda-urbana",
    }

    with session_factory() as db, db.begin():
        andina = db.scalar(select(Empresa).where(Empresa.slug == "demo-moda-andina"))
        subscription = db.get(SuscripcionEmpresa, andina.id)
        subscription.estado = "SUSPENDIDA"

    response = client.get("/api/catalogo/tiendas")
    assert [shop["slug"] for shop in response.json()] == ["demo-moda-urbana"]
