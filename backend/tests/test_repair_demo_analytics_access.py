"""Regresión: permisos de analítica para roles del sistema, sin alterar roles personalizados."""
from sqlalchemy import create_engine, text

from scripts.repair_demo_analytics_access import repair_grants


def test_repair_only_adds_expected_demo_permissions_and_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE empresas (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL)"))
        db.execute(text("CREATE TABLE roles_empresa (id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL, codigo_sistema TEXT)"))
        db.execute(text("CREATE TABLE permisos_rol (rol_empresa_id INTEGER NOT NULL, codigo TEXT NOT NULL, PRIMARY KEY(rol_empresa_id, codigo))"))
        db.execute(text("INSERT INTO empresas (id, slug) VALUES (1, 'demo-moda-andina'), (2, 'demo-moda-urbana'), (3, 'empresa-ajena')"))
        db.execute(text("""INSERT INTO roles_empresa (id, empresa_id, codigo_sistema) VALUES
            (1, 1, 'ADMINISTRADOR'), (2, 1, 'ENCARGADO_SUCURSAL'),
            (3, 2, 'ADMINISTRADOR'), (4, 2, 'ENCARGADO_SUCURSAL'),
            (5, 2, NULL), (6, 3, 'ADMINISTRADOR')"""))
        db.execute(text("INSERT INTO permisos_rol (rol_empresa_id, codigo) VALUES (3, 'reportes.ia.consultar'), (5, 'catalogo.consultar'), (6, 'catalogo.consultar')"))
        first = repair_grants(db)
        assert [(slug, role) for slug, role, _ in first] == [
            ('demo-moda-andina', 'ADMINISTRADOR'), ('demo-moda-andina', 'ENCARGADO_SUCURSAL'),
            ('demo-moda-urbana', 'ADMINISTRADOR'), ('demo-moda-urbana', 'ENCARGADO_SUCURSAL'),
        ]
        assert repair_grants(db) == [(slug, role, 0) for slug, role, _ in first]
        for role_id in (1, 3):
            permissions = set(db.scalars(text("SELECT codigo FROM permisos_rol WHERE rol_empresa_id = :id"), {"id": role_id}))
            assert {"sucursales.consultar", "reportes.ia.consultar", "analitica.consultar"} <= permissions
        for role_id in (2, 4):
            permissions = set(db.scalars(text("SELECT codigo FROM permisos_rol WHERE rol_empresa_id = :id"), {"id": role_id}))
            assert "reportes.ia.consultar" in permissions
            assert "analitica.consultar" not in permissions
        assert list(db.scalars(text("SELECT codigo FROM permisos_rol WHERE rol_empresa_id = 5"))) == ['catalogo.consultar']
        assert list(db.scalars(text("SELECT codigo FROM permisos_rol WHERE rol_empresa_id = 6"))) == ['catalogo.consultar']
    engine.dispose()
