"""CU13: bandeja central y conciliación autorizada de ventas offline.

La conciliación documenta una decisión y evidencia: no altera stock ni afirma
que se devolvió dinero sin constancia externa. El UUID original es inmutable.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Sucursal, utc_now
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, lock_tenant_mutation, require_tenant
from app.organizacion_empresarial.audit import record_audit_event
from app.operacion_sin_conexion.caja.online import SyncIncident, _incident_response

router = APIRouter(prefix="/api/admin/conciliacion", tags=["CU13 · Conciliación"])


class ResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(DEVOLUCION_DOCUMENTADA|ENTREGA_ALTERNATIVA_DOCUMENTADA|ACUERDO_DOCUMENTADO)$")
    observacion: str = Field(min_length=15, max_length=350)
    referencia_constancia: str = Field(min_length=4, max_length=120)


def _staff(context: TenantContext) -> None:
    if context.acceso is None or context.acceso.codigo_sistema != "ENCARGADO_SUCURSAL":
        raise HTTPException(403, "La conciliación requiere un Encargado de sucursal autorizado.")


@router.get("")
def list_conflicts(
    sucursal_id: int | None = Query(default=None, gt=0),
    estado: str | None = Query(default=None, pattern="^(CONFLICTO|RESUELTO)$"),
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    if sucursal_id is None:
        branches = db.scalars(authorized_branches_statement(context).with_only_columns(Sucursal.id)).all()
    else:
        authorized_branch(db, context, sucursal_id)
        branches = [sucursal_id]
    filters = [SyncIncident.empresa_id == context.empresa_id,
               SyncIncident.sucursal_id.in_(branches)]
    if estado is not None:
        filters.append(SyncIncident.estado == estado)
    rows = db.scalars(select(SyncIncident).where(*filters).order_by(
        SyncIncident.creada_en.desc()).limit(100)).all()
    return [_incident_response(row) for row in rows]


@router.get("/{incident_id}")
def detail_conflict(
    incident_id: UUID,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    row = db.scalar(select(SyncIncident).where(
        SyncIncident.id == str(incident_id), SyncIncident.empresa_id == context.empresa_id))
    if row is None:
        raise HTTPException(404, "Conflicto no encontrado.")
    authorized_branch(db, context, row.sucursal_id)
    return {**_incident_response(row), "datos_originales": row.datos_originales}


@router.post("/{incident_id}/resolver")
def resolve_conflict(
    incident_id: UUID, payload: ResolveInput,
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    _staff(context)
    context = lock_tenant_mutation(db, context)
    row = db.scalar(select(SyncIncident).where(
        SyncIncident.id == str(incident_id), SyncIncident.empresa_id == context.empresa_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Conflicto no encontrado.")
    authorized_branch(db, context, row.sucursal_id)
    if row.estado == "RESUELTO":
        if row.decision == payload.decision and row.observacion == (
            f"{payload.referencia_constancia}: {payload.observacion}"
        ):
            return _incident_response(row)
        raise HTTPException(409, "Este conflicto ya tiene una resolución documentada.")
    row.estado = "RESUELTO"
    row.decision = payload.decision
    row.observacion = f"{payload.referencia_constancia}: {payload.observacion}"
    row.responsable_id = context.usuario.id
    row.resuelta_en = utc_now()
    record_audit_event(db, context, accion="sincronizacion.conflicto_resuelto",
                       entidad="conflicto", entidad_id=row.id,
                       detalles={"tipo": row.tipo, "operacion_id": row.operacion_id,
                                 "sucursal_id": row.sucursal_id, "decision": payload.decision,
                                 "referencia_constancia": payload.referencia_constancia})
    db.commit()
    return _incident_response(row)
