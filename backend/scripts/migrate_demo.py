"""Aplica migraciones exclusivamente sobre vestinova_pruebas local.

No carga semillas ni modifica la base vestinova_mvp.
"""
from alembic import command
from alembic.config import Config

from app.config import BACKEND_ROOT
from scripts.demo_environment import use_demo_database


def main() -> None:
    use_demo_database()  # Valida URL local y fija exclusivamente vestinova_pruebas.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")
    print("Migraciones aplicadas a vestinova_pruebas; vestinova_mvp no fue modificada.")


if __name__ == "__main__":
    main()
