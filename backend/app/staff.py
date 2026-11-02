"""CU02: personal local, perfiles empresariales y permisos efectivos del servidor."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccesoSucursal, Administrador, MembresiaEmpresa, PermisoRol, RolEmpresa, Sucursal
from app.password_policy import validate_new_password
from app.permissions import PERMISSIONS, PERMISSION_CODES, PERMISSION_REQUIREMENTS, SYSTEM_ROLES, effective_role
from app.schemas import normalizar_correo
from app.security import hash_password
from app.tenancy import TenantContext, require_permission, require_tenant


router = APIRouter(prefix="/api/admin", tags=["Usuarios, roles y permisos"])
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("nombre", check_fields=False, mode="before")
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class Changes(Input):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Envía al menos un cambio no nulo.")
        return self


class RoleCreate(Input):
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str = Field(default="", max_length=500)
    permisos: list[str] = Field(max_length=50)


class RolePatch(Changes):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    descripcion: str | None = Field(default=None, max_length=500)
    permisos: list[str] | None = Field(default=None, max_length=50)
    activo: bool | None = Field(default=None, strict=True)


class RoleResponse(BaseModel):
    id: int
    empresa_id: int
    nombre: str
    descripcion: str
    codigo_sistema: str | None
    protegido: bool
    activo: bool
    permisos: list[str]


class Branches(Input):
    @field_validator("sucursal_ids", check_fields=False)
    @classmethod
    def unique_branches(cls, value):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Las sucursales no pueden repetirse.")
        return value


class StaffCreate(Branches):
    nombre: str = Field(min_length=3, max_length=120)
    correo: str = Field(min_length=3, max_length=254)
    password: str = Field(strict=True)
    rol_id: PositiveId
    activo: bool = Field(default=True, strict=True)
    sucursal_ids: list[PositiveId] = Field(default_factory=list, max_length=100)
    _email = field_validator("correo")(normalizar_correo)

class StaffPatch(Branches, Changes):
    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    rol_id: PositiveId | None = None
    activo: bool | None = Field(default=None, strict=True)
    sucursal_ids: list[PositiveId] | None = Field(default=None, max_length=100)


class StaffResponse(BaseModel):
    id: int
    empresa_id: int
    nombre: str
    correo: str
    activo: bool
    rol_id: int | None
    rol_nombre: str
    rol_sistema: str | None
    rol_activo: bool
    acceso_habilitado: bool
    sucursal_ids: list[int]


class StaffPage(BaseModel):
    items: list[StaffResponse]
    total: int
    limit: int
    offset: int


class AccessResponse(BaseModel):
    empresa_id: int
    usuario_id: int
    nombre: str
    rol_id: int | None
    rol_nombre: str
    rol_sistema: str | None
    permisos: list[str]


def permission_codes(db: Session, role_id: int) -> frozenset[str]:
    return frozenset(db.scalars(select(PermisoRol.codigo).where(PermisoRol.rol_empresa_id == role_id)).all())


def role_response(db: Session, role: RolEmpresa) -> RoleResponse:
    return RoleResponse(id=role.id, empresa_id=role.empresa_id, nombre=role.nombre, descripcion=role.descripcion,
                        codigo_sistema=role.codigo_sistema, protegido=role.codigo_sistema is not None,
                        activo=role.activo, permisos=sorted(permission_codes(db, role.id)))


def get_role(db: Session, company_id: int, role_id: int, *, active: bool = False) -> RolEmpresa:
    role = db.scalar(select(RolEmpresa).where(RolEmpresa.id == role_id, RolEmpresa.empresa_id == company_id)
                     .execution_options(populate_existing=True))
    if role is None or (active and not role.activo):
        raise HTTPException(404, "Rol no disponible en esta empresa.")
    return role


def validate_permissions(values: list[str], context: TenantContext) -> frozenset[str]:
    codes = frozenset(values)
    if len(codes) != len(values) or not codes <= PERMISSION_CODES:
        raise HTTPException(422, "Selecciona permisos válidos del catálogo, sin duplicados.")
    missing = {dependency for code in codes for dependency in PERMISSION_REQUIREMENTS[code] if dependency not in codes}
    if missing:
        raise HTTPException(422, "Faltan permisos requeridos: " + ", ".join(sorted(missing)) + ".")
    if not codes <= context.permisos:
        raise HTTPException(403, "No puedes conceder permisos que no posees.")
    return codes


def check_assignable_role(db: Session, context: TenantContext, role: RolEmpresa) -> None:
    if role.codigo_sistema == "ADMINISTRADOR" and not context.administrador_empresa:
        raise HTTPException(403, "Solo un administrador de empresa puede asignar ese rol.")
    if not permission_codes(db, role.id) <= context.permisos:
        raise HTTPException(403, "No puedes gestionar un rol con permisos que no posees.")


def get_member(db: Session, company_id: int, user_id: int) -> tuple[MembresiaEmpresa, Administrador]:
    row = db.execute(select(MembresiaEmpresa, Administrador).join(Administrador, Administrador.id == MembresiaEmpresa.administrador_id)
                     .where(MembresiaEmpresa.empresa_id == company_id, MembresiaEmpresa.administrador_id == user_id)
                     .execution_options(populate_existing=True)).one_or_none()
    if row is None:
        raise HTTPException(404, "Usuario no disponible en esta empresa.")
    return row


def member_branches(db: Session, member: MembresiaEmpresa) -> list[int]:
    return list(db.scalars(select(AccesoSucursal.sucursal_id).where(
        AccesoSucursal.empresa_id == member.empresa_id, AccesoSucursal.administrador_id == member.administrador_id
    ).order_by(AccesoSucursal.sucursal_id)).all())


def staff_response(db: Session, member: MembresiaEmpresa, user: Administrador) -> StaffResponse:
    role = get_role(db, member.empresa_id, member.rol_empresa_id) if member.rol_empresa_id is not None else None
    return StaffResponse(id=user.id, empresa_id=member.empresa_id, nombre=member.nombre or user.nombre, correo=user.correo,
                         activo=member.activo, rol_id=member.rol_empresa_id,
                         rol_nombre=role.nombre if role else SYSTEM_ROLES[member.rol][0],
                         rol_sistema=role.codigo_sistema if role else member.rol,
                         rol_activo=role.activo if role else True,
                         acceso_habilitado=user.activo and member.activo and effective_role(db, member) is not None,
                         sucursal_ids=member_branches(db, member))


def check_target_authority(db: Session, context: TenantContext, member: MembresiaEmpresa) -> None:
    if member.rol_empresa_id is not None:
        check_assignable_role(db, context, get_role(db, member.empresa_id, member.rol_empresa_id))
    else:
        if member.rol == "ADMINISTRADOR" and not context.administrador_empresa:
            raise HTTPException(403, "Solo un administrador puede gestionar esa pertenencia.")
        if not SYSTEM_ROLES[member.rol][2] <= context.permisos:
            raise HTTPException(403, "No puedes gestionar una pertenencia con permisos que no posees.")


def protect_last_administrator(db: Session, member: MembresiaEmpresa, *, active: bool, system_role: str | None) -> None:
    current_access = effective_role(db, member)
    if not member.activo or current_access is None or current_access.codigo_sistema != "ADMINISTRADOR":
        return
    if active and system_role == "ADMINISTRADOR":
        return
    # La cuenta global debe estar activa: una pertenencia de una identidad bloqueada
    # no puede mantener la administración. Roles personalizados no sustituyen este rol.
    other_admin = db.scalar(select(func.count()).select_from(MembresiaEmpresa)
        .join(Administrador, Administrador.id == MembresiaEmpresa.administrador_id)
        .outerjoin(RolEmpresa, (RolEmpresa.id == MembresiaEmpresa.rol_empresa_id) & (RolEmpresa.empresa_id == MembresiaEmpresa.empresa_id))
        .where(MembresiaEmpresa.empresa_id == member.empresa_id, MembresiaEmpresa.administrador_id != member.administrador_id,
               MembresiaEmpresa.activo.is_(True), Administrador.activo.is_(True),
               or_((MembresiaEmpresa.rol_empresa_id.is_(None)) & (MembresiaEmpresa.rol == "ADMINISTRADOR"),
                   (RolEmpresa.codigo_sistema == "ADMINISTRADOR") & RolEmpresa.activo.is_(True))))
    if not other_admin:
        raise HTTPException(409, "La empresa debe conservar al menos un administrador activo.")


def validate_branches(db: Session, context: TenantContext, ids: list[int], system_role: str | None) -> None:
    if system_role == "ADMINISTRADOR" and ids:
        raise HTTPException(422, "El administrador accede a todas las sucursales activas; no envíes sucursal_ids.")
    if ids:
        available = set(db.scalars(select(Sucursal.id).where(Sucursal.empresa_id == context.empresa_id,
                         Sucursal.activo.is_(True), Sucursal.id.in_(ids))).all())
        if available != set(ids):
            raise HTTPException(404, "Una sucursal no está disponible en esta empresa.")
        if not context.administrador_empresa:
            own = set(member_branches(db, context.membresia))
            if not set(ids) <= own:
                raise HTTPException(403, "No puedes asignar sucursales que no tienes autorizadas.")


def replace_branches(db: Session, member: MembresiaEmpresa, ids: list[int]) -> None:
    db.execute(delete(AccesoSucursal).where(AccesoSucursal.empresa_id == member.empresa_id,
                                          AccesoSucursal.administrador_id == member.administrador_id))
    db.add_all(AccesoSucursal(empresa_id=member.empresa_id, administrador_id=member.administrador_id, sucursal_id=id_) for id_ in ids)


def commit_staff(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo guardar: los datos ya existen o no están disponibles.") from None


@router.get("/acceso", response_model=AccessResponse)
def access(response: Response, context: TenantContext = Depends(require_tenant)):
    response.headers["Cache-Control"] = "no-store"
    return AccessResponse(empresa_id=context.empresa_id, usuario_id=context.usuario.id, nombre=context.membresia.nombre or context.usuario.nombre,
                          rol_id=context.acceso.id, rol_nombre=context.acceso.nombre, rol_sistema=context.acceso.codigo_sistema,
                          permisos=sorted(context.permisos))


@router.get("/permisos")
def list_permissions(_: TenantContext = Depends(require_permission("roles.consultar"))):
    return [{"codigo": code, "nombre": name, "descripcion": description, "requiere": list(required)}
            for code, name, description, required in PERMISSIONS]


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(context: TenantContext = Depends(require_permission("roles.consultar")), db: Session = Depends(get_db)):
    return [role_response(db, role) for role in db.scalars(select(RolEmpresa).where(
        RolEmpresa.empresa_id == context.empresa_id).order_by(RolEmpresa.id)).all()]


@router.post("/roles", response_model=RoleResponse, status_code=201)
def create_role(payload: RoleCreate, context: TenantContext = Depends(require_permission("roles.gestionar", mutation=True)), db: Session = Depends(get_db)):
    codes = validate_permissions(payload.permisos, context)
    role = RolEmpresa(empresa_id=context.empresa_id, nombre=payload.nombre, nombre_clave=payload.nombre.casefold(),
                      descripcion=payload.descripcion.strip(), activo=True)
    db.add(role)
    try:
        db.flush()
        db.add_all(PermisoRol(rol_empresa_id=role.id, codigo=code) for code in sorted(codes))
        commit_staff(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un rol con ese nombre en esta empresa.") from None
    return role_response(db, role)


@router.patch("/roles/{rol_id}", response_model=RoleResponse)
def update_role(rol_id: int, payload: RolePatch, context: TenantContext = Depends(require_permission("roles.gestionar", mutation=True)), db: Session = Depends(get_db)):
    role = get_role(db, context.empresa_id, rol_id)
    if role.codigo_sistema is not None:
        raise HTTPException(409, "Los roles del sistema están protegidos; crea un rol personalizado.")
    check_assignable_role(db, context, role)
    changes = payload.model_dump(exclude_unset=True)
    if "permisos" in changes:
        codes = validate_permissions(changes.pop("permisos"), context)
        db.execute(delete(PermisoRol).where(PermisoRol.rol_empresa_id == role.id))
        db.add_all(PermisoRol(rol_empresa_id=role.id, codigo=code) for code in sorted(codes))
    for field, value in changes.items():
        setattr(role, field, value.strip() if isinstance(value, str) else value)
    role.nombre_clave = role.nombre.casefold()
    commit_staff(db)
    return role_response(db, role)


@router.get("/usuarios", response_model=StaffPage)
def list_staff(q: str | None = Query(default=None, max_length=120), estado: Literal["activo", "inactivo", "todos"] = "todos",
               rol_id: int | None = Query(default=None, gt=0), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
               context: TenantContext = Depends(require_permission("usuarios.consultar")), db: Session = Depends(get_db)):
    filters = [MembresiaEmpresa.empresa_id == context.empresa_id]
    if estado != "todos":
        filters.append(MembresiaEmpresa.activo.is_(estado == "activo"))
    if rol_id is not None:
        get_role(db, context.empresa_id, rol_id)
        filters.append(MembresiaEmpresa.rol_empresa_id == rol_id)
    if q and q.strip():
        needle = q.strip().lower()
        filters.append(or_(func.lower(func.coalesce(MembresiaEmpresa.nombre, Administrador.nombre)).contains(needle, autoescape=True),
                           func.lower(Administrador.correo).contains(needle, autoescape=True)))
    base = select(MembresiaEmpresa, Administrador).join(Administrador, Administrador.id == MembresiaEmpresa.administrador_id).where(*filters)
    count = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(base.order_by(MembresiaEmpresa.administrador_id).limit(limit).offset(offset)).all()
    return StaffPage(items=[staff_response(db, member, user) for member, user in rows], total=count, limit=limit, offset=offset)


@router.get("/usuarios/{usuario_id}", response_model=StaffResponse)
def detail_staff(usuario_id: int, context: TenantContext = Depends(require_permission("usuarios.consultar")), db: Session = Depends(get_db)):
    return staff_response(db, *get_member(db, context.empresa_id, usuario_id))


@router.post("/usuarios", response_model=StaffResponse, status_code=201)
def create_staff(payload: StaffCreate, context: TenantContext = Depends(require_permission("usuarios.crear", mutation=True)), db: Session = Depends(get_db)):
    try:
        validate_new_password(payload.password)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    role = get_role(db, context.empresa_id, payload.rol_id, active=True)
    check_assignable_role(db, context, role)
    validate_branches(db, context, payload.sucursal_ids, role.codigo_sistema)
    if db.scalar(select(Administrador.id).where(Administrador.correo == payload.correo)) is not None:
        raise HTTPException(409, "No se puede registrar una cuenta con esos datos.")
    user = Administrador(nombre=payload.nombre, correo=payload.correo, password_hash=hash_password(payload.password), activo=True, es_superadministrador=False)
    db.add(user)
    try:
        db.flush()
        member = MembresiaEmpresa(administrador_id=user.id, empresa_id=context.empresa_id, nombre=payload.nombre,
                                 rol=role.codigo_sistema or "OPERADOR", rol_empresa_id=role.id, activo=payload.activo)
        db.add(member)
        db.flush()
        replace_branches(db, member, payload.sucursal_ids)
        commit_staff(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede registrar una cuenta con esos datos.") from None
    return staff_response(db, member, user)


@router.patch("/usuarios/{usuario_id}", response_model=StaffResponse)
def update_staff(usuario_id: int, payload: StaffPatch, context: TenantContext = Depends(require_permission("usuarios.editar", mutation=True)), db: Session = Depends(get_db)):
    member, user = get_member(db, context.empresa_id, usuario_id)
    check_target_authority(db, context, member)
    changes = payload.model_dump(exclude_unset=True)
    role = get_role(db, context.empresa_id, changes["rol_id"], active=True) if "rol_id" in changes else None
    if role is not None:
        check_assignable_role(db, context, role)
        system_code = role.codigo_sistema
    elif member.rol_empresa_id is not None:
        system_code = get_role(db, context.empresa_id, member.rol_empresa_id).codigo_sistema
    else:
        system_code = member.rol
    ids = changes.get("sucursal_ids", [] if system_code == "ADMINISTRADOR" else member_branches(db, member))
    # Reactivar vuelve a conceder el acceso guardado, aunque no se reenvíen IDs.
    # Ediciones de nombre o desactivaciones conservan concesiones históricas.
    reactivating = changes.get("activo") is True and not member.activo
    if "sucursal_ids" in changes or "rol_id" in changes:
        validate_branches(db, context, ids, system_code)
    elif reactivating and not context.administrador_empresa:
        if not set(ids) <= set(member_branches(db, context.membresia)):
            raise HTTPException(403, "No puedes reactivar accesos a sucursales que no tienes autorizadas.")
    protect_last_administrator(db, member, active=changes.get("activo", member.activo), system_role=system_code)
    if "nombre" in changes:
        member.nombre = changes["nombre"]
    if "activo" in changes:
        member.activo = changes["activo"]
    if role is not None:
        member.rol_empresa_id = role.id
        member.rol = role.codigo_sistema or "OPERADOR"
    if "sucursal_ids" in changes or "rol_id" in changes:
        replace_branches(db, member, ids)
    commit_staff(db)
    return staff_response(db, member, user)
