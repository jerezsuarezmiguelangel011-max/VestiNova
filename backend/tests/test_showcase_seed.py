"""La vitrina visual no recrea datos de seguridad, operaciones ni saldos."""
from sqlalchemy import func, select

from app.models import (
    Cliente, Empresa, Existencia, MovimientoInventario, PlanSaaS,
    Producto, Promocion, Sucursal, VarianteProducto,
)
from scripts.seed_demo import seed_data
from scripts.seed_showcase_demo import SHOWCASE, add_showcase


def _counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in (
        Empresa, Sucursal, Cliente, Producto, VarianteProducto,
        Existencia, MovimientoInventario, Promocion,
    ))


def test_vitrina_opcional_preserva_usuarios_y_saldos_al_repetirse(session_factory):
    with session_factory() as db, db.begin():
        db.add(PlanSaaS(codigo="BASICO", nombre="Plan básico demo",
                        max_sucursales=2, prestaciones=[], activo=True))
        db.add(PlanSaaS(codigo="PROFESIONAL", nombre="Plan profesional demo",
                        max_sucursales=10, prestaciones=[], activo=True))
        db.flush()
        seed_data(db, "Pruebas2026!")
        original = _counts(db)
        first = add_showcase(db)
        after_first = _counts(db)
        second = add_showcase(db)
        after_second = _counts(db)

        assert after_first == after_second, "La ejecución repetida creó filas adicionales."
        assert first["demo-moda-andina"]["productos_nuevos"] == len(SHOWCASE["demo-moda-andina"])
        assert first["demo-moda-urbana"]["productos_nuevos"] == len(SHOWCASE["demo-moda-urbana"])
        assert second["demo-moda-andina"]["productos_nuevos"] == 0
        assert second["demo-moda-urbana"]["productos_nuevos"] == 0
        assert original[:3] == after_first[:3], "Una seed visual no debe alterar empresas, sucursales ni clientes."
        assert after_first[3] == 30, "Tres prendas originales y doce de vitrina por empresa."
        assert after_first[4] > original[4]
        assert after_first[5] > original[5]
        assert after_first[6] > original[6]
        assert after_first[7] == 8, "Dos promociones originales y seis ofertas visuales nuevas."
        assert db.scalar(select(func.count()).select_from(Producto).where(
            Producto.imagen_url.is_not(None))) == 30
        assert db.scalar(select(func.count()).select_from(Producto).where(
            Producto.imagen_url.like("http://127.0.0.1:4201/demo-fashion/%"))) == 30
        assert db.scalar(select(func.count()).select_from(Existencia).where(
            Existencia.cantidad < Existencia.cantidad_comprometida)) == 0


def test_vitrina_respetara_limites_de_plan_sin_mutaciones_parciales(session_factory):
    from pytest import raises
    with session_factory() as db, db.begin():
        db.add(PlanSaaS(codigo="BASICO", nombre="Plan básico demo",
                        max_sucursales=2, max_productos=6, prestaciones=[], activo=True))
        db.add(PlanSaaS(codigo="PROFESIONAL", nombre="Plan profesional demo",
                        max_sucursales=10, prestaciones=[], activo=True))
        db.flush()
        seed_data(db, "Pruebas2026!")
        original = _counts(db)
        with raises(ValueError, match="cupo de productos"):
            add_showcase(db)
        db.rollback()
        assert original[3] == 6
