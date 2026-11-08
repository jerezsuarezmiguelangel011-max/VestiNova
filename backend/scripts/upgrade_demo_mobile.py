"""Actualiza SOLO vestinova_pruebas para probar CU09 móvil.

No modifica .env ni la base operativa vestinova_mvp.
"""
from pathlib import Path
import os

from alembic import command
from alembic.config import Config

from app.config import BACKEND_ROOT
from scripts.demo_environment import use_demo_database


def main():
    db = use_demo_database()
    if db.database != "vestinova_pruebas":
        raise RuntimeError("Cancelado: el destino no es vestinova_pruebas.")
    os.chdir(BACKEND_ROOT)
    ini = Config(str(BACKEND_ROOT / "alembic.ini"))
    print("Actualizando únicamente vestinova_pruebas...")
    command.upgrade(ini, "head")
    print("Migración demo completada. No se modificó vestinova_mvp.")


if __name__ == "__main__":
    main()
