from copy import deepcopy
from io import BytesIO

from openpyxl import load_workbook
from pypdf import PdfReader
import pytest

from app.analitica_ia.exports import cell_value, export_report


@pytest.fixture
def inventory_report():
    return {"tipo": "inventario", "titulo": "Existencias actuales", "empresa": {"id": 1, "nombre": "Empresa de prueba"},
        "generado_en": "2026-11-08T01:24:32.942338+00:00", "filtros": {"desde": None, "hasta": None, "sucursal_id": None, "categoria_id": None, "producto_id": None},
        "filtros_etiquetas": {}, "columnas": ["sucursal", "producto", "talla", "color", "fisico", "comprometido", "disponible", "registrada"],
        "filas": [{"sucursal": "Centro", "producto": "Camisa de lino", "talla": "M", "color": "Verde", "fisico": 12, "comprometido": 2, "disponible": 10, "registrada": True}],
        "total_filas": 1, "truncado": False, "totales": {"fisico": 12, "comprometido": 2, "disponible": 10},
        "notas": ["Texto técnico: registrada=false; no se inventan unidades."]}


def pdf_text(content):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


@pytest.mark.parametrize("format", ["pdf", "html", "xlsx"])
def test_exports_present_business_labels_without_raw_json_or_nulls(inventory_report, format):
    content, _ = export_report(inventory_report, format)
    if format == "pdf":
        text = pdf_text(content)
    elif format == "html":
        text = content.decode("utf-8")
    else:
        workbook = load_workbook(BytesIO(content))
        text = " ".join(str(cell.value) for sheet in workbook for row in sheet for cell in row if cell.value is not None)
    assert "VestiNova" in text and "Empresa de prueba" in text
    assert "Sucursales: todas las autorizadas" in text
    assert "07/11/2026, 21:24 (Bolivia)" in text
    assert "Camisa de lino" in text
    for technical in ('"desde"', 'null', 'sucursal_id', 'registrada', 'True', 'no se inventan', 'consultan nuevamente', '2026-11-08T'):
        assert technical not in text


def test_spoken_filters_are_exported_with_scoped_names_and_readable_dates(inventory_report):
    inventory_report.update(tipo="prendas_vendidas", titulo="Prendas vendidas", columnas=["producto", "unidades", "importe_bob"],
        filas=[{"producto": "Camisa de lino", "unidades": 2, "importe_bob": "1234.50"}], totales={"unidades": 2, "importe_bruto_bob": "1234.50"})
    inventory_report["filtros"] = {"desde": "2026-11-01", "hasta": "2026-11-07", "sucursal_id": 98765, "categoria_id": 98766, "producto_id": 98767}
    inventory_report["filtros_etiquetas"] = {"sucursal": "Centro", "categoria": "Camisas", "producto": "Camisa de lino"}
    text = pdf_text(export_report(inventory_report, "pdf")[0])
    assert "Sucursal: Centro" in text and "Categoría: Camisas" in text and "Prenda: Camisa de lino" in text
    assert "01/11/2026 - 07/11/2026" in text and "1.234,50" in text
    assert "98765" not in text and "null" not in text
    assert "sin descontar devoluciones" in text  # Conserva el significado comercial del importe.


def test_unknown_stock_is_not_exported_as_confirmed_zero(inventory_report):
    known = inventory_report["filas"][0]
    known.update(fisico=0, comprometido=0, disponible=0)
    unknown = {**known, "producto": "Prenda sin saldo", "registrada": False}
    inventory_report["filas"].append(unknown)
    inventory_report["total_filas"] = 2
    inventory_report["totales"] = {key: 0 for key in ("fisico", "comprometido", "disponible")}
    assert cell_value(inventory_report, known, "fisico") == 0
    assert cell_value(inventory_report, unknown, "fisico") == "Sin registro"
    text = pdf_text(export_report(inventory_report, "pdf")[0])
    assert "Sin registro" in text and "únicamente existencias registradas" in text
    assert "False" not in text and "registrada=false" not in text


def test_xlsx_treats_names_as_text_and_currency_as_numbers(inventory_report):
    inventory_report["filas"][0]["producto"] = '=HYPERLINK("https://example.test")'
    workbook = load_workbook(BytesIO(export_report(inventory_report, "xlsx")[0]))
    cells = [cell for row in workbook.active for cell in row if cell.value == inventory_report["filas"][0]["producto"]]
    assert len(cells) == 1 and cells[0].data_type == "s"
    inventory_report["totales"] = {"importe_bruto_bob": "1234.50"}
    workbook = load_workbook(BytesIO(export_report(inventory_report, "xlsx")[0]))
    value = workbook["Totales"].cell(2, 2)
    assert value.value == 1234.5 and value.data_type == "n" and value.number_format == '#,##0.00'


def test_empty_and_truncated_reports_keep_material_information(inventory_report):
    inventory_report["filas"] = []
    assert "No se encontraron registros" in pdf_text(export_report(inventory_report, "pdf")[0])
    inventory_report.update(truncado=True, total_filas=350)
    assert "Se muestran 0 de 350 resultados" in pdf_text(export_report(inventory_report, "pdf")[0])


def test_long_pdf_repeats_headers_and_pages_without_mutating_source(inventory_report):
    inventory_report["filas"] = [{**inventory_report["filas"][0], "producto": f"Prenda de prueba {index}"} for index in range(70)]
    inventory_report["total_filas"] = 70
    inventory_report["totales"] = {key: sum(row[key] for row in inventory_report["filas"]) for key in ("fisico", "comprometido", "disponible")}
    before = deepcopy(inventory_report)
    reader = PdfReader(BytesIO(export_report(inventory_report, "pdf")[0]))
    assert len(reader.pages) > 1
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        assert "Sucursal" in text and "Prenda" in text and f"Página {number}" in text
    assert inventory_report == before


def test_nine_short_inventory_rows_fit_one_page_without_losing_rows(inventory_report):
    inventory_report["filas"] = [{**inventory_report["filas"][0], "producto": f"Prenda {index}"} for index in range(9)]
    inventory_report["total_filas"] = 9
    reader = PdfReader(BytesIO(export_report(inventory_report, "pdf")[0]))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert all(f"Prenda {index}" in text for index in range(9))
