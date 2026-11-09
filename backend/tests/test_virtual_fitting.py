from io import BytesIO
from datetime import timedelta
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Empresa, MembresiaEmpresa, Producto, SuscripcionEmpresa, VarianteProducto, utc_now
from app.vestidor_virtual.models import ConfiguracionVestidor
from scripts.seed_analytics_history import fingerprints


@pytest.fixture
def fitting(client, auth):
    product=client.post('/api/admin/productos',headers=auth,json={'nombre':'Polera de varón','precio':'119.00'}).json()
    variants=[]
    for size,color in [('M','Gris'),('L','Azul')]:
        response=client.post(f"/api/admin/productos/{product['id']}/variantes",headers=auth,json={'talla':size,'color':color})
        assert response.status_code==201
        variants.append(response.json())
    return product,variants


def config_url(product,variant):
    return f"/api/admin/productos/{product['id']}/variantes/{variant['id']}/vestidor"


PAYLOAD={'recurso_url':'/api/vestidor/recursos/polera-gris.png','tipo_prenda':'POLERA'}


ANCHORS = {'manga': 'LARGA', **dict(zip(
    ['hombro_izq','hombro_der','cintura_izq','cintura_der','manga_izq_media','manga_izq_fin','manga_der_media','manga_der_fin'],
    [{'x': x, 'y': y} for x,y in [(.32,.2),(.68,.2),(.35,.86),(.65,.86),(.22,.48),(.12,.85),(.78,.48),(.88,.85)]]))}


def test_anchor_calibration_persists_is_public_and_legacy_clients_do_not_erase_it(client,auth,fitting,session_factory):
    product,variants=fitting
    path=config_url(product,variants[0])
    response=client.put(path,headers=auth,json={**PAYLOAD,'anclajes':ANCHORS})
    assert response.status_code==200,response.text
    assert response.json()['configuracion']['anclajes']==ANCHORS
    with session_factory() as db:
        assert db.get(ConfiguracionVestidor,variants[0]['id']).anclajes==ANCHORS
    assert client.get(path,headers=auth).json()['configuracion']['anclajes']==ANCHORS
    public=client.get(f"/api/catalogo/productos/{product['slug']}/vestidor",params={'tienda':'empresa-prueba'}).json()
    assert next(v for v in public['variantes'] if v['variante_id']==variants[0]['id'])['configuracion']['anclajes']==ANCHORS
    assert client.put(path,headers=auth,json=PAYLOAD).json()['configuracion']['anclajes']==ANCHORS
    assert client.put(path,headers=auth,json={**PAYLOAD,'anclajes':None}).json()['configuracion']['anclajes'] is None
    client.put(path,headers=auth,json={**PAYLOAD,'anclajes':ANCHORS})
    changed={**PAYLOAD,'recurso_url':'/api/vestidor/recursos/polera-azul.png'}
    assert client.put(path,headers=auth,json=changed).json()['configuracion']['anclajes'] is None


@pytest.mark.parametrize('changes',[
    {'hombro_izq':{'x':-.1,'y':.2}}, {'hombro_der':{'x':.3,'y':.2}},
    {'cintura_izq':{'x':.35,'y':.25}}, {'manga':'INVALID'},
    {'manga_izq_media':{'x':.32,'y':.2}}, {'manga_der_fin':{'x':.1,'y':.85}},
    {'privilegio':'SaaS'}, {'hombro_izq':{'x':.32,'y':.2,'z':1}},
])
def test_rejects_invalid_or_incomplete_source_calibration(client,auth,fitting,changes):
    product,variants=fitting
    response=client.put(config_url(product,variants[0]),headers=auth,json={**PAYLOAD,'anclajes':{**ANCHORS,**changes}})
    assert response.status_code==422


def test_catalog_contract_and_stock_are_preserved_and_variants_can_be_selected(client,auth,fitting,session_factory):
    product,variants=fitting
    public=f"/api/catalogo/productos/{product['slug']}"
    before=client.get(public).json()
    with session_factory() as db: original=fingerprints(db)
    for variant in variants:
        result=client.put(config_url(product,variant),headers=auth,json=PAYLOAD)
        assert result.status_code==200,result.text
        assert result.json()['configuracion']['demostracion'] is True
    result=client.get(public+'/vestidor',params={'tienda':'empresa-prueba'})
    assert result.status_code==200
    data=result.json()
    assert data['compatible'] is True and len(data['variantes'])==2
    assert {v['talla'] for v in data['variantes']}=={'M','L'}
    assert {v['color'] for v in data['variantes']}=={'GRIS','AZUL'}
    assert result.headers['cache-control']=='no-store'
    assert client.get(public).json()==before and before['precio']=='119.00' and before['moneda']=='BOB'
    with session_factory() as db:
        after=fingerprints(db)
        for name,rows in original.items():
            if name not in {'configuraciones_vestidor','eventos_auditoria'}:
                assert rows==after[name],name
    scoped=client.get(public+'/vestidor',params={'tienda':'empresa-prueba','variante_id':variants[1]['id']}).json()
    assert len(scoped['variantes'])==1 and scoped['variantes'][0]['color']=='AZUL'


@pytest.mark.parametrize('changes',[
    {'empresa_id':999},{'cliente_id':1},{'recurso_url':'javascript:alert(1)'},
    {'recurso_url':'https://user:secret@example.test/shirt.png'}, {'recurso_url':'https://example.test/photo.jpg'},
    {'recurso_url':'/api/vestidor/recursos/../other.png'}, {'recurso_url':'https://example.test/shirt.png#fragment'},
    {'factor_ancho':0}, {'factor_alto':3}, {'offset_x':.6}, {'tipo_prenda':'PANTALON'},
])
def test_configuration_rejects_unsupported_or_unsafe_fields(client,auth,fitting,changes):
    product,variants=fitting
    assert client.put(config_url(product,variants[0]),headers=auth,json={**PAYLOAD,**changes}).status_code==422


def test_permissions_and_company_isolation_are_checked_by_server(client,auth,fitting,session_factory,administrator):
    product,variants=fitting
    assert client.put(config_url(product,variants[0]),json=PAYLOAD).status_code==401
    with session_factory.begin() as db:
        other=Empresa(slug='otra-tienda',nombre='Otra empresa');db.add(other);db.flush()
        own=db.scalar(select(Empresa).where(Empresa.slug=='empresa-prueba'))
        other_product=Producto(empresa_id=other.id,slug='otra-polera',nombre='Otra polera',precio=90);db.add(other_product);db.flush()
        other_variant=VarianteProducto(empresa_id=other.id,producto_id=other_product.id,talla='M',color='Negro');db.add(other_variant);db.flush()
        foreign_id=other_variant.id;own_id=own.id
    assert client.put(f"/api/admin/productos/{product['id']}/variantes/{foreign_id}/vestidor",headers=auth,json=PAYLOAD).status_code==404
    assert client.get(f"/api/catalogo/productos/otra-polera/vestidor",params={'tienda':'empresa-prueba'}).status_code==404
    assert client.get(f"/api/catalogo/productos/{product['slug']}/vestidor",params={'tienda':'empresa-prueba','variante_id':foreign_id}).status_code==404
    with session_factory() as db:
        db.add(ConfiguracionVestidor(variante_id=foreign_id,empresa_id=own_id,**PAYLOAD))
        with pytest.raises(IntegrityError):db.flush()
        db.rollback()
    with session_factory.begin() as db:
        member=db.get(MembresiaEmpresa,(administrator.id,own_id));member.rol='CAJERO';member.rol_empresa_id=None
    assert client.put(config_url(product,variants[0]),headers=auth,json=PAYLOAD).status_code==403


@pytest.mark.parametrize('disabled',['config','variant','product','company','subscription'])
def test_inactive_resources_are_not_exposed(client,auth,fitting,session_factory,disabled):
    product,variants=fitting
    assert client.put(config_url(product,variants[0]),headers=auth,json=PAYLOAD).status_code==200
    with session_factory.begin() as db:
        p=db.get(Producto,product['id'])
        row={'config':db.get(ConfiguracionVestidor,variants[0]['id']),'variant':db.get(VarianteProducto,variants[0]['id']),
             'product':p,'company':db.get(Empresa,p.empresa_id),'subscription':db.get(SuscripcionEmpresa,p.empresa_id)}[disabled]
        if disabled=='subscription':row.estado='SUSPENDIDA'
        else:row.activo=False
    result=client.get(f"/api/catalogo/productos/{product['slug']}/vestidor",params={'tienda':'empresa-prueba'})
    if disabled in {'product','company','subscription'}:assert result.status_code==404
    else:assert result.status_code==200 and result.json()['compatible'] is False


def test_incompatible_product_suggests_only_compatible_products_from_same_store(client,auth,fitting):
    product,variants=fitting
    assert client.put(config_url(product,variants[0]),headers=auth,json=PAYLOAD).status_code==200
    other=client.post('/api/admin/productos',headers=auth,json={'nombre':'Pantalón de varón','precio':'209.00'}).json()
    result=client.get(f"/api/catalogo/productos/{other['slug']}/vestidor",params={'tienda':'empresa-prueba'}).json()
    assert result['compatible'] is False and result['variantes']==[]
    assert result['alternativas']==[{'slug':product['slug'],'nombre':product['nombre']}]
    assert 'no tiene un recurso' in result['motivo']


def test_demo_images_are_real_transparent_pngs_and_do_not_take_file_paths(client):
    for name in ['polera-gris.png','polera-azul.png','camisa-azul.png','camisa-blanca.png']:
        response=client.get('/api/vestidor/recursos/'+name)
        assert response.status_code==200 and response.headers['content-type']=='image/png'
        image=Image.open(BytesIO(response.content))
        assert image.format=='PNG' and image.mode=='RGBA'
        assert image.getchannel('A').getextrema()==(0,255)
    assert client.get('/api/vestidor/recursos/secrets.png').status_code==404


def test_demo_loader_preserves_existing_rows_and_is_repeatable(session_factory):
    from scripts.seed_tryon_demo import seed
    with session_factory() as db:
        db.add(Empresa(slug='demo-moda-urbana',nombre='Moda Urbana Demo'));db.flush()
        before=fingerprints(db)
        assert seed(db)==5
        after=fingerprints(db)
        for table,rows in before.items():
            assert not rows-after[table]
            if table not in {'productos','variantes_producto','configuraciones_vestidor'}:assert rows==after[table]
        assert seed(db)==0 and fingerprints(db)==after


def png_cutout(*, size=(240, 300), opaque=False, empty=False):
    image = Image.new('RGBA', size, (0, 0, 0, 0) if not opaque else (30, 50, 80, 255))
    if not empty and not opaque:
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle((45, 40, 195, 270), fill=(30, 50, 80, 255))
    output = BytesIO(); image.save(output, format='PNG')
    return output.getvalue()


def test_uploaded_cutout_is_private_until_published_and_does_not_change_catalog_or_stock(client, auth, fitting, session_factory, monkeypatch, tmp_path):
    from app.vestidor_virtual import resources
    monkeypatch.setattr(resources, 'STORAGE_ROOT', tmp_path / 'recortes')
    product, variants = fitting
    path = config_url(product, variants[0])
    public = '/api/catalogo/productos/' + product['slug']
    catalog_before = client.get(public).json()
    with session_factory() as db: before = fingerprints(db)
    data = png_cutout()
    response = client.put(path + '/recurso', headers={**auth, 'Content-Type': 'image/png'}, content=data)
    assert response.status_code == 200
    url = response.json()['recurso_url']
    assert response.json()['publicado'] is False
    assert client.get(url).status_code == 404
    assert client.put(path + '/recurso', headers={**auth, 'Content-Type': 'image/png'}, content=data).json()['recurso_url'] == url
    assert len(list((tmp_path / 'recortes').rglob('*.png'))) == 1
    with session_factory() as db: assert fingerprints(db) == before
    result = client.put(path, headers=auth, json={**PAYLOAD, 'recurso_url': url})
    assert result.status_code == 200 and result.json()['configuracion']['demostracion'] is False
    downloaded = client.get(url)
    assert downloaded.status_code == 200 and downloaded.content == data
    assert downloaded.headers['x-content-type-options'] == 'nosniff'
    assert client.get(public).json() == catalog_before
    assert client.put(path, headers=auth, json={**PAYLOAD, 'recurso_url': url, 'activo': False}).status_code == 200
    assert client.get(url).status_code == 404


@pytest.mark.parametrize('data,status', [(b'not a png', 422), (png_cutout(opaque=True), 422),
    (png_cutout(empty=True), 422), (png_cutout(size=(2049, 10)), 422), (b'x'*(6*1024*1024+1), 413)],
    ids=['not-png', 'opaque-background', 'empty', 'dimensions', 'payload-limit'])
def test_upload_rejects_wrong_background_invalid_or_oversized_images(client, auth, fitting, monkeypatch, tmp_path, data, status):
    from app.vestidor_virtual import resources
    monkeypatch.setattr(resources, 'STORAGE_ROOT', tmp_path / 'recortes')
    product, variants = fitting
    result = client.put(config_url(product, variants[0]) + '/recurso', headers={**auth, 'Content-Type': 'image/png'}, content=data)
    assert result.status_code == status
    assert not (tmp_path / 'recortes').exists()


def test_upload_and_configuration_enforce_company_and_permission(client, auth, fitting, administrator, session_factory, monkeypatch, tmp_path):
    from app.vestidor_virtual import resources
    monkeypatch.setattr(resources, 'STORAGE_ROOT', tmp_path / 'recortes')
    product, variants = fitting
    path = config_url(product, variants[0])
    data = png_cutout()
    assert client.put(path + '/recurso', headers={'Content-Type': 'image/png'}, content=data).status_code == 401
    assert client.put(path + '/recurso', headers={**auth, 'Content-Type': 'image/jpeg'}, content=data).status_code == 415
    with session_factory() as db:
        other = Empresa(slug='otra-tienda-recorte', nombre='Otra tienda')
        db.add(other); db.flush()
        first_company = db.get(Producto, product['id']).empresa_id
        plan = db.get(SuscripcionEmpresa, first_company).plan_id
        db.add(SuscripcionEmpresa(empresa_id=other.id, plan_id=plan, estado='ACTIVA', inicia_en=utc_now()-timedelta(days=1)))
        db.add(MembresiaEmpresa(administrador_id=administrator.id, empresa_id=other.id, rol='ADMINISTRADOR'))
        db.commit(); other_id = other.id
    other_auth = {**auth, 'X-Empresa-Id': str(other_id)}
    own_auth = {**auth, 'X-Empresa-Id': str(first_company)}
    assert client.put(path + '/recurso', headers={**other_auth, 'Content-Type': 'image/png'}, content=data).status_code == 404
    other_product = client.post('/api/admin/productos', headers=other_auth, json={'nombre':'Otra polera de varón','precio':'99.00'}).json()
    other_variant = client.post(f"/api/admin/productos/{other_product['id']}/variantes", headers=other_auth, json={'talla':'M','color':'Azul'}).json()
    uploaded = client.put(path + '/recurso', headers={**own_auth, 'Content-Type': 'image/png'}, content=data)
    assert uploaded.status_code == 200
    url = uploaded.json()['recurso_url']
    assert client.put(config_url(other_product, other_variant), headers=other_auth, json={**PAYLOAD, 'recurso_url':url}).status_code == 404
    with session_factory() as db:
        member = db.get(MembresiaEmpresa, (administrator.id, first_company))
        member.rol = 'OPERADOR'; member.rol_empresa_id = None; db.commit()
    assert client.put(path + '/recurso', headers={**own_auth, 'Content-Type': 'image/png'}, content=data).status_code == 403


def test_session_revoked_while_uploading_cannot_publish_a_resource(client, auth, fitting, administrator, session_factory, monkeypatch, tmp_path):
    from app.models import SesionAdministrador
    from app.vestidor_virtual import api, resources
    monkeypatch.setattr(resources, 'STORAGE_ROOT', tmp_path / 'recortes')
    seen = []
    original = api.admin_variant
    def observed_variant(*args):
        seen.append(True)
        return original(*args)
    monkeypatch.setattr(api, 'admin_variant', observed_variant)
    data = png_cutout()
    def chunks():
        assert seen, 'La autorización inicial debe haber ocurrido antes de recibir el archivo.'
        yield data[:40]
        with session_factory.begin() as db:
            session = db.scalar(select(SesionAdministrador).where(SesionAdministrador.administrador_id == administrator.id))
            session.revocada = True
        yield data[40:]
    product, variants = fitting
    result = client.put(config_url(product, variants[0]) + '/recurso',
                        headers={**auth, 'Content-Type': 'image/png'}, content=chunks())
    assert result.status_code == 401 and not (tmp_path / 'recortes').exists()
