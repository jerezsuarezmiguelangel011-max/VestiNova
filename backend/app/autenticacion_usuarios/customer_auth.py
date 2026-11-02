"""Cuenta pública de cliente ligada a la tienda de la URL, sin permisos de personal."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
import jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Cliente, Empresa, SesionCliente, utc_now
from app.password_policy import validate_new_password
from app.schemas import LoginRequest, normalizar_correo
from app.security import JWT_ISSUER, bearer, hash_password, unauthorized, verify_password, verify_unknown_password


CLIENT_JWT_AUDIENCE = "vestinova-clientes"
router = APIRouter(prefix="/api/tiendas/{slug}", tags=["Cuenta del cliente por tienda"])


class TiendaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    nombre: str


class RegistroClienteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=3, max_length=120)
    correo: str = Field(min_length=3, max_length=254)
    password: str = Field(strict=True)

    @field_validator("nombre", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    _correo = field_validator("correo")(normalizar_correo)


class ClienteResponse(BaseModel):
    id: int
    nombre: str
    correo: str
    rol: Literal["CLIENTE"] = "CLIENTE"
    empresa: TiendaResponse


class SesionClienteResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    cliente: ClienteResponse


def active_store(slug: str, db: Session = Depends(get_db)) -> Empresa:
    company = db.scalar(select(Empresa).where(Empresa.slug == slug, Empresa.activo.is_(True)))
    if company is None:
        raise HTTPException(404, "Tienda no disponible.")
    return company


def customer_response(customer: Cliente, company: Empresa) -> ClienteResponse:
    return ClienteResponse(id=customer.id, nombre=customer.nombre, correo=customer.correo,
                           empresa=TiendaResponse.model_validate(company))


def new_customer_session(db: Session, customer: Cliente, request: Request):
    """El llamador confirma cuenta y sesión en la misma transacción."""
    now = utc_now()
    expiry = now + timedelta(minutes=request.app.state.settings.session_minutes)
    session = SesionCliente(id=str(uuid4()), cliente_id=customer.id, expira_en=expiry, revocada=False)
    db.add(session)
    token = jwt.encode({"sub": str(customer.id), "jti": session.id, "tipo": "cliente",
                        "empresa_id": customer.empresa_id, "iat": now, "exp": expiry,
                        "iss": JWT_ISSUER, "aud": CLIENT_JWT_AUDIENCE},
                       request.app.state.settings.jwt_secret, algorithm="HS256")
    return token, expiry


def current_customer_session(request: Request, company: Empresa = Depends(active_store),
                             credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                             db: Session = Depends(get_db)) -> tuple[Cliente, SesionCliente, Empresa]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        claims = jwt.decode(credentials.credentials, request.app.state.settings.jwt_secret,
                            algorithms=["HS256"], issuer=JWT_ISSUER, audience=CLIENT_JWT_AUDIENCE,
                            options={"require": ["sub", "jti", "tipo", "empresa_id", "iat", "exp", "iss", "aud"]})
        customer_id = int(claims["sub"])
        session_id = str(claims["jti"])
        company_id = int(claims["empresa_id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise unauthorized() from None
    if claims["tipo"] != "cliente" or company_id != company.id:
        raise unauthorized()
    session = db.get(SesionCliente, session_id)
    customer = db.get(Cliente, customer_id)
    if (session is None or customer is None or not customer.activo or session.revocada
            or session.cliente_id != customer.id or customer.empresa_id != company.id):
        raise unauthorized()
    expiry = session.expira_en
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= utc_now():
        raise unauthorized()
    return customer, session, company


@router.get("", response_model=TiendaResponse)
def store(response: Response, company: Empresa = Depends(active_store)):
    response.headers["Cache-Control"] = "no-store"
    return company


@router.post("/cuenta/registro", response_model=SesionClienteResponse, status_code=201)
def register(payload: RegistroClienteRequest, request: Request, response: Response,
             company: Empresa = Depends(active_store), db: Session = Depends(get_db)):
    # Validar aquí evita reflejar la contraseña en el input de un error Pydantic.
    try:
        validate_new_password(payload.password)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    customer = Cliente(empresa_id=company.id, nombre=payload.nombre, correo=payload.correo,
                       password_hash=hash_password(payload.password), activo=True)
    db.add(customer)
    try:
        db.flush()
        token, expiry = new_customer_session(db, customer, request)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese correo ya está registrado en esta tienda.") from None
    response.headers["Cache-Control"] = "no-store"
    return SesionClienteResponse(access_token=token, expires_at=expiry, cliente=customer_response(customer, company))


@router.post("/cuenta/login", response_model=SesionClienteResponse)
def login(payload: LoginRequest, request: Request, response: Response,
          company: Empresa = Depends(active_store), db: Session = Depends(get_db)):
    customer = db.scalar(select(Cliente).where(Cliente.empresa_id == company.id, Cliente.correo == payload.correo))
    if customer is None:
        verify_unknown_password(payload.password)
        raise HTTPException(401, "Correo o contraseña incorrectos.", headers={"WWW-Authenticate": "Bearer"})
    if not verify_password(payload.password, customer.password_hash) or not customer.activo:
        raise HTTPException(401, "Correo o contraseña incorrectos.", headers={"WWW-Authenticate": "Bearer"})
    token, expiry = new_customer_session(db, customer, request)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return SesionClienteResponse(access_token=token, expires_at=expiry, cliente=customer_response(customer, company))


@router.get("/cuenta/me", response_model=ClienteResponse)
def me(response: Response, current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session)):
    response.headers["Cache-Control"] = "no-store"
    return customer_response(current[0], current[2])


@router.post("/cuenta/logout", status_code=204)
def logout(current: tuple[Cliente, SesionCliente, Empresa] = Depends(current_customer_session), db: Session = Depends(get_db)):
    current[1].revocada = True
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
