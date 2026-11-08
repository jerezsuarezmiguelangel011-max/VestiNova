"""CU20: reportes comerciales de operaciones centrales aceptadas.

No incluye ventas provisionales solo presentes en IndexedDB/SQLite.
Las existencias representan un corte actual, no un saldo histórico.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseRecord
from app.compras_reservas.reservas.online import ReservationRecord
from app.db import get_db
from app.models import Existencia, Sucursal, VarianteProducto
from app.organizacion_empresarial.plans import current_subscription, subscription_state
from app.operacion_sin_conexion.caja.online import CashSale
from app.tenancy import TenantContext, authorized_branch, authorized_branches_statement, check_permission, require_tenant

router = APIRouter(prefix="/api/admin/reportes-comerciales",
                   tags=["CU20 · Reportes comerciales"])


def _date_range(start: date | None, end: date | None) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(timezone.utc).date()
    finish = end or today
    begin = start or finish - timedelta(days=29)
    if begin > finish or finish > today or (finish - begin).days > 366:
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
    subscription = current_subscription(db, context.empresa_id)
    if subscription is None or not subscription[1].activo or subscription_state(subscription[0]) != "ACTIVA":
        raise HTTPException(403, "La suscripción de esta empresa no permite consultar reportes.")
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
        "ventas_por_prenda": [],
        "totales": {
            "ventas_confirmadas": 0, "ingresos_confirmados": "0.00",
            "ventas_digitales": 0, "ventas_efectivo": 0, "ventas_demo": 0,
            "reservas_confirmadas": 0, "reservas_atendidas": 0,
            "reservas_canceladas": 0, "reservas_vencidas": 0,
            "stock_fisico_actual": 0, "stock_comprometido_actual": 0,
            "stock_disponible_actual": 0,
        },
    }
    aggregates = {row.id: {
        "sucursal_id": row.id, "sucursal": row.nombre,
        "ventas_confirmadas": 0, "ingresos_confirmados": "0.00",
        "ventas_digitales": 0, "ventas_efectivo": 0, "ventas_demo": 0,
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
        # Desglose verificable por prenda, variante y color, incluidas las
        # líneas de compras digitales asentadas y de ventas de contado.
        sales = db.scalars(select(CashSale).where(
            CashSale.empresa_id == context.empresa_id,
            CashSale.sucursal_id.in_(branch_ids),
            CashSale.confirmada_en >= start_dt,
            CashSale.confirmada_en < end_dt,
        )).all()
        purchases = db.scalars(select(PurchaseRecord).options(
            selectinload(PurchaseRecord.line_records)
        ).where(
            PurchaseRecord.empresa_clave == identifier_token(context.empresa_id),
            PurchaseRecord.sucursal_clave.in_([
                identifier_token(branch_id) for branch_id in branch_ids
            ]),
            PurchaseRecord.creado_en >= start_dt,
            PurchaseRecord.creado_en < end_dt,
        )).all()
        detail_lines = []
        for sale in sales:
            if sale.codigo.startswith("VN-DEMO-CU20-"):
                aggregates[sale.sucursal_id]["ventas_demo"] += 1
            for line in sale.lineas:
                if not isinstance(line, dict):
                    continue
                if not isinstance(line.get("variante_id"), int) or not isinstance(line.get("cantidad"), int):
                    continue
                try:
                    amount = Decimal(str(line["subtotal"]))
                except (ValueError, TypeError, ArithmeticError):
                    continue
                detail_lines.append((
                    sale.sucursal_id, line["variante_id"],
                    str(line.get("nombre") or "Prenda"),
                    line["cantidad"], amount,
                    sale.codigo.startswith("VN-DEMO-CU20-"),
                ))
        for purchase in purchases:
            try:
                branch_id = next(branch_id for branch_id in branch_ids
                                 if identifier_token(branch_id) == purchase.sucursal_clave)
            except StopIteration:
                continue
            for line in purchase.line_records:
                if type(line.variante_ref) is not int:
                    continue
                detail_lines.append((
                    branch_id, line.variante_ref, line.nombre,
                    line.cantidad, line.precio_unitario * line.cantidad, False,
                ))
        variant_ids = {entry[1] for entry in detail_lines}
        variants = {
            variant.id: variant for variant in db.scalars(select(VarianteProducto).where(
                VarianteProducto.empresa_id == context.empresa_id,
                VarianteProducto.id.in_(variant_ids),
            )).all()
        } if variant_ids else {}
        grouped = {}
        for branch_id, variant_id, name, qty, amount, synthetic in detail_lines:
            v = variants.get(variant_id)
            key = (branch_id, variant_id, name, v.talla if v else "—", v.color if v else "—", synthetic)
            if key not in grouped:
                grouped[key] = {"sucursal_id": branch_id, "producto": name,
                                "talla": key[3], "color": key[4],
                                "unidades": 0, "importe": Decimal("0.00"),
                                "es_demo": synthetic}
            grouped[key]["unidades"] += qty
            grouped[key]["importe"] += amount
        result["ventas_por_prenda"] = [
            {**entry, "importe": f"{entry['importe']:.2f}"}
            for entry in sorted(grouped.values(), key=lambda row:
                                (-row["unidades"], row["producto"], row["color"]))[:100]
        ]


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

    if result["ventas_por_prenda"] and any(row["es_demo"] for row in result["ventas_por_prenda"]):
        result["nota"] += " Los comprobantes identificados como DEMO son ficticios y no representan dinero cobrado."
    result["por_sucursal"] = list(aggregates.values())
    totals = result["totales"]
    for row in result["por_sucursal"]:
        for key in totals:
            if key == "ingresos_confirmados":
                totals[key] = f"{Decimal(totals[key]) + Decimal(row[key]):.2f}"
            else:
                totals[key] += row[key]
    return result
