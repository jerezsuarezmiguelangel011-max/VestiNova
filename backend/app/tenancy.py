"""Autorización de empresa y sucursal leída del servidor en cada solicitud."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa, Sucursal
from app.security import require_administrator
from app.autenticacion_usuarios.permissions import RoleAccess, effective_role


@dataclass(frozen=True)
class TenantContext:
    empresa: Empresa
    membresia: MembresiaEmpresa
    usuario: Administrador
    acceso: RoleAccess | None = None

    @property
    def permisos(self) -> frozenset[str]:
        return self.acceso.permisos if self.acceso else frozenset()

    @property
    def administrador_empresa(self) -> bool:
        return self.acceso is not None and self.acceso.codigo_sistema == "ADMINISTRADOR"

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
    access = effective_role(db, membresia)
    if access is None:
        raise HTTPException(403, "El rol de esta pertenencia no está disponible.")
    return TenantContext(empresa=empresa, membresia=membresia, usuario=usuario, acceso=access)


def require_tenant_admin(context: TenantContext = Depends(require_tenant)) -> TenantContext:
    if not context.administrador_empresa:
        raise HTTPException(403, "Se requiere administración de la empresa.")
    return context


def lock_tenant_mutation(db: Session, context: TenantContext) -> TenantContext:
    # UPDATE sin cambio de datos adquiere el bloqueo de escritura también en SQLite.
    # Todas las mutaciones empresariales usan el mismo orden: empresa y luego recurso.
    db.execute(update(Empresa).where(Empresa.id == context.empresa_id).values(nombre=Empresa.nombre))
    company = db.get(Empresa, context.empresa_id, populate_existing=True)
    user = db.get(Administrador, context.usuario.id, populate_existing=True)
    member = db.get(MembresiaEmpresa, (context.usuario.id, context.empresa_id), populate_existing=True)
    if company is None or not company.activo or user is None or not user.activo or member is None or not member.activo:
        raise HTTPException(403, "Ya no tienes acceso activo a esta empresa.")
    access = effective_role(db, member)
    if access is None:
        raise HTTPException(403, "El rol de esta pertenencia no está disponible.")
    return TenantContext(company, member, user, access)


def check_permission(context: TenantContext, code: str) -> None:
    if code not in context.permisos:
        raise HTTPException(403, "No tienes permiso para realizar esta operación.")


def require_permission(code: str, *, mutation: bool = False):
    def dependency(context: TenantContext = Depends(require_tenant), db: Session = Depends(get_db)) -> TenantContext:
        if mutation:
            context = lock_tenant_mutation(db, context)
        check_permission(context, code)
        return context
    return dependency


def require_superadministrator(usuario: Administrador = Depends(require_administrator)) -> Administrador:
    if not usuario.es_superadministrador:
        raise HTTPException(403, "Se requiere superadministración de la plataforma.")
    return usuario


def authorized_branches_statement(context: TenantContext):
    statement = select(Sucursal).where(Sucursal.empresa_id == context.empresa_id, Sucursal.activo.is_(True))
    if not context.administrador_empresa:
        statement = statement.join(AccesoSucursal, (AccesoSucursal.sucursal_id == Sucursal.id) & (AccesoSucursal.empresa_id == Sucursal.empresa_id)).where(AccesoSucursal.administrador_id == context.usuario.id)
    return statement


def authorized_branch(db: Session, context: TenantContext, sucursal_id: int) -> Sucursal:
    branch = db.scalar(authorized_branches_statement(context).where(Sucursal.id == sucursal_id))
    if branch is None:
        raise HTTPException(404, "Sucursal no disponible para esta empresa y usuario.")
    return branch
