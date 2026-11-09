from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from openpyxl import load_workbook

from app.analitica_ia import analytics
from app.analitica_ia.provider import get_interpreter
from app.analitica_ia.schemas import Interpretation
from app.autenticacion_usuarios.permissions import ensure_company_roles
from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseLineRecord, PurchaseRecord
from app.models import (AccesoSucursal, Administrador, CategoriaProducto, Empresa, Existencia, MembresiaEmpresa,
                        PlanSaaS, Producto, Sucursal, SuscripcionEmpresa, VarianteProducto, utc_now)
from app.security import hash_password

PASSWORD = "Clave-solo-fixtures-2026!"


class FakeInterpreter:
    kind = "inventario"
    calls = 0
    def interpret(self, prompt, today):
        self.calls += 1
        return Interpretation(tipo=self.kind)


@pytest.fixture
def ai(client, app, administrator, auth, session_factory):
    fake = FakeInterpreter()
    app.dependency_overrides[get_interpreter] = lambda: fake
    with session_factory() as db:
        member = db.scalar(select(MembresiaEmpresa).where(MembresiaEmpresa.administrador_id == administrator.id))
        first = db.get(Empresa, member.empresa_id)
        plan = PlanSaaS(codigo="PROFESIONAL", nombre="Profesional aislado", max_sucursales=100, max_productos=100, max_usuarios=100, activo=True)
        second = Empresa(slug="analitica-otra", nombre="Otra empresa privada")
        db.add_all([plan, second]); db.flush()
        subscription = db.get(SuscripcionEmpresa, first.id)
        subscription.plan_id = plan.id
        db.add(SuscripcionEmpresa(empresa_id=second.id, plan_id=plan.id, estado="ACTIVA", inicia_en=utc_now()-timedelta(days=1)))
        branches = [Sucursal(empresa_id=first.id, codigo="UNO", nombre="Sucursal Uno"), Sucursal(empresa_id=first.id, codigo="DOS", nombre="Sucursal Dos"), Sucursal(empresa_id=second.id, codigo="OTRA", nombre="Sucursal Privada")]
        category = CategoriaProducto(empresa_id=first.id, nombre="Categoría propia", nombre_clave="categoria propia")
        other_category = CategoriaProducto(empresa_id=second.id, nombre="Categoría ajena", nombre_clave="categoria ajena")
        db.add_all([*branches, category, other_category]); db.flush()
        product = Producto(empresa_id=first.id, categoria_id=category.id, slug="prenda-reporte", nombre="<b>Prenda propia</b>", precio=Decimal("100.00"))
        other_product = Producto(empresa_id=second.id, categoria_id=other_category.id, slug="prenda-privada", nombre="Prenda ajena secreta", precio=Decimal("300.00"))
        db.add_all([product, other_product]); db.flush()
        variant = VarianteProducto(empresa_id=first.id, producto_id=product.id, talla="M", color="VERDE")
        other_variant = VarianteProducto(empresa_id=second.id, producto_id=other_product.id, talla="L", color="AZUL")
        db.add_all([variant, other_variant]); db.flush()
        for branch, item, quantity in [(branches[0], variant, 12), (branches[1], variant, 30), (branches[2], other_variant, 777)]:
            db.add(Existencia(empresa_id=branch.empresa_id, sucursal_id=branch.id, variante_id=item.id, cantidad=quantity))
        roles = ensure_company_roles(db, first.id)
        member.rol_empresa_id = roles["ADMINISTRADOR"].id
        people = {}
        for code in ("ENCARGADO_SUCURSAL", "CAJERO"):
            user = Administrador(nombre="Personal de prueba", correo=f"{code.lower()}@analytics.test", password_hash=hash_password(PASSWORD), activo=True)
            db.add(user); db.flush()
            db.add(MembresiaEmpresa(administrador_id=user.id, empresa_id=first.id, rol=code, rol_empresa_id=roles[code].id, activo=True))
            db.flush(); db.add(AccesoSucursal(administrador_id=user.id, empresa_id=first.id, sucursal_id=branches[0].id))
            people[code] = user.correo
        for branch, item, days, quantity in [(branches[0], product, 2, 2), (branches[0], product, 4, 3), (branches[0], product, 9, 4), (branches[1], product, 3, 7), (branches[2], other_product, 1, 99)]:
            purchase = PurchaseRecord(id=str(uuid4()), empresa_clave=identifier_token(branch.empresa_id), cliente_clave="1", sucursal_clave=identifier_token(branch.id), contexto={}, huella="a"*64, creado_en=utc_now()-timedelta(days=days), total=item.precio*quantity, moneda="BOB")
            purchase.line_records = [PurchaseLineRecord(posicion=0, empresa_clave=purchase.empresa_clave, producto_id=item.id, variante_ref=variant.id if item.id == product.id else other_variant.id, nombre=item.nombre, cantidad=quantity, precio_unitario=item.precio)]
            db.add(purchase)
        db.commit()
        data = SimpleNamespace(company=first.id, other=second.id, own_branch=branches[0].id, other_own_branch=branches[1].id, foreign_branch=branches[2].id, category=category.id, foreign_category=other_category.id, product=product.id, foreign_product=other_product.id, fake=fake,
                               ah={**auth, "X-Empresa-Id": str(first.id)})
    for code, email in people.items():
        signed = client.post("/api/auth/login", json={"correo": email, "password": PASSWORD})
        assert signed.status_code == 200
        setattr(data, "eh" if code == "ENCARGADO_SUCURSAL" else "ch", {"Authorization": "Bearer "+signed.json()["access_token"], "X-Empresa-Id": str(data.company)})
    yield data
    app.dependency_overrides.pop(get_interpreter, None)
    analytics.load_models.cache_clear()


@pytest.mark.parametrize("kind", ["ventas_diarias", "prendas_vendidas", "inventario", "abastecimiento"])
def test_four_report_types_use_real_scoped_queries(client, ai, kind):
    ai.fake.kind = kind
    response = client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Consulta autorizada", "filtros": {}})
    assert response.status_code == 200, response.text
    report = response.json()["reporte"]
    assert report["tipo"] == kind and report["empresa"]["id"] == ai.company
    assert "Prenda ajena secreta" not in response.text and "777" not in response.text
    assert response.headers["cache-control"] == "no-store"


def _cash_for_analytics(db, company, branch, product, user, quantity, price, *, identifier=None, code=None, days=1):
    from app.operacion_sin_conexion.caja.online import CashSale
    variant = db.scalar(select(VarianteProducto).where(
        VarianteProducto.empresa_id == company, VarianteProducto.producto_id == product))
    total = Decimal(price) * quantity
    sale = CashSale(id=identifier or str(uuid4()), empresa_id=company, sucursal_id=branch,
        usuario_id=user, huella="b" * 64,
        lineas=[{"variante_id": variant.id, "producto_id": product, "cantidad": quantity,
                 "precio_unitario": price}], total=total, efectivo=total, cambio=Decimal("0.00"),
        codigo=code or "VN-C-" + uuid4().hex[:12], origen="EN_LINEA", entrega_local=False,
        confirmada_en=utc_now() - timedelta(days=days))
    db.add(sale)
    return sale


def test_cash_and_digital_sales_feed_reports_without_uuid_collisions(client, ai, session_factory, administrator):
    with session_factory() as db:
        same_uuid = db.scalar(select(PurchaseRecord.id).where(
            PurchaseRecord.empresa_clave == identifier_token(ai.company)))
        _cash_for_analytics(db, ai.company, ai.own_branch, ai.product, administrator.id, 2, "75.00",
                            identifier=same_uuid, code="VN-DEMO-CU20-REGRESION")
        _cash_for_analytics(db, ai.company, ai.other_own_branch, ai.product, administrator.id, 4, "80.00")
        _cash_for_analytics(db, ai.other, ai.foreign_branch, ai.foreign_product, administrator.id, 99, "9.00")
        db.commit()
    ai.fake.kind = "prendas_vendidas"
    report = client.post("/api/admin/reportes-ia/generar", headers=ai.ah,
                         json={"consulta": "Todas las prendas vendidas"}).json()["reporte"]
    assert report["totales"]["unidades"] == 22
    assert report["totales"]["importe_bruto_bob"] == "2070.00"  # Precio del comprobante, no el actual.
    assert report["totales"]["operaciones_aceptadas"] == 6  # Cuatro digitales y dos de caja.
    assert report["origen_datos"] == {"demostracion": True, "compras_demo": 1, "compras_operativas": 5}
    scoped = client.post("/api/admin/reportes-ia/generar", headers=ai.eh,
                         json={"consulta": "Prendas de mi sucursal"}).json()["reporte"]
    assert scoped["totales"]["unidades"] == 11
    assert scoped["totales"]["importe_bruto_bob"] == "1050.00"
    dashboard = client.post("/api/admin/dashboard-predictivo", headers=ai.ah, json={}).json()
    assert dashboard["filas"][0]["unidades_reales_7d"] == 18
    assert dashboard["filas"][0]["unidades_reales_previas_7d"] == 4


def test_cash_sales_respect_date_product_and_category_filters(client, ai, session_factory, administrator):
    with session_factory() as db:
        _cash_for_analytics(db, ai.company, ai.own_branch, ai.product, administrator.id, 3, "50.00", days=1)
        _cash_for_analytics(db, ai.company, ai.own_branch, ai.product, administrator.id, 8, "50.00", days=10)
        empty_category = CategoriaProducto(empresa_id=ai.company, nombre="Sin ventas", nombre_clave="sin ventas")
        db.add(empty_category); db.commit(); empty_id = empty_category.id
    ai.fake.kind = "ventas_diarias"
    filters = {"desde": (utc_now().date()-timedelta(days=6)).isoformat(),
               "producto_id": ai.product, "categoria_id": ai.category}
    report = client.post("/api/admin/reportes-ia/generar", headers=ai.eh,
                         json={"consulta": "Ventas de los últimos siete días", "filtros": filters}).json()["reporte"]
    assert report["totales"]["unidades"] == 8  # Digitales 5 + caja 3; excluye la caja antigua y otra sucursal.
    empty = client.post("/api/admin/reportes-ia/generar", headers=ai.ah,
                        json={"consulta": "Ventas por categoría", "filtros": {"categoria_id": empty_id}}).json()["reporte"]
    assert empty["filas"] == [] and empty["totales"]["unidades"] == 0


def test_incompatible_cash_snapshot_is_reported_without_inventing_totals(client, ai, session_factory, administrator):
    with session_factory() as db:
        sale = _cash_for_analytics(db, ai.company, ai.own_branch, ai.product, administrator.id, 1, "50.00")
        sale.lineas[0]["precio_unitario"] = "NaN"
        db.commit()
    ai.fake.kind = "ventas_diarias"
    result = client.post("/api/admin/reportes-ia/generar", headers=ai.ah,
                         json={"consulta": "Ventas confirmadas"})
    assert result.status_code == 503 and "comprobante de caja" in result.json()["detail"]


def test_branch_grants_are_applied_even_when_ai_does_not_choose_a_branch(client, ai):
    response = client.post("/api/admin/reportes-ia/generar", headers=ai.eh, json={"consulta": "Inventario actual", "filtros": {}})
    assert response.status_code == 200
    assert response.json()["reporte"]["totales"]["fisico"] == 12
    ai.fake.kind = "prendas_vendidas"
    response = client.post("/api/admin/reportes-ia/generar", headers=ai.eh, json={"consulta": "Prendas vendidas", "filtros": {}})
    assert response.json()["reporte"]["totales"]["unidades"] == 9
    assert response.json()["reporte"]["totales"]["importe_bruto_bob"] == "900.00"


@pytest.mark.parametrize("field", ["sucursal_id", "categoria_id", "producto_id"])
def test_foreign_filters_are_rejected_before_contacting_ai(client, ai, field):
    identifier = {"sucursal_id": ai.foreign_branch, "categoria_id": ai.foreign_category, "producto_id": ai.foreign_product}[field]
    response = client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Reporte de otra empresa", "filtros": {field: identifier}})
    assert response.status_code == 404 and ai.fake.calls == 0


def test_cannot_select_an_unassigned_branch_and_cashier_has_no_reports(client, ai):
    assert client.post("/api/admin/reportes-ia/generar", headers=ai.eh, json={"consulta": "Inventario", "filtros": {"sucursal_id": ai.other_own_branch}}).status_code == 404
    assert client.get("/api/admin/reportes-ia/opciones", headers=ai.ch).status_code == 403
    assert client.post("/api/admin/dashboard-predictivo", headers=ai.eh, json={}).status_code == 403


def test_basic_or_suspended_plan_blocks_reports_without_using_ai(client, ai, session_factory):
    with session_factory() as db:
        basic = db.scalar(select(PlanSaaS).where(PlanSaaS.codigo == "BASICO"))
        db.get(SuscripcionEmpresa, ai.company).plan_id = basic.id
        db.commit()
    assert client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Inventario actual"}).status_code == 403
    assert ai.fake.calls == 0


@pytest.mark.parametrize("kind", ["aclaracion", "no_admitido"])
def test_ambiguous_and_unsupported_queries_have_no_fabricated_results(client, ai, kind):
    ai.fake.kind = kind
    result = client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Algo que no está claro"})
    assert result.status_code == 200 and result.json()["estado"] == kind and "reporte" not in result.json()


@pytest.mark.parametrize("formato", ["html", "pdf", "xlsx"])
def test_exports_revalidate_scope_and_produce_real_files(client, ai, formato):
    payload = {"tipo": "inventario", "filtros": {"sucursal_id": ai.own_branch}, "formato": formato}
    result = client.post("/api/admin/reportes-ia/exportar", headers=ai.eh, json=payload)
    assert result.status_code == 200 and len(result.content) > 100
    assert result.headers["cache-control"] == "no-store"
    if formato == "html":
        assert b"&lt;b&gt;Prenda propia&lt;/b&gt;" in result.content and b"Prenda ajena" not in result.content
    elif formato == "pdf":
        assert result.content.startswith(b"%PDF-")
    else:
        workbook = load_workbook(BytesIO(result.content))
        assert any(cell.value == "<b>Prenda propia</b>" for row in workbook.active for cell in row)
        assert workbook['Totales'].cell(2, 2).value == 12
    payload["filtros"]["sucursal_id"] = ai.foreign_branch
    assert client.post("/api/admin/reportes-ia/exportar", headers=ai.eh, json=payload).status_code == 404


def test_prediction_runs_trained_models_and_labels_synthetic_metrics(client, ai):
    response = client.post("/api/admin/dashboard-predictivo", headers=ai.ah, json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["estado"] == "resultados" and len(result["filas"]) == 1
    assert result["filas"][0]["unidades_reales_7d"] == 12
    assert result["filas"][0]["demanda_estimada_7d"] >= 0
    assert result["modelo"]["origen"] == "sintetico" and result["modelo"]["evaluacion"] == 600
    assert result["modelo"]["metricas"]["mae"] >= 0
    assert "Prenda ajena secreta" not in response.text


def test_insufficient_real_data_does_not_make_up_business_predictions(client, ai, session_factory):
    with session_factory() as db:
        for record in db.scalars(select(PurchaseRecord)).all():
            db.delete(record)
        db.commit()
    result = client.post("/api/admin/dashboard-predictivo", headers=ai.ah, json={}).json()
    assert result["estado"] == "datos_insuficientes" and result["filas"] == []
    assert len(result["modelo"]["ejemplos_sinteticos"]) == 5


def test_missing_models_are_not_presented_as_evaluated(client, ai, monkeypatch, tmp_path):
    analytics.load_models.cache_clear()
    monkeypatch.setattr(analytics, "ARTIFACT", tmp_path / "inexistente.json")
    response = client.post("/api/admin/dashboard-predictivo", headers=ai.ah, json={})
    assert response.status_code == 503


def test_queries_do_not_change_commercial_records(client, ai, session_factory):
    models = (PurchaseRecord, PurchaseLineRecord, Existencia, Producto)
    with session_factory() as db:
        before = [db.scalar(select(func.count()).select_from(model)) for model in models]
    for kind in ("inventario", "ventas_diarias", "prendas_vendidas", "abastecimiento"):
        ai.fake.kind = kind
        assert client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Consulta de solo lectura"}).status_code == 200
    with session_factory() as db:
        assert [db.scalar(select(func.count()).select_from(model)) for model in models] == before


def test_membership_revoked_while_waiting_for_ai_cannot_return_private_rows(client, ai, session_factory):
    def revoke(prompt, today):
        with session_factory() as db:
            membership = db.scalar(select(MembresiaEmpresa).where(MembresiaEmpresa.empresa_id == ai.company))
            membership.activo = False
            db.commit()
        return Interpretation(tipo="inventario")
    ai.fake.interpret = revoke
    response = client.post("/api/admin/reportes-ia/generar", headers=ai.ah, json={"consulta": "Inventario actual"})
    assert response.status_code == 403 and "reporte" not in response.json()


def test_unknown_partial_stock_does_not_become_a_prediction(client, ai, session_factory):
    with session_factory() as db:
        db.delete(db.get(Existencia, (ai.company, ai.other_own_branch, db.scalar(select(VarianteProducto.id).where(VarianteProducto.producto_id == ai.product)))) )
        db.commit()
    result = client.post("/api/admin/dashboard-predictivo", headers=ai.ah, json={}).json()
    assert result["filas"] == [] and result["estado"] == "datos_insuficientes"
    assert "existencias" in result["omitidos"][0]["motivo"]


def test_provider_cannot_supply_sql_or_arbitrary_report_types(monkeypatch):
    from fastapi import HTTPException
    from app.analitica_ia.provider import Interpreter, JSONClient
    from datetime import date
    monkeypatch.setattr(JSONClient, "complete", lambda *args: {"tipo": "inventario", "sql": "SELECT * FROM administradores"})
    with pytest.raises(HTTPException) as failure:
        Interpreter().interpret("Inventario actual", date.today())
    assert failure.value.status_code == 503


def test_session_revoked_while_waiting_for_ai_is_rechecked(client, ai, session_factory):
    import jwt
    from app.models import SesionAdministrador
    identifier = jwt.decode(ai.ah['Authorization'].split()[1], options={'verify_signature': False})['jti']
    def revoke(prompt, today):
        with session_factory() as db:
            db.get(SesionAdministrador, identifier).revocada = True
            db.commit()
        return Interpretation(tipo='inventario')
    ai.fake.interpret = revoke
    response = client.post('/api/admin/reportes-ia/generar', headers=ai.ah, json={'consulta':'Inventario actual'})
    assert response.status_code == 401 and 'reporte' not in response.json()
