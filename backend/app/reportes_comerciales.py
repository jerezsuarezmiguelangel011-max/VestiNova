"""CU20: reportes comerciales de operaciones centrales aceptadas.

No incluye ventas provisionales solo presentes en IndexedDB/SQLite.
Las existencias representan un corte actual, no un saldo histórico.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.autenticacion_usuarios.permissions import effective_role
from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseRecord
from app.compras_reservas.reservas.online import ReservationRecord
from app.db import get_db
from app.models import Existencia, Sucursal
from app.operacion_sin_conexion.caja.online import CashSale
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, check_permission, require_tenant

router = APIRouter(prefix="/api/admin/reportes-comerciales",
                   tags=["CU20 · Reportes comerciales"])


def _date_range(start: date | None, end: date | None) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(timezone.utc).date()
    finish = end or today
    begin = start or finish - timedelta(days=29)
    if begin > finish or (finish - begin).days > 366:
        raise HTTPException(422, "El período debe ser válido y no superar 367 días.")
    return (begin, finish,
            datetime.combine(begin, time.min, tzinfo=timezone.utc),
            datetime.combine(finish + timedelta(days=1), time.min, tzinfo=timezone.utc))


@router.get("")
def reports(
    response: Response,
    tipo: str = Query(default="resumen", pattern="^(resumen|ventas|reservas|inventario)$"),
    desde: date | None = None,
    hasta: date | None = None,
    sucursal_id: int | None = Query(default=None, gt=0),
    context: TenantContext = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    if context.acceso is None or context.acceso.codigo_sistema not in {"ADMINISTRADOR", "ENCARGADO_SUCURSAL"}:
        raise HTTPException(403, "Solo Administrador o Encargado pueden consultar reportes.")
    check_permission(context, "reportes.consultar")
    begin, finish, start_dt, end_dt = _date_range(desde, hasta)
    if sucursal_id is not None:
        authorized_branch(db, context, sucursal_id)
        branches = [db.get(Sucursal, sucursal_id)]
    else:
        branches = db.scalars(authorized_branches_statement(context).order_by(Sucursal.id)).all()
    branch_ids = [row.id for row in branches]
    result = {
        "tipo": tipo,
        "desde": begin.isoformat(),
        "hasta": finish.isoformat(),
        "zona_horaria": "UTC",
        "nota": "Solo datos centrales confirmados. Ventas locales pendientes no incluidas. Inventario es un corte actual.",
        "por_sucursal": [],
        "totales": {
            "ventas_confirmadas": 0, "ingresos_confirmados": "0.00",
            "ventas_digitales": 0, "ventas_efectivo": 0,
            "reservas_confirmadas": 0, "reservas_atendidas": 0,
            "reservas_canceladas": 0, "reservas_vencidas": 0,
            "stock_fisico_actual": 0, "stock_comprometido_actual": 0,
            "stock_disponible_actual": 0,
        },
    }
    aggregates = {row.id: {
        "sucursal_id": row.id, "sucursal": row.nombre,
        "ventas_confirmadas": 0, "ingresos_confirmados": "0.00",
        "ventas_digitales": 0, "ventas_efectivo": 0,
        "reservas_confirmadas": 0, "reservas_atendidas": 0,
        "reservas_canceladas": 0, "reservas_vencidas": 0,
        "stock_fisico_actual": 0, "stock_comprometido_actual": 0,
        "stock_disponible_actual": 0,
    } for row in branches}
    if not branch_ids:
        return result

    if tipo in {"resumen", "ventas"}:
        # Solo PurchaseRecord asentadas: una sesión Stripe pendiente o incidencia
        # financiera no se trata como compra digital confirmada.
        digital = db.execute(select(
            PurchaseRecord.sucursal_clave, func.count(), func.sum(PurchaseRecord.total)
        ).where(
            PurchaseRecord.empresa_clave == identifier_token(context.empresa_id),
            PurchaseRecord.sucursal_clave.in_([identifier_token(branch_id) for branch_id in branch_ids]),
            PurchaseRecord.creado_en >= start_dt,
            PurchaseRecord.creado_en < end_dt,
        ).group_by(PurchaseRecord.sucursal_clave)).all()
        for token, count, amount in digital:
            for branch_id in branch_ids:
                if identifier_token(branch_id) == token:
                    aggregates[branch_id]["ventas_digitales"] = int(count)
                    aggregates[branch_id]["ventas_confirmadas"] += int(count)
                    aggregates[branch_id]["ingresos_confirmados"] = f"{Decimal(str(amount or 0)):.2f}"
                    break
        cash = db.execute(select(
            CashSale.sucursal_id, func.count(), func.sum(CashSale.total)
        ).where(
            CashSale.empresa_id == context.empresa_id,
            CashSale.sucursal_id.in_(branch_ids),
            CashSale.confirmada_en >= start_dt,
            CashSale.confirmada_en < end_dt,
        ).group_by(CashSale.sucursal_id)).all()
        for branch_id, count, amount in cash:
            row = aggregates[branch_id]
            row["ventas_efectivo"] = int(count)
            row["ventas_confirmadas"] += int(count)
            row["ingresos_confirmados"] = f"{Decimal(row['ingresos_confirmados']) + Decimal(str(amount or 0)):.2f}"

    if tipo in {"resumen", "reservas"}:
        reservations = db.execute(select(
            ReservationRecord.sucursal_id, ReservationRecord.estado, func.count()
        ).where(
            ReservationRecord.empresa_id == context.empresa_id,
            ReservationRecord.sucursal_id.in_(branch_ids),
            ReservationRecord.creada_en >= start_dt,
            ReservationRecord.creada_en < end_dt,
        ).group_by(ReservationRecord.sucursal_id, ReservationRecord.estado)).all()
        state_keys = {
            "CONFIRMADA": "reservas_confirmadas",
            "ATENDIDA": "reservas_atendidas",
            "CANCELADA": "reservas_canceladas",
            "VENCIDA": "reservas_vencidas",
        }
        for branch_id, state, count in reservations:
            key = state_keys.get(state)
            if key:
                aggregates[branch_id][key] += int(count)

    if tipo in {"resumen", "inventario"}:
        balances = db.execute(select(
            Existencia.sucursal_id,
            func.sum(Existencia.cantidad),
            func.sum(Existencia.cantidad_comprometida),
        ).where(
            Existencia.empresa_id == context.empresa_id,
            Existencia.sucursal_id.in_(branch_ids),
        ).group_by(Existencia.sucursal_id)).all()
        for branch_id, physical, committed in balances:
            row = aggregates[branch_id]
            row["stock_fisico_actual"] = int(physical or 0)
            row["stock_comprometido_actual"] = int(committed or 0)
            row["stock_disponible_actual"] = int(physical or 0) - int(committed or 0)

    result["por_sucursal"] = list(aggregates.values())
    totals = result["totales"]
    for row in result["por_sucursal"]:
        for key in totals:
            if key == "ingresos_confirmados":
                totals[key] = f"{Decimal(totals[key]) + Decimal(row[key]):.2f}"
            else:
                totals[key] += row[key]
    return result
