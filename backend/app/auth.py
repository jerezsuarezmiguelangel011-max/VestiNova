from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Administrador, SesionAdministrador, Sucursal
from app.organizations import EmpresaAccesoResponse, EmpresaResponse, SucursalResponse
from app.schemas import AdministradorResponse, LoginRequest, LoginResponse
from app.security import get_current_session, issue_session, require_administrator, verify_password, verify_unknown_password
from app.tenancy import TenantContext, authorized_branches_statement, require_tenant


router = APIRouter(prefix="/api/auth", tags=["Acceso del personal"])


class ContextoAccesoResponse(BaseModel):
    empresa: EmpresaAccesoResponse
    sucursales: list[SucursalResponse]


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    administrator = db.scalar(select(Administrador).where(Administrador.correo == payload.correo))
    if administrator is None:
        verify_unknown_password(payload.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.", headers={"WWW-Authenticate": "Bearer"})
    if not verify_password(payload.password, administrator.password_hash) or not administrator.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.", headers={"WWW-Authenticate": "Bearer"})
    token, expiry = issue_session(db, administrator, request)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(access_token=token, expires_at=expiry, administrador=AdministradorResponse.model_validate(administrator))


@router.get("/me", response_model=AdministradorResponse)
def me(response: Response, administrator: Administrador = Depends(require_administrator)):
    response.headers["Cache-Control"] = "no-store"
    return administrator


@router.get("/contexto", response_model=ContextoAccesoResponse)
def context(response: Response, current: TenantContext = Depends(require_tenant), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    company = {**EmpresaResponse.model_validate(current.empresa).model_dump(), "rol": current.membresia.rol}
    branches = db.scalars(authorized_branches_statement(current).order_by(Sucursal.id)).all()
    return {"empresa": company, "sucursales": branches}


@router.post("/logout", status_code=204)
def logout(current: tuple[Administrador, SesionAdministrador] = Depends(get_current_session), db: Session = Depends(get_db)):
    current[1].revocada = True
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
