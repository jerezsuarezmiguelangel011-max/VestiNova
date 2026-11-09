"""Cuatro consultas de solo lectura; ámbito decidido por el servidor, no por la IA."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (CategoriaProducto, Existencia, LineaAbastecimiento, OrdenAbastecimiento,
                        Producto, Proveedor, Sucursal, VarianteProducto, utc_now)
from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseLineRecord, PurchaseRecord
from app.tenancy import TenantContext, authorized_branches_statement
from app.analitica_ia.schemas import Filters, Interpretation
from app.analitica_ia.data_origin import DEMO_CASH_ORIGIN, purchase_origin

MAX_SOURCE = 10000
REPORTS = {
    "ventas_diarias": ("Ventas confirmadas por día", ["fecha", "operaciones", "unidades", "importe_bob"]),
    "prendas_vendidas": ("Prendas vendidas", ["producto", "unidades", "importe_bob"]),
    "inventario": ("Existencias actuales", ["sucursal", "producto", "talla", "color", "fisico", "comprometido", "disponible", "registrada"]),
    "abastecimiento": ("Abastecimiento por proveedor", ["proveedor", "estado", "ordenes", "solicitadas", "recibidas", "costo_recibido_bob"]),
}


def scope(db: Session, context: TenantContext, filters: Filters):
    branches = db.scalars(authorized_branches_statement(context)).all()
    ids = [branch.id for branch in branches]
    if filters.sucursal_id is not None:
        if filters.sucursal_id not in ids:
            raise HTTPException(404, "Sucursal no disponible en tu ámbito autorizado.")
        ids = [filters.sucursal_id]
    if filters.producto_id is not None and db.scalar(select(Producto.id).where(Producto.id == filters.producto_id, Producto.empresa_id == context.empresa_id)) is None:
        raise HTTPException(404, "Prenda no disponible en esta empresa.")
    if filters.categoria_id is not None and db.scalar(select(CategoriaProducto.id).where(CategoriaProducto.id == filters.categoria_id, CategoriaProducto.empresa_id == context.empresa_id)) is None:
        raise HTTPException(404, "Categoría no disponible en esta empresa.")
    return ids, branches


def resolve_names(db: Session, context: TenantContext, filters: Filters, plan: Interpretation) -> Filters:
    values = filters.model_dump()
    for key in ("desde", "hasta"):
        if values[key] is None:
            values[key] = getattr(plan, key)
    for model, name_key, id_key in ((Sucursal, "sucursal", "sucursal_id"), (CategoriaProducto, "categoria", "categoria_id"), (Producto, "producto", "producto_id")):
        name = getattr(plan, name_key)
        if not name:
            continue
        statement = authorized_branches_statement(context) if model is Sucursal else select(model).where(model.empresa_id == context.empresa_id)
        matches = [record.id for record in db.scalars(statement).all() if record.nombre.casefold() == name.strip().casefold()]
        if len(matches) != 1:
            raise HTTPException(422, f"No se identificó una única opción autorizada de {name_key}. Selecciónala en los filtros.")
        if values[id_key] is not None and values[id_key] != matches[0]:
            raise HTTPException(422, f"La consulta y el filtro de {name_key} no coinciden.")
        values[id_key] = matches[0]
    try:
        return Filters.model_validate(values)
    except ValueError:
        raise HTTPException(422, "Corrige las fechas y los filtros de la solicitud.") from None


def period(filters: Filters):
    end = filters.hasta or date.today()
    start = filters.desde or end - timedelta(days=29)
    if start > end or (end-start).days > 365 or end > date.today():
        raise HTTPException(422, "El período debe ser válido, no futuro y de hasta 366 días.")
    return start, end


def bounds(start, end):
    return datetime.combine(start, time.min, timezone.utc), datetime.combine(end+timedelta(days=1), time.min, timezone.utc)


def limited(db, statement):
    records = db.execute(statement.limit(MAX_SOURCE+1)).all()
    if len(records) > MAX_SOURCE:
        raise HTTPException(422, "La consulta supera 10000 registros. Reduce el período o agrega filtros.")
    return records


def accepted_sales(db, context, filters, ids, start, end):
    low, high = bounds(start, end)
    query = (select(PurchaseRecord, PurchaseLineRecord, Producto)
             .join(PurchaseLineRecord, (PurchaseLineRecord.compra_id == PurchaseRecord.id) & (PurchaseLineRecord.empresa_clave == PurchaseRecord.empresa_clave))
             .join(Producto, Producto.id == PurchaseLineRecord.producto_id)
             .where(PurchaseRecord.empresa_clave == identifier_token(context.empresa_id), Producto.empresa_id == context.empresa_id,
                    PurchaseRecord.sucursal_clave.in_([identifier_token(value) for value in ids]),
                    PurchaseRecord.creado_en >= low, PurchaseRecord.creado_en < high)
             .order_by(PurchaseRecord.creado_en, PurchaseRecord.id, PurchaseLineRecord.posicion))
    if filters.producto_id:
        query = query.where(Producto.id == filters.producto_id)
    if filters.categoria_id:
        query = query.where(Producto.categoria_id == filters.categoria_id)
    digital = limited(db, query)
    cash = accepted_cash_sales(db, context, filters, ids, low, high)
    if len(digital) + len(cash) > MAX_SOURCE:
        raise HTTPException(422, "La consulta supera 10000 registros. Reduce el período o agrega filtros.")
    return sorted([*digital, *cash], key=lambda row: (row[0].creado_en.isoformat(), row[0].id))


def accepted_cash_sales(db, context, filters, ids, low, high):
    """Adapta comprobantes CU15 confirmados al lector común de CU21/CU22.

    Usa fecha y precio del comprobante, nunca el precio actual ni la cola local.
    El prefijo del ID separa una venta de caja de una compra con el mismo UUID.
    """
    from app.operacion_sin_conexion.caja.online import CashSale

    records = limited(db, select(CashSale).where(
        CashSale.empresa_id == context.empresa_id,
        CashSale.sucursal_id.in_(ids),
        CashSale.confirmada_en >= low, CashSale.confirmada_en < high,
    ).order_by(CashSale.confirmada_en, CashSale.id))
    if sum(len(sale.lineas) for sale, in records) > MAX_SOURCE:
        raise HTTPException(422, "La consulta supera 10000 registros. Reduce el período o agrega filtros.")
    variant_ids = {line.get("variante_id") for sale, in records for line in sale.lineas
                   if type(line.get("variante_id")) is int}
    if not variant_ids:
        return []
    query = select(VarianteProducto, Producto).join(
        Producto, (Producto.id == VarianteProducto.producto_id)
        & (Producto.empresa_id == VarianteProducto.empresa_id),
    ).where(VarianteProducto.empresa_id == context.empresa_id,
            Producto.empresa_id == context.empresa_id, VarianteProducto.id.in_(variant_ids))
    if filters.producto_id:
        query = query.where(Producto.id == filters.producto_id)
    if filters.categoria_id:
        query = query.where(Producto.categoria_id == filters.categoria_id)
    products = {variant.id: product for variant, product in db.execute(query)}
    output = []
    for sale, in records:
        operation = SimpleNamespace(
            id="caja:" + sale.id, creado_en=sale.confirmada_en,
            contexto={"origen": DEMO_CASH_ORIGIN if sale.codigo.startswith("VN-DEMO-") else "VENTA_CONTADO_CENTRAL"},
        )
        for line in sale.lineas:
            product = products.get(line.get("variante_id"))
            if product is None or product.id != line.get("producto_id"):
                continue
            try:
                quantity = line["cantidad"]
                price = Decimal(str(line["precio_unitario"]))
                if type(quantity) is not int or quantity < 1 or not price.is_finite() or price <= 0:
                    raise ValueError()
            except (KeyError, ValueError, TypeError, InvalidOperation):
                raise HTTPException(503, "Hay un comprobante de caja incompatible. Revisa los datos antes de generar el reporte.") from None
            output.append((operation, SimpleNamespace(cantidad=quantity, precio_unitario=price), product))
    return output


def build_report(db, context, tipo, filters: Filters):
    ids, branches = scope(db, context, filters)
    rows, notes = [], []
    origin = None
    totals = {}
    resolved = filters
    if tipo == "inventario":
        if filters.desde or filters.hasta:
            raise HTTPException(422, "Inventario refleja existencias actuales; quita las fechas para consultarlo.")
        query = (select(Sucursal, Producto, VarianteProducto, Existencia)
                 .select_from(Sucursal).join(Producto, Producto.empresa_id == Sucursal.empresa_id)
                 .join(VarianteProducto, (VarianteProducto.producto_id == Producto.id) & (VarianteProducto.empresa_id == context.empresa_id))
                 .outerjoin(Existencia, (Existencia.empresa_id == context.empresa_id) & (Existencia.sucursal_id == Sucursal.id) & (Existencia.variante_id == VarianteProducto.id))
                 .where(Sucursal.empresa_id == context.empresa_id, Sucursal.id.in_(ids))
                 .order_by(Sucursal.id, Producto.id, VarianteProducto.id))
        if filters.producto_id:
            query = query.where(Producto.id == filters.producto_id)
        if filters.categoria_id:
            query = query.where(Producto.categoria_id == filters.categoria_id)
        for branch, product, variant, stock in limited(db, query):
            physical, committed = (stock.cantidad, stock.cantidad_comprometida) if stock else (0, 0)
            rows.append(dict(sucursal=branch.nombre, producto=product.nombre, talla=variant.talla, color=variant.color,
                             fisico=physical, comprometido=committed, disponible=physical-committed, registrada=stock is not None))
        totals = {key: sum(row[key] for row in rows) for key in ("fisico", "comprometido", "disponible")}
        notes.append("Sin registro de existencias se muestra cero conocido y registrada=false; no se inventan unidades.")
    elif tipo in {"ventas_diarias", "prendas_vendidas"}:
        start, end = period(filters)
        resolved = filters.model_copy(update={"desde": start, "hasta": end})
        groups = {}
        all_operations = set()
        sales = accepted_sales(db, context, filters, ids, start, end)
        origin = purchase_origin(row[0] for row in sales)
        for purchase, line, product in sales:
            day = purchase.creado_en.date().isoformat()
            key = day if tipo == "ventas_diarias" else product.id
            group = groups.setdefault(key, {"label": day if tipo == "ventas_diarias" else product.nombre, "unidades": 0, "importe": Decimal(0), "operaciones": set()})
            group["unidades"] += line.cantidad
            group["importe"] += line.precio_unitario * line.cantidad
            group["operaciones"].add(purchase.id)
            all_operations.add(purchase.id)
        values = sorted(groups.values(), key=lambda value: value["label"]) if tipo == "ventas_diarias" else sorted(groups.values(), key=lambda value: (-value["unidades"], value["label"]))
        for group in values:
            row = {"fecha" if tipo == "ventas_diarias" else "producto": group["label"], "unidades": group["unidades"], "importe_bob": f"{group['importe']:.2f}"}
            if tipo == "ventas_diarias":
                row["operaciones"] = len(group["operaciones"])
            rows.append(row)
        totals = {"operaciones_aceptadas": len(all_operations), "unidades": sum(row["unidades"] for row in rows),
                  "importe_bruto_bob": f"{sum((Decimal(row['importe_bob']) for row in rows), Decimal(0)):.2f}"}
        notes.append("Comprobantes centrales de compras digitales y ventas de caja confirmadas. No incluye ventas locales sin sincronizar ni descuenta devoluciones posteriores.")
        # Intentos de pago todavía no aceptados se cuentan separadamente, nunca como ingresos.
        from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt
        low, high = bounds(start, end)
        pending = limited(db, select(CheckoutAttempt.id).where(CheckoutAttempt.empresa_id == context.empresa_id,
                          CheckoutAttempt.sucursal_id.in_(ids), CheckoutAttempt.estado.in_(["PENDIENTE", "PAGO_PENDIENTE"]),
                          CheckoutAttempt.creado_en >= low, CheckoutAttempt.creado_en < high))
        totals["intentos_pago_pendientes"] = len(pending)
        notes.append("Los intentos pendientes se cuentan por período/sucursal y no por producto; no forman parte del importe aceptado.")
    elif tipo == "abastecimiento":
        start, end = period(filters)
        resolved = filters.model_copy(update={"desde": start, "hasta": end})
        low, high = bounds(start, end)
        query = (select(OrdenAbastecimiento, LineaAbastecimiento, Proveedor)
                 .join(LineaAbastecimiento, (LineaAbastecimiento.orden_id == OrdenAbastecimiento.id) & (LineaAbastecimiento.empresa_id == context.empresa_id))
                 .join(Proveedor, (Proveedor.id == OrdenAbastecimiento.proveedor_id) & (Proveedor.empresa_id == context.empresa_id))
                 .join(VarianteProducto, VarianteProducto.id == LineaAbastecimiento.variante_id).join(Producto, Producto.id == VarianteProducto.producto_id)
                 .where(OrdenAbastecimiento.empresa_id == context.empresa_id, Producto.empresa_id == context.empresa_id,
                        OrdenAbastecimiento.sucursal_id.in_(ids), OrdenAbastecimiento.creado_en >= low, OrdenAbastecimiento.creado_en < high)
                 .order_by(OrdenAbastecimiento.id, LineaAbastecimiento.id))
        if filters.producto_id:
            query = query.where(Producto.id == filters.producto_id)
        if filters.categoria_id:
            query = query.where(Producto.categoria_id == filters.categoria_id)
        groups = {}
        for order, line, vendor in limited(db, query):
            group = groups.setdefault((vendor.id, order.estado), dict(proveedor=vendor.nombre, estado=order.estado, ordenes=set(), solicitadas=0, recibidas=0, costo=Decimal(0)))
            group["ordenes"].add(order.id)
            group["solicitadas"] += line.cantidad_solicitada
            group["recibidas"] += line.cantidad_recibida
            group["costo"] += line.cantidad_recibida * line.costo_unitario
        rows = [dict(proveedor=value["proveedor"], estado=value["estado"], ordenes=len(value["ordenes"]), solicitadas=value["solicitadas"],
                     recibidas=value["recibidas"], costo_recibido_bob=f"{value['costo']:.2f}") for value in groups.values()]
        totals = {"unidades_recibidas": sum(row["recibidas"] for row in rows), "costo_recibido_bob": f"{sum((Decimal(row['costo_recibido_bob']) for row in rows), Decimal(0)):.2f}"}
        notes.append("Período por creación de la orden. Se muestran estados separados; solo las unidades recibidas aportan costo recibido. No equivale a pagos realizados.")
    else:
        raise HTTPException(422, "El tipo de reporte no está admitido.")
    labels = {}
    if origin and origin["demostracion"]:
        notes.insert(0, "Historial de demostración: esta consulta incluye compras simuladas para probar el sistema.")
    if filters.sucursal_id is not None:
        labels["sucursal"] = next(branch.nombre for branch in branches if branch.id == filters.sucursal_id)
    for key, model in (("categoria", CategoriaProducto), ("producto", Producto)):
        identifier = getattr(filters, key + "_id")
        if identifier is not None:
            labels[key] = db.scalar(select(model.nombre).where(model.empresa_id == context.empresa_id, model.id == identifier))
    return {"tipo": tipo, "titulo": REPORTS[tipo][0], "empresa": {"id": context.empresa_id, "nombre": context.empresa.nombre},
            "generado_en": utc_now().isoformat(), "filtros": resolved.model_dump(mode="json"), "filtros_etiquetas": labels, "columnas": REPORTS[tipo][1],
            "filas": rows[:200], "total_filas": len(rows), "truncado": len(rows)>200, "totales": totals,
            "notas": notes, "sin_datos": not rows, "origen": "registros_centrales", "moneda": "BOB",
            **({"origen_datos": origin} if origin is not None else {})}
