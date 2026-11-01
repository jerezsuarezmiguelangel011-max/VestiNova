"""Crea, si no existe, exclusivamente vestinova_mvp local y aplica Alembic."""
from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.config import BACKEND_ROOT, Settings


def main() -> None:
    settings = Settings.from_env()  # Rechaza otras bases o servidores remotos.
    url = make_url(settings.database_url)
    with psycopg.connect(host=url.host, port=url.port or 5432, user=url.username, password=url.password, dbname="postgres", autocommit=True) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("vestinova_mvp",)).fetchone()
        if exists:
            print("La base vestinova_mvp ya existe. Se conservarán sus datos.")
        else:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("vestinova_mvp")))
            print("Base local vestinova_mvp creada.")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")
    print("Migraciones de vestinova_mvp aplicadas. La base vestinova no se modificó.")
    print("Si todavía no tienes una cuenta, ejecuta python -m scripts.create_admin. Al actualizar, conserva tu administrador actual.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        # Los errores de conexión pueden incluir el DSN; no imprimirlos con credenciales.
        print("No se completó la inicialización. Comprueba .env, PostgreSQL local y permiso CREATEDB del usuario.")
        raise SystemExit(1) from None
