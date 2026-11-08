"""Catálogo cerrado de capacidades del backend y perfiles propios de cada empresa."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MembresiaEmpresa, PermisoRol, RolEmpresa


PERMISSIONS = (
    ("reportes.ia.consultar", "Generar reportes con IA", "Consultar reportes autorizados; requiere plan Profesional vigente.", ("sucursales.consultar",)),
    ("analitica.consultar", "Consultar dashboard predictivo", "Consultar modelos evaluados; reservado al Administrador de empresa.", ("sucursales.consultar",)),
    ("catalogo.consultar", "Consultar catálogo", "Consultar prendas y sus variantes.", ()),
    ("catalogo.gestionar", "Gestionar catálogo", "Registrar y editar prendas y variantes.", ("catalogo.consultar",)),
    ("sucursales.consultar", "Consultar sucursales", "Consultar las sucursales autorizadas.", ()),
    ("sucursales.gestionar", "Gestionar sucursales", "Registrar y editar sucursales de la empresa.", ("sucursales.consultar",)),
    ("inventario.consultar", "Consultar inventario", "Consultar saldos e historial de sucursales autorizadas.", ("sucursales.consultar", "catalogo.consultar")),
    ("inventario.registrar", "Registrar movimientos", "Registrar entradas y salidas de inventario en sucursales autorizadas.", ("inventario.consultar",)),
    ("inventario.ajustar", "Ajustar inventario", "Registrar incrementos, disminuciones y reingresos autorizados por sucursal.", ("inventario.consultar",)),
    ("abastecimiento.consultar", "Consultar abastecimiento", "Consultar proveedores y órdenes de compra de la empresa.", ("sucursales.consultar", "catalogo.consultar", "inventario.consultar")),
    ("abastecimiento.gestionar", "Gestionar abastecimiento", "Crear órdenes y registrar recepciones para sucursales autorizadas.", ("abastecimiento.consultar",)),
    ("promociones.consultar", "Consultar promociones", "Consultar descuentos y liquidaciones de la empresa.", ("catalogo.consultar",)),
    ("promociones.gestionar", "Gestionar promociones", "Registrar, editar y desactivar promociones de la empresa.", ("promociones.consultar", "catalogo.gestionar")),
    ("reportes.consultar", "Consultar reportes comerciales", "Consultar ventas, reservas e inventario del ámbito autorizado.", ("inventario.consultar",)),
    ("plan.consultar", "Consultar plan", "Consultar el plan y estado de suscripción de la empresa.", ()),
    ("descarga.consultar", "Descargar información", "Descargar catálogo e inventario de sucursales autorizadas.", ("catalogo.consultar", "sucursales.consultar", "inventario.consultar")),
    ("empresa.editar", "Editar empresa", "Editar el nombre de la empresa seleccionada.", ()),
    ("usuarios.consultar", "Consultar personal", "Consultar y buscar personal de esta empresa.", ()),
    ("usuarios.crear", "Registrar personal", "Crear una nueva cuenta de personal y asociarla a esta empresa.", ("usuarios.consultar", "roles.consultar", "sucursales.consultar")),
    ("usuarios.editar", "Editar personal", "Editar nombre local, estado, rol y sucursales del personal.", ("usuarios.consultar", "roles.consultar", "sucursales.consultar")),
    ("roles.consultar", "Consultar roles y permisos", "Consultar perfiles y el catálogo de permisos disponibles.", ()),
    ("roles.gestionar", "Gestionar roles", "Crear y editar perfiles personalizados de esta empresa.", ("roles.consultar",)),
    ("auditoria.consultar", "Consultar bitácora", "Consultar el historial de acciones relevantes de esta empresa.", ("usuarios.consultar",)),
    ("postventa.consultar", "Consultar cambios y devoluciones", "Consultar solicitudes de cambios y devoluciones en sucursales autorizadas.", ("sucursales.consultar",)),
    ("postventa.gestionar", "Gestionar cambios y devoluciones", "Aprobar, rechazar y completar solicitudes de postventa.", ("postventa.consultar",)),
)
PERMISSION_CODES = frozenset(item[0] for item in PERMISSIONS)
PERMISSION_REQUIREMENTS = {code: frozenset(required) for code, _, _, required in PERMISSIONS}
READ_PERMISSIONS = frozenset({"catalogo.consultar", "sucursales.consultar", "inventario.consultar", "descarga.consultar", "promociones.consultar", "postventa.consultar"})
SYSTEM_ROLES = {
    "ADMINISTRADOR": ("Administrador de empresa", "Administración completa de la empresa.", PERMISSION_CODES),
    "ENCARGADO_SUCURSAL": ("Encargado de sucursal", "Gestión de abastecimiento y consulta de información en sucursales asignadas.", READ_PERMISSIONS | {"abastecimiento.consultar", "abastecimiento.gestionar", "postventa.gestionar", "inventario.ajustar", "reportes.consultar", "reportes.ia.consultar"}),
    "CAJERO": ("Cajero", "Consulta de información en sucursales asignadas.", READ_PERMISSIONS | {"postventa.gestionar"}),
    "OPERADOR": ("Operador", "Perfil histórico de consulta en sucursales asignadas.", READ_PERMISSIONS),
}


@dataclass(frozen=True)
class RoleAccess:
    id: int | None
    nombre: str
    codigo_sistema: str | None
    permisos: frozenset[str]


def effective_role(db: Session, membership: MembresiaEmpresa) -> RoleAccess | None:
    if membership.rol_empresa_id is None:
        # Compatibilidad de cuentas creadas por integraciones previas y fixtures.
        # Solo NULL y códigos canónicos conocidos; un ID inválido nunca tiene fallback.
        preset = SYSTEM_ROLES.get(membership.rol)
        return RoleAccess(None, preset[0], membership.rol, preset[2]) if preset else None
    role = db.scalar(select(RolEmpresa).where(
        RolEmpresa.id == membership.rol_empresa_id,
        RolEmpresa.empresa_id == membership.empresa_id,
        RolEmpresa.activo.is_(True),
    ).execution_options(populate_existing=True))
    if role is None:
        return None
    codes = frozenset(db.scalars(select(PermisoRol.codigo).where(PermisoRol.rol_empresa_id == role.id)).all())
    # Los datos persistidos no pueden ampliar el catálogo ni omitir sus dependencias.
    valid = codes <= PERMISSION_CODES and all(PERMISSION_REQUIREMENTS[code] <= codes for code in codes)
    if not valid:
        return None
    return RoleAccess(role.id, role.nombre, role.codigo_sistema, codes)


def ensure_company_roles(db: Session, empresa_id: int) -> dict[str, RolEmpresa]:
    """Solo para altas/migración explícitas, nunca desde consultas GET."""
    rows = {role.codigo_sistema: role for role in db.scalars(select(RolEmpresa).where(
        RolEmpresa.empresa_id == empresa_id, RolEmpresa.codigo_sistema.is_not(None)
    )).all()}
    for code, (name, description, permissions) in SYSTEM_ROLES.items():
        if code in rows:
            continue
        role = RolEmpresa(empresa_id=empresa_id, nombre=name, nombre_clave=name.casefold(), descripcion=description,
                          codigo_sistema=code, activo=True)
        db.add(role)
        db.flush()
        db.add_all(PermisoRol(rol_empresa_id=role.id, codigo=permission) for permission in sorted(permissions))
        rows[code] = role
    db.flush()
    return rows
