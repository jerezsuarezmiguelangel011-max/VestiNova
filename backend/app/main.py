from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import router as auth_router
from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory, get_db
from app.products import admin_router, catalog_router
from app.purchases.router import router as purchases_router


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    settings = settings or get_settings()
    database_engine = engine if engine is not None else build_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        database_engine.dispose()

    app = FastAPI(title="VestiNova MVP", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = database_engine
    app.state.session_factory = build_session_factory(database_engine)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(_: Request, __: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "La base de datos no está disponible. Intenta nuevamente."})

    @app.get("/api/health", tags=["Estado"])
    def health():
        return {"status": "ok", "application": "vestinova-mvp"}

    @app.get("/api/health/db", tags=["Estado"])
    def health_database(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "vestinova_mvp"}

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(purchases_router)
    return app


# Usar: uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
