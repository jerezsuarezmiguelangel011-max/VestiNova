"""Selecciona la base de demostración sin alterar el archivo .env del usuario."""
import os

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.config import BACKEND_ROOT, Settings, get_settings, validate_local_database_url


def use_demo_database():
    values = dotenv_values(BACKEND_ROOT / ".env", interpolate=False)
    original = values.get("DATABASE_URL") or ""
    # La base fuente debe ser el PostgreSQL local habitual; nunca se admite
    # copiar la configuración de producción hacia el entorno de demostración.
    validate_local_database_url(original)
    demo_url = make_url(original).set(database="vestinova_pruebas")
    os.environ["APP_ENV"] = "demo"
    os.environ["DATABASE_URL"] = demo_url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    Settings.from_env()  # Revalidar el destino antes de abrir conexiones.
    return demo_url
