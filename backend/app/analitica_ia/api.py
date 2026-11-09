from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Administrador, CategoriaProducto, Producto
from app.organizacion_empresarial.plans import current_subscription, subscription_state
from app.tenancy import TenantContext, check_permission, require_permission, require_tenant
from app.security import get_current_session
from app.analitica_ia.analytics import dashboard, load_models
from app.analitica_ia.exports import export_report
from app.analitica_ia.provider import configured, get_interpreter, Interpreter
from app.analitica_ia.queries import REPORTS, build_report, resolve_names, scope
from app.analitica_ia.schemas import DashboardRequest, ExportRequest, ReportRequest

router = APIRouter(prefix="/api/admin", tags=["CU21 · Reportes IA / CU22 · Dashboard predictivo"])


def active_plan(db, context, professional=False):
    current = current_subscription(db, context.empresa_id)
    if current is None or not current[1].activo or subscription_state(current[0]) != "ACTIVA":
        raise HTTPException(403, "Se requiere una suscripción vigente para esta consulta.")
    if professional and current[1].codigo != "PROFESIONAL":
        raise HTTPException(403, "Los reportes con IA requieren el plan Profesional vigente.")


def fresh_context(db, context, permission):
    identifier = context.usuario.id
    company = context.empresa_id
    db.expire_all()
    user = db.get(Administrador, identifier)
    if user is None or not user.activo:
        raise HTTPException(401, "Tu cuenta ya no está activa.")
    refreshed = require_tenant(empresa_id=company, usuario=user, db=db)
    check_permission(refreshed, permission)
    return refreshed


@router.get("/reportes-ia/opciones")
def options(response: Response, context: TenantContext = Depends(require_permission("reportes.ia.consultar")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    from app.analitica_ia.schemas import Filters
    _, branches = scope(db, context, Filters())
    current = current_subscription(db, context.empresa_id)
    allowed = bool(current and current[1].activo and current[1].codigo == "PROFESIONAL" and subscription_state(current[0]) == "ACTIVA")
    return {"profesional_vigente": allowed, "ia_configurada": configured(),
            "tipos": [{"codigo": key, "nombre": value[0]} for key, value in REPORTS.items()],
            "sucursales": [{"id": branch.id, "nombre": branch.nombre} for branch in branches],
            "categorias": [{"id": record.id, "nombre": record.nombre} for record in db.scalars(select(CategoriaProducto).where(CategoriaProducto.empresa_id == context.empresa_id)).all()],
            "productos": [{"id": record.id, "nombre": record.nombre} for record in db.scalars(select(Producto).where(Producto.empresa_id == context.empresa_id).limit(1000)).all()],
            "formatos": ["html", "pdf", "xlsx"]}


@router.post("/reportes-ia/generar")
def generate(payload: ReportRequest, response: Response, request: Request, context: TenantContext = Depends(require_permission("reportes.ia.consultar")),
             db: Session = Depends(get_db), interpreter: Interpreter = Depends(get_interpreter)):
    response.headers["Cache-Control"] = "no-store"
    active_plan(db, context, professional=True)
    scope(db, context, payload.filtros)  # Rechazar filtros ajenos antes de llamar al proveedor.
    if not payload.consulta.strip():
        raise HTTPException(422, "Escribe una consulta válida.")
    interpretation = interpreter.interpret(payload.consulta, date.today())
    if interpretation.tipo in {"aclaracion", "no_admitido"}:
        return {"estado": interpretation.tipo, "mensaje": "Aclara el tipo de reporte, el período o los filtros." if interpretation.tipo == "aclaracion" else "Ese reporte no está admitido. Puedes consultar ventas diarias, prendas vendidas, inventario o abastecimiento."}
    context = fresh_context(db, context, "reportes.ia.consultar")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=request.headers.get("Authorization", "").partition(" ")[2])
    get_current_session(request=request, credentials=credentials, db=db)
    active_plan(db, context, professional=True)
    filters = resolve_names(db, context, payload.filtros, interpretation)
    return {"estado": "generado", "reporte": build_report(db, context, interpretation.tipo, filters)}


@router.post("/reportes-ia/exportar")
def export(payload: ExportRequest, context: TenantContext = Depends(require_permission("reportes.ia.consultar")), db: Session = Depends(get_db)):
    active_plan(db, context, professional=True)
    report = build_report(db, context, payload.tipo, payload.filtros)
    content, media_type = export_report(report, payload.formato)
    return Response(content, media_type=media_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="vestinova-{payload.tipo}.{payload.formato}"'})


@router.post("/dashboard-predictivo")
def predictive_dashboard(payload: DashboardRequest, response: Response, context: TenantContext = Depends(require_permission("analitica.consultar")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if not context.administrador_empresa:
        raise HTTPException(403, "El dashboard predictivo requiere el perfil Administrador de empresa.")
    active_plan(db, context)
    return dashboard(db, context, payload.filtros, payload.analisis)
