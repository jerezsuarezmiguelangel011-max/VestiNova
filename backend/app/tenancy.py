"""Autorización de empresa y sucursal leída del servidor en cada solicitud."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa, Sucursal
from app.security import require_administrator


@dataclass(frozen=True)
class TenantContext:
    empresa: Empresa
    membresia: MembresiaEmpresa
    usuario: Administrador

    @property
    def empresa_id(self) -> int:
        return self.empresa.id


def require_tenant(
    empresa_id: Annotated[int | None, Header(alias="X-Empresa-Id", ge=1)] = None,
    usuario: Administrador = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> TenantContext:
    statement = select(Empresa, MembresiaEmpresa).join(MembresiaEmpresa, MembresiaEmpresa.empresa_id == Empresa.id).where(
        MembresiaEmpresa.administrador_id == usuario.id, MembresiaEmpresa.activo.is_(True), Empresa.activo.is_(True)
    )
    if empresa_id is not None:
        statement = statement.where(Empresa.id == empresa_id)
    contexts = db.execute(statement).all()
    if not contexts:
        raise HTTPException(403, "No tienes pertenencia activa a esa empresa.")
    if len(contexts) > 1:
        raise HTTPException(409, "Selecciona una empresa mediante X-Empresa-Id.")
    empresa, membresia = contexts[0]
    return TenantContext(empresa=empresa, membresia=membresia, usuario=usuario)


def require_tenant_admin(context: TenantContext = Depends(require_tenant)) -> TenantContext:
    if context.membresia.rol != "ADMINISTRADOR":
        raise HTTPException(403, "Se requiere administración de la empresa.")
    return context


def require_superadministrator(usuario: Administrador = Depends(require_administrator)) -> Administrador:
    if not usuario.es_superadministrador:
        raise HTTPException(403, "Se requiere superadministración de la plataforma.")
    return usuario


def authorized_branches_statement(context: TenantContext):
    statement = select(Sucursal).where(Sucursal.empresa_id == context.empresa_id, Sucursal.activo.is_(True))
    if context.membresia.rol != "ADMINISTRADOR":
        statement = statement.join(AccesoSucursal, (AccesoSucursal.sucursal_id == Sucursal.id) & (AccesoSucursal.empresa_id == Sucursal.empresa_id)).where(AccesoSucursal.administrador_id == context.usuario.id)
    return statement


def authorized_branch(db: Session, context: TenantContext, sucursal_id: int) -> Sucursal:
    branch = db.scalar(authorized_branches_statement(context).where(Sucursal.id == sucursal_id))
    if branch is None:
        raise HTTPException(404, "Sucursal no disponible para esta empresa y usuario.")
    return branch
