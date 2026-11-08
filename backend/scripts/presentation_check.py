"""Comprueba requisitos de datos de la demo local sin crear operaciones comerciales.

Solo vestinova_pruebas. No imprime claves, hashes, tokens ni URLs de conexión.
--json permite conservar el resultado en una ubicación local ignorada por Git.
"""
import argparse
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from app.config import Settings, validate_demo_database_url
from app.db import build_engine, build_session_factory
from app.models import (CategoriaProducto, Cliente, Empresa, EventoAuditoria, Existencia,
    MembresiaEmpresa, MovimientoInventario, OrdenAbastecimiento, PlanSaaS, Producto, Promocion, Proveedor,
    RecepcionAbastecimiento, RolEmpresa, Sucursal, SuscripcionEmpresa, VarianteProducto)
from app.organizacion_empresarial.plans import subscription_state
from app.catalogo_abastecimiento.promotions import promotion_state
from app.compras_reservas.compras.domain import identifier_token
from app.compras_reservas.compras.persistence import PurchaseRecord
from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt, _configuration
from app.compras_reservas.postventa.persistence import SolicitudPostventa
from app.compras_reservas.reservas.online import ReservationRecord
from app.compras_reservas.compras.valoraciones import EntregaCompra, ValoracionCompra
from app.compras_reservas.alertas_push import AlertaReposicion, push_enabled
from app.compras_reservas.deseos import Deseo
from app.catalogo_publico.historial_recomendaciones import VistaCU19
from app.operacion_sin_conexion.caja.online import CashSale, SyncIncident
from app.vestidor_virtual.models import ConfiguracionVestidor
from app.analitica_ia.data_origin import DEMO_HISTORY_ORIGIN
from app.analitica_ia.analytics import load_models
from app.ia.client import configured as ai_configured
from scripts.demo_environment import use_demo_database


def collect(db, settings):
    stores=[]
    for slug in ('demo-moda-andina','demo-moda-urbana'):
        company=db.scalar(select(Empresa).where(Empresa.slug==slug))
        if company is None:
            stores.append({'tienda':slug,'problema':'Empresa demo ausente'});continue
        def count(model,*filters):
            return db.scalar(select(func.count()).select_from(model).where(model.empresa_id==company.id,*filters)) or 0
        sub=db.get(SuscripcionEmpresa,company.id)
        plan=db.get(PlanSaaS,sub.plan_id) if sub else None
        purchases=db.scalars(select(PurchaseRecord).where(PurchaseRecord.empresa_clave==identifier_token(company.id))).all()
        simulation=sum(row.contexto.get('origen')==DEMO_HISTORY_ORIGIN for row in purchases)
        rows=db.execute(select(Producto.slug,VarianteProducto.talla,VarianteProducto.color,Sucursal.codigo,
                              Existencia.cantidad-Existencia.cantidad_comprometida)
            .join(VarianteProducto,(VarianteProducto.producto_id==Producto.id)&(VarianteProducto.empresa_id==company.id))
            .join(Existencia,(Existencia.variante_id==VarianteProducto.id)&(Existencia.empresa_id==company.id))
            .join(Sucursal,(Sucursal.id==Existencia.sucursal_id)&(Sucursal.empresa_id==company.id))
            .where(Producto.empresa_id==company.id,Producto.activo.is_(True),VarianteProducto.activo.is_(True),
                   Sucursal.activo.is_(True),Existencia.cantidad>Existencia.cantidad_comprometida)
            .order_by(Producto.id,Sucursal.id).limit(3)).all()
        promotions=db.scalars(select(Promocion).where(Promocion.empresa_id==company.id)).all()
        stores.append({'tienda':slug,'empresa_activa':company.activo,'plan':plan.codigo if plan else None,
            'suscripcion':subscription_state(sub) if sub else 'AUSENTE',
            'sucursales':count(Sucursal,Sucursal.activo.is_(True)),
            'personal_activo':count(MembresiaEmpresa,MembresiaEmpresa.activo.is_(True)),
            'clientes':count(Cliente,Cliente.activo.is_(True)),
            'roles_personalizados':count(RolEmpresa,RolEmpresa.codigo_sistema.is_(None)),
            'categorias':count(CategoriaProducto), 'prendas':count(Producto,Producto.activo.is_(True)),
            'prendas_sin_imagen':count(Producto,Producto.activo.is_(True),Producto.imagen_url.is_(None)),
            'variantes':count(VarianteProducto,VarianteProducto.activo.is_(True)),
            'saldos_registrados':count(Existencia),
            'existencias_fisicas':db.scalar(select(func.coalesce(func.sum(Existencia.cantidad),0)).where(Existencia.empresa_id==company.id)),
            'movimientos':count(MovimientoInventario),'proveedores':count(Proveedor,Proveedor.activo.is_(True)),
            'ordenes':count(OrdenAbastecimiento),'ordenes_pendientes':count(OrdenAbastecimiento,OrdenAbastecimiento.estado.in_(['PENDIENTE','PARCIAL'])),
            'recepciones':count(RecepcionAbastecimiento),
            'promociones_vigentes':sum(promotion_state(p)=='ACTIVA' for p in promotions),
            'eventos_bitacora':count(EventoAuditoria),
            'compras_historial_simulado':simulation,'compras_otro_origen':len(purchases)-simulation,
            'intentos_stripe':count(CheckoutAttempt),'solicitudes_postventa':count(SolicitudPostventa),
            'ventas_caja_confirmadas':count(CashSale),
            'reservas_confirmadas':count(ReservationRecord,ReservationRecord.estado=='CONFIRMADA'),
            'reservas_atendidas':count(ReservationRecord,ReservationRecord.estado=='ATENDIDA'),
            'conflictos_pendientes':count(SyncIncident,SyncIncident.estado=='CONFLICTO'),
            'deseos':count(Deseo),'visitas_consentidas':count(VistaCU19),
            'compras_entregadas':count(EntregaCompra),'valoraciones':count(ValoracionCompra),
            'alertas_reposicion':count(AlertaReposicion),
            'variantes_vestidor':count(ConfiguracionVestidor,ConfiguracionVestidor.activo.is_(True)),
            'opciones_compra_con_stock':[{'prenda':p,'talla':s,'color':c,'sucursal':b,'disponible':q} for p,s,c,b,q in rows]})
    models=False
    try:load_models();models=True
    except Exception:pass
    return {'comprobado_utc':datetime.now(timezone.utc).isoformat(),'base':'vestinova_pruebas','empresas':stores,
        'configuracion':{'ia_configurada':ai_configured(),'stripe_formato_test':_configuration() is not None,
                         'web_push_configurado':push_enabled(settings),'modelos_cu22_verificados':models}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    use_demo_database()
    settings=Settings.from_env();validate_demo_database_url(settings.database_url)
    engine=build_engine(settings)
    try:
        with build_session_factory(engine)() as db: report=collect(db,settings)
    finally:engine.dispose()
    try:
        with httpx.Client(base_url='http://127.0.0.1:8001',timeout=5) as api:
            health=api.get('/api/health/db')
            report['api_demo']=health.status_code==200 and health.json().get('database')=='vestinova_pruebas'
            report['compra_gateway_generico']=api.get('/api/compras/capacidades').json().get('habilitado',False)
            report['stripe_capacidad_anunciada']=api.get('/api/tiendas/demo-moda-urbana/compras/capacidades').json().get('habilitado',False)
    except Exception:
        report['api_demo']=False
    if args.json:
        print(json.dumps(report,ensure_ascii=False,indent=2));return
    print('VestiNova: preparación de datos en vestinova_pruebas (solo lectura).')
    print('API demo:', 'OK' if report['api_demo'] else 'NO COMPROBADA')
    for store in report['empresas']:
        print('\n'+store['tienda'])
        for key,value in store.items():
            if key!='tienda':print(f'  {key}: {value}')
    print('\nConfiguración:',report['configuracion'])
    print('La presencia de datos/endpoints no acredita un caso completo, una compra pagada ni una prueba de cámara.')
    print('Reservas/caja/sincronización comercial deben distinguirse de sus borradores y dominio aislado.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('No se completó la comprobación: '+type(error).__name__+'. No se muestran credenciales.')
        raise SystemExit(1) from None
