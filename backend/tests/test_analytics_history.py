from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from app.autenticacion_usuarios.permissions import ensure_company_roles
from app.compras_reservas.compras.persistence import PurchaseRecord, _hydrate
from app.models import Cliente, Empresa, Existencia, MembresiaEmpresa, MovimientoInventario, PlanSaaS, Producto, Sucursal, SuscripcionEmpresa, VarianteProducto, utc_now
from app.analitica_ia.data_origin import DEMO_HISTORY_ORIGIN
from scripts import seed_analytics_history as loader


@pytest.fixture
def history(session_factory, administrator):
    with session_factory() as db:
        company = Empresa(slug=loader.COMPANY_SLUG, nombre="Moda Urbana Demo")
        db.add(company); db.flush()
        roles = ensure_company_roles(db,company.id)
        plan = PlanSaaS(codigo="PROFESIONAL",nombre="Profesional aislado",activo=True,max_sucursales=10,max_usuarios=100,max_productos=100)
        db.add(plan); db.flush()
        db.add(SuscripcionEmpresa(empresa_id=company.id,plan_id=plan.id,estado="ACTIVA",inicia_en=utc_now()-timedelta(days=1)))
        db.add(MembresiaEmpresa(administrador_id=administrator.id,empresa_id=company.id,nombre=administrator.nombre,rol="ADMINISTRADOR",rol_empresa_id=roles['ADMINISTRADOR'].id,activo=True))
        customer = Cliente(empresa_id=company.id,correo="cliente.urbana@vestinova.test",nombre="Cliente Demo",password_hash="fixture-no-utilizable",activo=True)
        branches = [Sucursal(empresa_id=company.id,codigo=code,nombre=code) for code in loader.BRANCHES]
        db.add_all([customer,*branches]); db.flush()
        product_ids=[]
        for index,slug in enumerate(loader.PRODUCTS):
            product=Producto(empresa_id=company.id,slug=slug,nombre=f"Prenda demo {index}",precio=[119,209,289][index])
            db.add(product); db.flush(); product_ids.append(product.id)
            variant=VarianteProducto(empresa_id=company.id,producto_id=product.id,talla="M",color="Verde")
            db.add(variant); db.flush()
            for branch_index,branch in enumerate(branches):
                quantity=((16,14,12),(5,3,1),(0,0,0))[index][branch_index]
                db.add(Existencia(empresa_id=company.id,sucursal_id=branch.id,variante_id=variant.id,cantidad=quantity))
        db.commit()
        return SimpleNamespace(company=company.id,branches=[branch.id for branch in branches],products=product_ids,reference=datetime.now(timezone.utc).date())


def test_history_is_valid_repeatable_and_preserves_every_previous_record(session_factory, history):
    with session_factory() as db:
        before=loader.fingerprints(db)
        first=loader.seed_history(db,history.reference)
        assert first['creadas']==126 and first['existentes']==0
        after=loader.fingerprints(db)
        for table,rows in before.items():
            assert not rows-after[table]
            if table not in {'compras_digitales','compras_digitales_lineas'}:
                assert rows==after[table]
        records=db.scalars(select(PurchaseRecord)).all()
        assert len(records)==126
        for record in records:
            assert record.contexto['origen']==DEMO_HISTORY_ORIGIN
            assert _hydrate(record).total==record.total
            assert record.creado_en.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
        assert loader.seed_history(db,history.reference)['creadas']==0
        assert loader.fingerprints(db)==after


def test_dashboard_predicts_and_groups_with_explicit_demo_origin(client,auth,session_factory,history):
    with session_factory.begin() as db:
        loader.seed_history(db,history.reference)
    headers={**auth,'X-Empresa-Id':str(history.company)}
    for analysis in ('ambos','prediccion','agrupaciones'):
        response=client.post('/api/admin/dashboard-predictivo',headers=headers,json={'analisis':analysis})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['estado']=='resultados' and len(result['filas'])==3
        assert result['origen_datos']=={'demostracion':True,'compras_demo':126,'compras_operativas':0}
        assert sum(row['stock_disponible_real'] for row in result['filas'])==51
        assert all((row['demanda_estimada_7d'] is None)==(analysis=='agrupaciones') for row in result['filas'])
        assert all((row['agrupacion_estimada'] is None)==(analysis=='prediccion') for row in result['filas'])
    scoped=client.post('/api/admin/dashboard-predictivo',headers=headers,json={'filtros':{'sucursal_id':history.branches[0]}}).json()
    assert scoped['origen_datos']['compras_demo']==42


def test_demo_history_does_not_leak_to_other_company(client,auth,session_factory,history,administrator):
    with session_factory.begin() as db:
        loader.seed_history(db,history.reference)
        other=db.scalar(select(Empresa).where(Empresa.slug=='empresa-prueba'))
        branch=Sucursal(empresa_id=other.id,codigo="OTRA",nombre="Otra sucursal")
        db.add(branch); db.flush(); foreign_branch=branch.id; other_id=other.id
    result=client.post('/api/admin/dashboard-predictivo',headers={**auth,'X-Empresa-Id':str(other_id)},json={}).json()
    assert result['filas']==[] and result['origen_datos']['compras_demo']==0
    result=client.post('/api/admin/dashboard-predictivo',headers={**auth,'X-Empresa-Id':str(history.company)},json={'filtros':{'sucursal_id':foreign_branch}})
    assert result.status_code==404


def test_sales_exports_identify_the_imported_demo_history(client,auth,session_factory,history):
    with session_factory.begin() as db:
        loader.seed_history(db,history.reference)
    result=client.post('/api/admin/reportes-ia/exportar',headers={**auth,'X-Empresa-Id':str(history.company)},json={'tipo':'prendas_vendidas','filtros':{},'formato':'pdf'})
    assert result.status_code==200
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(result.content)).pages)
    assert 'Datos de demostración' in text and 'historial de compras simulado' in text


def test_loader_refuses_mvp_database_before_connecting(monkeypatch,tmp_path):
    monkeypatch.setattr(loader,'BACKEND_ROOT',tmp_path)
    (tmp_path/'.env').write_text('TEST_CONFIG=fixture',encoding='utf-8')
    monkeypatch.setattr('sys.argv',['seed_analytics_history'])
    monkeypatch.setattr(loader,'use_demo_database',lambda:None)
    monkeypatch.setattr(loader,'Settings',SimpleNamespace(from_env=lambda:SimpleNamespace(database_url='postgresql+psycopg://fixture@127.0.0.1/vestinova_mvp')))
    monkeypatch.setattr(loader,'build_engine',lambda *_:pytest.fail('No debe abrir una conexión'))
    with pytest.raises(ValueError,match='vestinova_pruebas'):
        loader.main()


def test_loader_refuses_future_reference_date(monkeypatch):
    tomorrow=(datetime.now(timezone.utc).date()+timedelta(days=1)).isoformat()
    monkeypatch.setattr('sys.argv',['seed_analytics_history','--fecha-referencia',tomorrow])
    with pytest.raises(ValueError,match='futura'):
        loader.main()
