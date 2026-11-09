"""No recibe cámara, medidas corporales ni escrituras de stock."""
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.image_url import validate_image_url
from app.models import Empresa, PlanSaaS, Producto, SuscripcionEmpresa, VarianteProducto, utc_now
from app.organizacion_empresarial.audit import record_audit_event
from app.organizacion_empresarial.plans import subscription_state
from app.security import get_current_session
from app.tenancy import TenantContext, check_permission, lock_tenant_mutation, require_permission
from app.vestidor_virtual.models import ConfiguracionVestidor
from app.vestidor_virtual.anchors import GarmentAnchors
from app.vestidor_virtual.resources import MAX_BYTES, resource_path, store_png, uploaded_reference, validate_png

router = APIRouter(tags=["CU18 · Vestidor virtual"])
ASSETS = {name: Path(__file__).parent / "assets" / name for name in
          ("polera-gris.png", "polera-azul.png", "camisa-azul.png", "camisa-blanca.png")}
ASSET_PREFIX = "/api/vestidor/recursos/"


class VestidorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    recurso_url: str = Field(min_length=1, max_length=2048)
    tipo_prenda: Literal["POLERA", "CAMISA"]
    factor_ancho: float = Field(default=1.9, ge=.5, le=2.5)
    factor_alto: float = Field(default=1.2, ge=.5, le=2.5)
    offset_x: float = Field(default=0, ge=-.5, le=.5)
    offset_y: float = Field(default=0, ge=-.5, le=.5)
    activo: bool = True
    anclajes: GarmentAnchors | None = None

    @field_validator("recurso_url")
    @classmethod
    def png_url(cls, value):
        if value in {ASSET_PREFIX + name for name in ASSETS} or uploaded_reference(value):
            return value
        validate_image_url(value)
        parsed = urlsplit(value)
        if parsed.fragment or not parsed.path.lower().endswith(".png"):
            raise ValueError("Utiliza una URL de PNG transparente, sin fragmento. La foto del catálogo no se usa automáticamente.")
        return value


def config_response(row):
    return {**VestidorConfig.model_validate({key: getattr(row,key) for key in VestidorConfig.model_fields}).model_dump(),
            "zona": "TORSO", "demostracion": row.recurso_url in {ASSET_PREFIX + name for name in ASSETS},
            "actualizado_en": row.actualizado_en.isoformat()}


def admin_variant(db, context, product_id, variant_id):
    variant = db.scalar(select(VarianteProducto).where(VarianteProducto.id == variant_id,
        VarianteProducto.empresa_id == context.empresa_id, VarianteProducto.producto_id == product_id))
    if variant is None:
        raise HTTPException(404, "Prenda o variante no disponible para esta empresa.")
    return variant


@router.get("/api/admin/productos/{producto_id}/variantes/{variante_id}/vestidor")
def admin_get(producto_id: int, variante_id: int, db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.consultar"))):
    admin_variant(db, context, producto_id, variante_id)
    row = db.get(ConfiguracionVestidor, variante_id)
    return {"variante_id": variante_id, "configuracion": config_response(row) if row else None}


@router.put("/api/admin/productos/{producto_id}/variantes/{variante_id}/vestidor")
def admin_put(producto_id: int, variante_id: int, payload: VestidorConfig, db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True))):
    variant = admin_variant(db, context, producto_id, variante_id)
    reference = uploaded_reference(payload.recurso_url)
    if reference:
        if reference[0] != context.empresa_id:
            raise HTTPException(404, "Recurso no disponible en esta empresa.")
        if not resource_path(*reference).is_file():
            raise HTTPException(422, "Primero carga el PNG de esta prenda desde sus variantes.")
    row = db.get(ConfiguracionVestidor, variant.id)
    same_resource = row is not None and row.recurso_url == payload.recurso_url
    if row is None:
        row = ConfiguracionVestidor(variante_id=variant.id, empresa_id=context.empresa_id)
        db.add(row)
    for name,value in payload.model_dump().items():
        # Clientes anteriores no conocen el campo. Conservar solo si es la misma foto;
        # cambiar la foto requiere recalibrar y null explícito permite desactivarlo.
        if name == "anclajes" and name not in payload.model_fields_set and same_resource:
            continue
        setattr(row,name,value)
    row.actualizado_en = utc_now()
    record_audit_event(db, context, accion="vestidor.configurado", entidad="variante", entidad_id=variant.id,
                       detalles={"producto_id": producto_id, "tipo_prenda": payload.tipo_prenda, "activo": payload.activo})
    db.commit()
    return {"variante_id": variant.id, "configuracion": config_response(row)}


@router.put("/api/admin/productos/{producto_id}/variantes/{variante_id}/vestidor/recurso")
async def upload_resource(producto_id: int, variante_id: int, request: Request, response: Response,
                          db: Session = Depends(get_db), context: TenantContext = Depends(require_permission("catalogo.gestionar"))):
    admin_variant(db, context, producto_id, variante_id)
    if request.headers.get("content-type", "").partition(";")[0].lower() != "image/png":
        raise HTTPException(415, "Selecciona un archivo PNG con fondo transparente.")
    chunks, length = [], 0
    async for chunk in request.stream():
        length += len(chunk)
        if length > MAX_BYTES:
            raise HTTPException(413, "La imagen puede ocupar como máximo 6 MiB.")
        chunks.append(chunk)
    data = b"".join(chunks)
    validate_png(data)
    # El cliente pudo tardar en subirlo: revalidar permisos después de la espera.
    db.expire_all()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=request.headers.get("Authorization", "").partition(" ")[2])
    get_current_session(request=request, credentials=credentials, db=db)
    context = lock_tenant_mutation(db, context)
    check_permission(context, "catalogo.gestionar")
    admin_variant(db, context, producto_id, variante_id)
    url = store_png(context.empresa_id, data)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"recurso_url": url, "publicado": False}


@router.get("/api/catalogo/productos/{slug}/vestidor")
def public_configuration(slug: str, response: Response, tienda: str = Query(min_length=1, max_length=100),
                         variante_id: int | None = Query(default=None, gt=0), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    pair = db.execute(select(Empresa, SuscripcionEmpresa).join(SuscripcionEmpresa, SuscripcionEmpresa.empresa_id == Empresa.id)
        .join(PlanSaaS, PlanSaaS.id == SuscripcionEmpresa.plan_id)
        .where(Empresa.slug == tienda, Empresa.activo.is_(True), PlanSaaS.activo.is_(True))).first()
    if pair is None or subscription_state(pair[1]) != "ACTIVA":
        raise HTTPException(404,"Tienda no disponible.")
    company = pair[0]
    product = db.scalar(select(Producto).where(Producto.slug == slug, Producto.empresa_id == company.id, Producto.activo.is_(True)))
    if product is None:
        raise HTTPException(404,"Prenda no disponible en esta tienda.")
    rows = db.execute(select(VarianteProducto, ConfiguracionVestidor).outerjoin(ConfiguracionVestidor,
        (ConfiguracionVestidor.variante_id == VarianteProducto.id) & (ConfiguracionVestidor.empresa_id == company.id))
        .where(VarianteProducto.empresa_id == company.id, VarianteProducto.producto_id == product.id,
               VarianteProducto.activo.is_(True), *([VarianteProducto.id == variante_id] if variante_id else []))
        .order_by(VarianteProducto.talla, VarianteProducto.color)).all()
    if variante_id and not rows:
        raise HTTPException(404,"Variante no disponible en esta prenda.")
    variants = [{"variante_id": variant.id, "talla": variant.talla, "color": variant.color,
                 "compatible": config is not None and config.activo,
                 "configuracion": config_response(config) if config is not None and config.activo else None} for variant, config in rows]
    alternatives = db.execute(select(Producto.slug, Producto.nombre).join(VarianteProducto,
        (VarianteProducto.producto_id == Producto.id) & (VarianteProducto.empresa_id == company.id))
        .join(ConfiguracionVestidor,(ConfiguracionVestidor.variante_id == VarianteProducto.id) & (ConfiguracionVestidor.empresa_id == company.id))
        .where(Producto.empresa_id == company.id, Producto.activo.is_(True), Producto.id != product.id,
               VarianteProducto.activo.is_(True), ConfiguracionVestidor.activo.is_(True)).distinct().order_by(Producto.nombre).limit(5)).all()
    compatible = any(row["compatible"] for row in variants)
    return {"tienda": company.slug, "producto_id": product.id, "compatible": compatible,
            "motivo": None if compatible else "Esta prenda todavía no tiene un recurso preparado para el vestidor virtual.",
            "variantes": variants, "alternativas": [{"slug": slug, "nombre": name} for slug,name in alternatives],
            "aviso": "Visualización orientativa. No garantiza talla ni ajuste físico y no reserva existencias."}


@router.get("/api/vestidor/recursos/{nombre}", include_in_schema=False)
def demo_asset(nombre: str):
    path = ASSETS.get(nombre)
    if path is None or not path.is_file():
        raise HTTPException(404,"Recurso no disponible.")
    return FileResponse(path,media_type="image/png",headers={"Cache-Control":"public, max-age=86400"})


@router.get("/api/vestidor/recursos/empresas/{empresa_id}/{nombre}", include_in_schema=False)
def published_resource(empresa_id: int, nombre: str, db: Session = Depends(get_db)):
    url = f"/api/vestidor/recursos/empresas/{empresa_id}/{nombre}"
    reference = uploaded_reference(url)
    if reference is None:
        raise HTTPException(404, "Recurso no disponible.")
    pair = db.execute(select(ConfiguracionVestidor, SuscripcionEmpresa)
        .join(VarianteProducto, (VarianteProducto.id == ConfiguracionVestidor.variante_id)
              & (VarianteProducto.empresa_id == ConfiguracionVestidor.empresa_id))
        .join(Producto, (Producto.id == VarianteProducto.producto_id) & (Producto.empresa_id == VarianteProducto.empresa_id))
        .join(Empresa, Empresa.id == Producto.empresa_id)
        .join(SuscripcionEmpresa, SuscripcionEmpresa.empresa_id == Empresa.id)
        .join(PlanSaaS, PlanSaaS.id == SuscripcionEmpresa.plan_id)
        .where(ConfiguracionVestidor.empresa_id == empresa_id, ConfiguracionVestidor.recurso_url == url,
               ConfiguracionVestidor.activo.is_(True), VarianteProducto.activo.is_(True), Producto.activo.is_(True),
               Empresa.activo.is_(True), PlanSaaS.activo.is_(True))).first()
    path = resource_path(*reference)
    if pair is None or subscription_state(pair[1]) != "ACTIVA" or not path.is_file():
        raise HTTPException(404, "Recurso no disponible.")
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=86400"})
