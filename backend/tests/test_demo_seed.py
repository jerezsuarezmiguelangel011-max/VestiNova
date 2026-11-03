"""Comprobaciones del entorno demo sin conectarse a PostgreSQL real."""
import pytest
from sqlalchemy import func, select

from app.config import validate_demo_database_url
from app.models import (
    Administrador, Cliente, Empresa, Existencia, MovimientoInventario,
    OrdenAbastecimiento, PlanSaaS, Producto, Promocion, Sucursal,
    SuscripcionEmpresa,
)
from scripts.seed_demo import seed_data


def test_demo_url_is_strictly_local_and_separate():
    validate_demo_database_url("postgresql+psycopg://local:secret@127.0.0.1:5432/vestinova_pruebas")
    for url in (
        "postgresql+psycopg://local:secret@127.0.0.1:5432/vestinova_mvp",
        "postgresql+psycopg://local:secret@external.example/vestinova_pruebas",
        "postgresql+psycopg://local:secret@localhost/vestinova_pruebas?host=external.example",
        "sqlite:///vestinova_pruebas",
    ):
        with pytest.raises(ValueError):
            validate_demo_database_url(url)


def _counts(db):
    models = (
        Empresa, Sucursal, Administrador, Cliente, Producto, Existencia,
        MovimientoInventario, OrdenAbastecimiento, Promocion, SuscripcionEmpresa,
    )
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in models)


def test_demo_seed_is_idempotent_and_isolates_tenants(session_factory):
    with session_factory() as db, db.begin():
        for code, limit in (("BASICO", 2), ("PROFESIONAL", 10)):
            db.add(PlanSaaS(codigo=code, nombre=code, max_sucursales=limit,
                            prestaciones=[], activo=True))
        db.flush()
        summary_first = seed_data(db, "Pruebas2026!")
        before = _counts(db)
        summary_second = seed_data(db, "Pruebas2026!")
        after = _counts(db)

        assert summary_first == summary_second
        assert before == after
        assert len(summary_first) == 2
        assert before[0] == 2
        assert before[1] == 5
        assert before[2] == 7
        assert before[3] == 2
        assert before[4] == 6
        assert before[5] == 15
        assert before[7] == 2
        assert before[8] == 2
        companies = db.scalars(select(Empresa)).all()
        for company in companies:
            assert db.scalar(select(func.count()).select_from(Producto).where(
                Producto.empresa_id == company.id)) == 3
        assert db.scalar(select(func.count()).select_from(Existencia).where(
            Existencia.cantidad == 0)) == 5
