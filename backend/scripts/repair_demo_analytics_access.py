"""Restaura únicamente permisos CU21/CU22 de roles del sistema en la BD DEMO.

No modifica cuentas, contraseñas, planes, roles personalizados ni vestinova_mvp.
Es seguro reejecutarlo. Requiere migraciones Alembic ya aplicadas.
"""
from sqlalchemy import text

from app.config import Settings
from app.db import build_engine
from scripts.demo_environment import use_demo_database

DEMO_SLUGS = ("demo-moda-andina", "demo-moda-urbana")
GRANTS = {
    "ADMINISTRADOR": ("sucursales.consultar", "reportes.ia.consultar", "analitica.consultar"),
    "ENCARGADO_SUCURSAL": ("sucursales.consultar", "reportes.ia.consultar"),
}


def repair_grants(connection):
    """Conserva permisos existentes y agrega solo los autorizados a perfiles DEMO."""
    rows = []
    for slug in DEMO_SLUGS:
        for role, permissions in GRANTS.items():
            role_id = connection.scalar(text("""
                SELECT r.id FROM roles_empresa AS r
                JOIN empresas AS e ON e.id = r.empresa_id
                WHERE e.slug = :slug AND r.codigo_sistema = :role
            """), {"slug": slug, "role": role})
            if role_id is None:
                rows.append((slug, role, None))
                continue
            added = 0
            for permission in permissions:
                result = connection.execute(text("""
                    INSERT INTO permisos_rol (rol_empresa_id, codigo)
                    VALUES (:role_id, :permission)
                    ON CONFLICT (rol_empresa_id, codigo) DO NOTHING
                """), {"role_id": role_id, "permission": permission})
                added += max(result.rowcount, 0)
            rows.append((slug, role, added))
    return rows


def main():
    target = use_demo_database()
    if target.database != "vestinova_pruebas":
        raise RuntimeError("Solo se permite actualizar vestinova_pruebas.")
    engine = build_engine(Settings.from_env())
    try:
        with engine.begin() as connection:
            rows = repair_grants(connection)
        print("CU21/CU22 — permisos DEMO verificados:")
        for slug, role, added in rows:
            if added is None:
                print(f"  {slug} / {role}: rol no encontrado. Revisa scripts.seed_demo.")
            else:
                print(f"  {slug} / {role}: {added} permisos agregados (0 = ya estaban).")
        print("Solo se actualizó vestinova_pruebas; no se modificó vestinova_mvp.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
