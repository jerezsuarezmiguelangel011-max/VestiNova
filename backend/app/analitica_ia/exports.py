"""Presentación de reportes; conserva los valores y el ámbito de la API."""
from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

LABELS = {
    "fecha": "Fecha", "operaciones": "Compras", "unidades": "Unidades",
    "importe_bob": "Importe (BOB)", "sucursal": "Sucursal", "producto": "Prenda",
    "talla": "Talla", "color": "Color", "fisico": "Stock físico",
    "comprometido": "Comprometido", "disponible": "Disponible",
    "proveedor": "Proveedor", "estado": "Estado", "ordenes": "Órdenes",
    "solicitadas": "Solicitadas", "recibidas": "Recibidas", "costo_recibido_bob": "Costo recibido (BOB)",
    "operaciones_aceptadas": "Ventas confirmadas", "importe_bruto_bob": "Importe bruto (BOB)",
    "intentos_pago_pendientes": "Pagos pendientes", "unidades_recibidas": "Unidades recibidas",
}
NUMERIC = {"operaciones", "unidades", "fisico", "comprometido", "disponible", "ordenes", "solicitadas", "recibidas"}


def label(key):
    return LABELS.get(key, key.replace("_", " ").capitalize())


def money(value):
    return f"{Decimal(str(value)):,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def cell_value(report, row, key, spreadsheet=False):
    if report["tipo"] == "inventario" and row.get("registrada") is False and key in {"fisico", "comprometido", "disponible"}:
        return "Sin registro"
    value = row.get(key)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if key.endswith("_bob"):
        return Decimal(str(value)) if spreadsheet else money(value)
    if key == "fecha":
        return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
    if key == "estado":
        return str(value).replace("_", " ").capitalize()
    return value


def presentation(report):
    filters, names = report["filtros"], report.get("filtros_etiquetas", {})
    scope = ["Sucursal: " + names.get("sucursal", "seleccionada") if filters.get("sucursal_id") else "Sucursales: todas las autorizadas"]
    for key, title in (("categoria", "Categoría"), ("producto", "Prenda")):
        if filters.get(key + "_id"):
            scope.append(title + ": " + names.get(key, "seleccionada"))
    period = ""
    start, end = filters.get("desde"), filters.get("hasta")
    if start or end:
        period = "Período: " + " - ".join(date.fromisoformat(str(value)).strftime("%d/%m/%Y") for value in (start, end) if value)
        period += " (fechas UTC)"
    generated = datetime.fromisoformat(report["generado_en"])
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    emitted = "Emitido: " + generated.astimezone(ZoneInfo("America/La_Paz")).strftime("%d/%m/%Y, %H:%M") + " (Bolivia)"
    notes = []
    if report.get("origen_datos", {}).get("demostracion"):
        notes.append("Datos de demostración: este reporte incluye un historial de compras simulado.")
    if report["tipo"] == "inventario":
        if any(row.get("registrada") is False for row in report["filas"]):
            notes.append("Los totales incluyen únicamente existencias registradas.")
    elif report["tipo"] in {"ventas_diarias", "prendas_vendidas"}:
        notes.append("Importes brutos de compras digitales y caja confirmada, sin descontar devoluciones. Los pagos pendientes no se suman al importe.")
        if filters.get("producto_id") or filters.get("categoria_id"):
            notes.append("El conteo de pagos pendientes corresponde al período y las sucursales, sin filtro de prenda o categoría.")
    elif report["tipo"] == "abastecimiento":
        notes.append("Período según la creación de la orden. El costo corresponde a las unidades recibidas; no a pagos realizados.")
    if report["truncado"]:
        notes.append(f"Se muestran {len(report['filas'])} de {report['total_filas']} resultados. Los totales incluyen todos los resultados consultados.")
    return {"titulo": "Inventario por sucursal" if report["tipo"] == "inventario" else report["titulo"],
            "empresa": report["empresa"]["nombre"], "emision": emitted, "alcance": " | ".join(scope),
            "periodo": period, "notas": notes, "columnas": [key for key in report["columnas"] if key != "registrada"]}


def export_report(report, formato):
    view = presentation(report)
    if formato == "html":
        return export_html(report, view), "text/html; charset=utf-8"
    if formato == "xlsx":
        return export_xlsx(report, view), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return export_pdf(report, view), "application/pdf"


def export_html(report, view):
    columns = view["columnas"]
    head = "".join("<th scope='col'>" + escape(label(key)) + "</th>" for key in columns)
    body = "".join("<tr>" + "".join("<td>" + escape(str(cell_value(report, row, key))) + "</td>" for key in columns) + "</tr>" for row in report["filas"])
    totals = "".join("<div><dt>" + escape(label(key)) + "</dt><dd>" + escape(money(value) if key.endswith("_bob") else str(value)) + "</dd></div>" for key, value in report["totales"].items())
    notes = "".join("<p class='note'>" + escape(note) + "</p>" for note in view["notas"])
    table = f"<div class='table'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>" if report["filas"] else "<p>No se encontraron registros para los criterios consultados.</p>"
    return ("<!doctype html><html lang='es'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(view['titulo'])} - {escape(view['empresa'])}</title>"
        "<style>body{font:14px/1.5 Arial,sans-serif;background:#f6f4ec;color:#202c27;margin:0;border-top:6px solid #12644e}main{max-width:1100px;margin:auto;padding:36px}header{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}.brand{font:28px Georgia,serif;color:#12644e}h1{font:30px Georgia,serif}p{overflow-wrap:anywhere}.meta,.note,footer{color:#52665c}.metrics{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}.metrics div{background:#edf2e9;border:1px solid #d8e0d4;padding:16px;min-width:130px}.metrics dd{font:26px Georgia,serif;color:#12644e;margin:8px 0 0}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;text-align:left;border-bottom:1px solid #d8e0d4}th{background:#12644e;color:white}tbody tr:nth-child(even){background:#f4f6ef}.note{font-size:12px}footer{margin-top:24px;border-top:1px solid #d8e0d4;padding-top:12px;font-size:12px}</style>"
        f"<main><header><strong class='brand'>VestiNova</strong><span class='meta'>{escape(view['emision'])}</span></header><h1>{escape(view['titulo'])}</h1><p>{escape(view['empresa'])}</p><p class='meta'>{escape(view['alcance'])}</p>"
        + (f"<p class='meta'>{escape(view['periodo'])}</p>" if view["periodo"] else "")
        + f"<dl class='metrics'>{totals}</dl>{table}{notes}<footer>VestiNova | Reporte de gestión</footer></main></html>").encode("utf-8")


def export_xlsx(report, view):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reporte"

    def append(target, values):
        target.append(values)
        for cell in target[target.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # Ningún nombre se interpreta como fórmula.
            elif isinstance(cell.value, Decimal):
                cell.number_format = '#,##0.00'

    metadata = ["VestiNova | " + view["titulo"], view["empresa"], view["emision"], view["alcance"]]
    if view["periodo"]:
        metadata.append(view["periodo"])
    for index, text in enumerate(metadata, 1):
        append(sheet, [text])
        sheet.merge_cells(start_row=index, start_column=1, end_row=index, end_column=len(view["columnas"]))
        sheet.cell(index, 1).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[index].height = 30 if index == 1 else 28
    sheet.cell(1, 1).font = Font(size=18, color="12644E", bold=True)
    append(sheet, [])
    append(sheet, [label(key) for key in view["columnas"]])
    header = sheet.max_row
    for row in report["filas"]:
        append(sheet, [cell_value(report, row, key, spreadsheet=True) for key in view["columnas"]])
    if not report["filas"]:
        append(sheet, ["No se encontraron registros para los criterios consultados."])
    sheet.freeze_panes = f"A{header+1}"
    sheet.auto_filter.ref = f"A{header}:{get_column_letter(len(view['columnas']))}{sheet.max_row}"
    for cell in sheet[header]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12644E")
    for index in range(1, len(view["columnas"]) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 26
    summary = workbook.create_sheet("Totales")
    append(summary, ["Indicador", "Valor"])
    for key, value in report["totales"].items():
        append(summary, [label(key), Decimal(str(value)) if key.endswith("_bob") else value])
    summary.column_dimensions["A"].width = 38
    summary.column_dimensions["B"].width = 24
    for note in view["notas"]:
        append(summary, [note])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def export_pdf(report, view):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    output = BytesIO()
    width, height = landscape(A4)
    margin, green, line = 36, colors.HexColor("#12644e"), colors.HexColor("#d8e0d4")
    available = width - 2*margin - 12  # Padding interior del marco de Platypus.
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#202c27"))
    muted = ParagraphStyle("meta", parent=body, fontSize=9, textColor=colors.HexColor("#52665c"))
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    heading = ParagraphStyle("heading", parent=body, fontName="Times-Bold", fontSize=23, leading=28, spaceAfter=6)
    brand = ParagraphStyle("brand", parent=heading, fontSize=22, textColor=green)
    th = ParagraphStyle("th", parent=body, fontName="Helvetica-Bold", textColor=colors.white)
    number = ParagraphStyle("number", parent=body, fontName="Times-Roman", fontSize=21, leading=26, textColor=green)
    note_style = ParagraphStyle("note", parent=muted, fontSize=8, leading=11, spaceBefore=6)
    document = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=margin, rightMargin=margin,
        topMargin=28, bottomMargin=42, title=view["titulo"], author="VestiNova")
    def p(text, style=body):
        return Paragraph(escape(str(text)), style)
    story = [p("VestiNova", brand), Spacer(1, 6), p(view["titulo"], heading), p(view["empresa"], body), Spacer(1, 9),
             p(view["emision"], muted), p(view["alcance"], muted)]
    if view["periodo"]:
        story.append(p(view["periodo"], muted))
    story.append(HRFlowable(width="100%", thickness=1, color=green, spaceBefore=10, spaceAfter=14))
    metrics = [[p(label(key), muted), p(money(value) if key.endswith("_bob") else value, number)] for key, value in report["totales"].items()]
    if metrics:
        summary = Table([metrics], colWidths=[available/len(metrics)]*len(metrics))
        summary.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#edf2e9")),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 12),
            ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 9)]))
        story.extend([summary, Spacer(1, 18)])
    columns = view["columnas"]
    if report["filas"]:
        weights = {"sucursal":1.5, "producto":2.3, "talla":.5, "color":.8, "comprometido":1.05, "proveedor":2, "estado":1.2}
        sizes = [weights.get(key, 1) for key in columns]
        data = [[p(label(key), th) for key in columns]]
        data.extend([[p(cell_value(report, row, key), right if key in NUMERIC or key.endswith("_bob") else body) for key in columns] for row in report["filas"]])
        table = Table(data, colWidths=[available*size/sum(sizes) for size in sizes], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), green), ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f6f0")]),
            ("LINEBELOW", (0,0), (-1,-1), .3, line), ("TOPPADDING", (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7), ("LEFTPADDING", (0,0), (-1,-1), 9), ("RIGHTPADDING", (0,0), (-1,-1), 9)]))
        story.append(table)
    else:
        story.append(p("No se encontraron registros para los criterios consultados."))
    story.extend(p(note, note_style) for note in view["notas"])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(green)
        canvas.rect(0, height-5, width, 5, fill=1, stroke=0)
        canvas.setStrokeColor(line)
        canvas.line(margin, 30, width-margin, 30)
        canvas.setFillColor(colors.HexColor("#52665c"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(margin, 17, "VestiNova | Reporte de gestión")
        canvas.drawRightString(width-margin, 17, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
