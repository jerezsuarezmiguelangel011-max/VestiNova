import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory, get_db
# Autenticacion y usuarios.
from app.autenticacion_usuarios.auth import router as auth_router
from app.autenticacion_usuarios.customer_auth import router as customer_auth_router
from app.autenticacion_usuarios.staff import router as staff_router

# Organizacion empresarial.
from app.organizacion_empresarial.audit import router as audit_router
from app.organizacion_empresarial.branches import router as branches_router
from app.organizacion_empresarial.organizations import router as organizations_router
from app.organizacion_empresarial.platform_companies import router as platform_companies_router
from app.organizacion_empresarial.platform_plans import router as platform_plans_router
from app.organizacion_empresarial.plans import router as plans_router

# Catalogo y abastecimiento.
from app.catalogo_abastecimiento.categories import router as categories_router
from app.catalogo_abastecimiento.productos import admin_router
from app.catalogo_abastecimiento.procurement import router as procurement_router
from app.catalogo_abastecimiento.promotions import router as promotions_router
from app.catalogo_abastecimiento.variantes import router as variantes_router

# Inventario, catalogo publico, compras y operacion sin conexion.
from app.inventario.api import router as inventario_router
from app.catalogo_publico.catalogo import router as catalog_router, directory_router as public_directory_router
from app.compras_reservas.compras.router import router as compras_router
from app.compras_reservas.compras.stripe_checkout import router as stripe_checkout_router, webhook_router as stripe_webhook_router
from app.compras_reservas.compras.history import router as historial_compras_router
from app.compras_reservas.reservas.online import (
    customer_router as customer_reservations_router,
    staff_router as staff_reservations_router,
    expire_all_due,
)
from app.compras_reservas.postventa.router import customer_router as postventa_cliente_router
from app.compras_reservas.postventa.router import staff_router as postventa_personal_router
from app.operacion_sin_conexion.mobile_download import router as mobile_router
from app.compras_reservas.reservas.attention import router as attention_reservations_router
from app.operacion_sin_conexion.caja.online import router as cash_sales_router, catalog_router as cash_catalog_router
from app.operacion_sin_conexion.sincronizacion.reconciliation import router as reconciliation_router
from app.catalogo_publico.recomendaciones import router as recomendaciones_router
from app.compras_reservas.deseos import router as deseos_router
from app.reportes_comerciales import router as reportes_comerciales_router


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    settings = settings or get_settings()
    database_engine = engine if engine is not None else build_engine(settings)

    session_factory = build_session_factory(database_engine)

    async def periodic_reservation_expiry():
        # Las consultas también vencen reservas, pero la liberación no debe
        # depender de visitas web. Cada instancia verifica cada minuto.
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(expire_all_due, session_factory)
            except Exception:
                logging.getLogger(__name__).exception(
                    "CU10: no se pudo completar el vencimiento periódico; se reintentará."
                )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        expiry_task = asyncio.create_task(periodic_reservation_expiry())
        try:
            yield
        finally:
            expiry_task.cancel()
            try:
                await expiry_task
            except asyncio.CancelledError:
                pass
            database_engine.dispose()

    app = FastAPI(title="VestiNova MVP", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = database_engine
    app.state.session_factory = session_factory
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Empresa-Id", "ngsw-bypass"])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError):
        # Pydantic incluye por defecto el valor recibido (también contraseñas).
        # Mantener estado, ubicación y mensaje sin reflejar cuerpos ni contextos.
        details = [{key: item[key] for key in ("type", "loc", "msg") if key in item}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details}, headers={"Cache-Control": "no-store"})

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(_: Request, __: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "La base de datos no está disponible. Intenta nuevamente."})

    @app.get("/api/health", tags=["Estado"])
    def health():
        return {"status": "ok", "application": "vestinova-mvp"}

    @app.get("/api/health/db", tags=["Estado"])
    def health_database(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": make_url(settings.database_url).database}
    # Autenticacion y usuarios.
    app.include_router(auth_router)
    app.include_router(customer_auth_router)
    app.include_router(staff_router)

    # Organizacion empresarial.
    app.include_router(audit_router)
    app.include_router(branches_router)
    app.include_router(organizations_router)
    app.include_router(platform_companies_router)
    app.include_router(platform_plans_router)
    app.include_router(plans_router)

    # Catalogo y abastecimiento.
    app.include_router(categories_router)
    app.include_router(admin_router)
    app.include_router(variantes_router)
    app.include_router(promotions_router)
    app.include_router(procurement_router)

    # Inventario, catalogo publico, compras y operacion sin conexion.
    app.include_router(inventario_router)
    app.include_router(public_directory_router)
    app.include_router(catalog_router)
    app.include_router(compras_router)
    app.include_router(stripe_checkout_router)
    app.include_router(stripe_webhook_router)
    app.include_router(historial_compras_router)
    app.include_router(customer_reservations_router)
    app.include_router(staff_reservations_router)
    app.include_router(attention_reservations_router)
    app.include_router(cash_catalog_router)
    app.include_router(cash_sales_router)
    app.include_router(reconciliation_router)
    app.include_router(recomendaciones_router)
    app.include_router(deseos_router)
    app.include_router(reportes_comerciales_router)
    app.include_router(postventa_cliente_router)
    app.include_router(postventa_personal_router)
    app.include_router(mobile_router)
    return app


# Usar: uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
