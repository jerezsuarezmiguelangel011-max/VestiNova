"""Verifica escenario de prueba CU19/20/23 sin tocar PostgreSQL real."""
from sqlalchemy import func, select

from app.models import (
    AccesoSucursal, Administrador, Cliente, Empresa, Existencia,
    MembresiaEmpresa, Sucursal,
)
from app.catalogo_publico.historial_recomendaciones import ConsentimientoCU19, VistaCU19
from app.compras_reservas.deseos import Deseo
from app.operacion_sin_conexion.caja.online import CashSale
from scripts.seed_demo_cu19_cu20_cu23 import seed_scenarios
from tests.test_seed_fashion_catalog_demo import _prepare_demo_companies


def test_escenarios_demo_son_repetibles_y_tienen_ventas_reales_de_prueba(session_factory):
    with session_factory.begin() as db:
        _prepare_demo_companies(db)
        company = db.scalar(select(Empresa).where(Empresa.slug == "demo-moda-andina"))
        centro = db.scalar(select(Sucursal).where(
            Sucursal.empresa_id == company.id, Sucursal.codigo == "CENTRO",
        ))
        client = Cliente(
            empresa_id=company.id, nombre="Cliente Demo Andina",
            correo="cliente.andina@vestinova.test",
            password_hash="test-no-login", activo=True,
        )
        cashier = Administrador(
            nombre="Cajero Demo Andina", correo="cajero.andina@vestinova.test",
            password_hash="test-no-login", activo=True,
        )
        db.add_all([client, cashier])
        db.flush()
        db.add(MembresiaEmpresa(
            administrador_id=cashier.id, empresa_id=company.id,
            rol="CAJERO", activo=True,
        ))
        db.flush()
        db.add(AccesoSucursal(
            administrador_id=cashier.id, empresa_id=company.id,
            sucursal_id=centro.id,
        ))
        db.flush()

        first = seed_scenarios(db)
        db.flush()
        assert first["cliente"] == "cliente.andina@vestinova.test"
        assert len(first["vistas"]) == 3
        assert first["deseos_nuevos"] == 2
        assert len(first["ventas_nuevas"]) == 3
        assert db.get(ConsentimientoCU19, (company.id, client.id)).habilitado
        assert db.scalar(select(func.count()).select_from(VistaCU19)) == 3
        assert db.scalar(select(func.count()).select_from(Deseo)) == 2
        assert db.scalar(select(func.count()).select_from(CashSale)) == 3

        balances = {row.variante_id: row.cantidad for row in db.scalars(
            select(Existencia).where(
                Existencia.empresa_id == company.id,
                Existencia.sucursal_id == centro.id,
            )
        ).all()}

        second = seed_scenarios(db)
        db.flush()
        assert second["deseos_nuevos"] == 0
        assert second["ventas_nuevas"] == []
        assert db.scalar(select(func.count()).select_from(CashSale)) == 3
        assert db.scalar(select(func.count()).select_from(Deseo)) == 2
        current = {row.variante_id: row.cantidad for row in db.scalars(
            select(Existencia).where(
                Existencia.empresa_id == company.id,
                Existencia.sucursal_id == centro.id,
            )
        ).all()}
        assert current == balances
