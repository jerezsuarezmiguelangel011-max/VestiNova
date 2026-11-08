from logging.config import fileConfig

from alembic import context

from app.config import Settings, validate_local_database_url
from app.db import Base, build_engine
from app import models  # noqa: F401, registra todos los modelos del MVP.
from app.compras_reservas.compras import persistence  # noqa: F401, registra únicamente las tablas propias de CU10.
from app.compras_reservas.compras import stripe_checkout  # noqa: F401, registra intentos Stripe CU09.
from app.compras_reservas.reservas import online  # noqa: F401, registra reservas CU10.
from app.operacion_sin_conexion.caja import online as cash_online  # noqa: F401, registra CU15/CU13.
from app.compras_reservas.postventa import persistence as postventa_persistence  # noqa: F401, registra las tablas de CU17.
from app.compras_reservas.compras import valoraciones  # noqa: F401, registra CU25.
from app.compras_reservas import alertas_push  # noqa: F401, registra CU26.
from app.compras_reservas import deseos as deseos_cu23  # noqa: F401, registra CU23.
from app.catalogo_publico import historial_recomendaciones as historial_cu19  # noqa: F401, registra CU19.


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = Settings.from_env()
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Una conexión explícita permite pruebas contra una instancia PostgreSQL aislada.
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        validate_local_database_url(supplied_connection.engine.url.render_as_string(hide_password=True))
        context.configure(connection=supplied_connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = build_engine(Settings.from_env())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
