"""Consulta local de IDs públicos de empresas/sucursales; nunca concede permisos."""
from sqlalchemy import select

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import Empresa, Sucursal


def main() -> None:
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine)() as db:
            companies = db.scalars(select(Empresa).order_by(Empresa.id)).all()
            if not companies:
                print("No hay empresas registradas. Aplica las migraciones antes de crear accesos.")
            for company in companies:
                print(f"Empresa ID {company.id} | {company.slug} | {company.nombre} | activa: {company.activo}")
                branches = db.scalars(select(Sucursal).where(Sucursal.empresa_id == company.id).order_by(Sucursal.id)).all()
                for branch in branches:
                    print(f"  Sucursal ID {branch.id} | {branch.codigo} | {branch.nombre} | activa: {branch.activo}")
                if not branches:
                    print("  Sin sucursales registradas.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print("No se pudo consultar el contexto. Comprueba PostgreSQL local, .env y las migraciones.")
        raise SystemExit(1) from None
