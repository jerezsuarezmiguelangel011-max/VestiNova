"""Dos prendas masculinas ilustrativas, exclusivas de vestinova_pruebas local."""
from hashlib import sha256
from sqlalchemy import select
from app.config import BACKEND_ROOT, Settings, validate_demo_database_url
from app.db import build_engine, build_session_factory
from app.models import Empresa, Producto, VarianteProducto
from app.vestidor_virtual.api import ASSET_PREFIX
from app.vestidor_virtual.models import ConfiguracionVestidor
from scripts.demo_environment import use_demo_database
from scripts.seed_analytics_history import fingerprints


def seed(db):
    company=db.scalar(select(Empresa).where(Empresa.slug=='demo-moda-urbana',Empresa.activo.is_(True)))
    if company is None:
        raise ValueError('Falta Moda Urbana Demo; prepara primero scripts.seed_demo.')
    count=0
    for slug,name,kind,price,variants in [
        ('demo-vestidor-polera-varon','Polera masculina · Vestidor demo','POLERA','119.00',[('M','Gris','polera-gris.png'),('L','Gris','polera-gris.png'),('L','Azul marino','polera-azul.png')]),
        ('demo-vestidor-camisa-varon','Camisa masculina · Vestidor demo','CAMISA','169.00',[('M','Celeste','camisa-azul.png'),('L','Blanco','camisa-blanca.png')])]:
        product=db.scalar(select(Producto).where(Producto.slug==slug))
        if product is None:
            product=Producto(empresa_id=company.id,slug=slug,nombre=name,precio=price,
                descripcion='Prenda de demostración del vestidor masculino. Imágenes ilustrativas; no es una fotografía de mercancía ni garantiza ajuste físico.',activo=True)
            db.add(product);db.flush()
        elif product.empresa_id != company.id:
            raise ValueError('Conflicto de empresa en el identificador demo; no se sobrescribe.')
        for size,color,asset in variants:
            variant=db.scalar(select(VarianteProducto).where(VarianteProducto.empresa_id==company.id,VarianteProducto.producto_id==product.id,VarianteProducto.talla==size,VarianteProducto.color==color))
            if variant is None:
                variant=VarianteProducto(empresa_id=company.id,producto_id=product.id,talla=size,color=color,activo=True)
                db.add(variant);db.flush()
            config=db.get(ConfiguracionVestidor,variant.id)
            if config is None:
                db.add(ConfiguracionVestidor(variante_id=variant.id,empresa_id=company.id,recurso_url=ASSET_PREFIX+asset,tipo_prenda=kind,factor_ancho=2.1,factor_alto=1.35,offset_x=0,offset_y=0,activo=True));count+=1
    db.flush()
    return count


def main():
    private=BACKEND_ROOT/'.env'
    private_hash=sha256(private.read_bytes()).digest()
    use_demo_database()
    settings=Settings.from_env();validate_demo_database_url(settings.database_url)
    engine=build_engine(settings)
    try:
        with build_session_factory(engine).begin() as db:
            before=fingerprints(db)
            count=seed(db)
            after=fingerprints(db)
            for table,rows in before.items():
                if rows-after[table] or (table not in {'productos','variantes_producto','configuraciones_vestidor'} and rows!=after[table]):
                    raise ValueError('La carga intentó alterar datos anteriores; se cancela.')
            if sha256(private.read_bytes()).digest()!=private_hash:
                raise ValueError('La configuración privada cambió; se cancela.')
        print(f'Vestidor masculino demo: {count} configuraciones nuevas. Repetir no duplica ni sobrescribe.')
        print('Dos prendas demo independientes; no se alteran las prendas de CU22, existencias, compras, cuentas ni .env.')
        print('Solo vestinova_pruebas. Las imágenes son ilustraciones propias, identificadas como demostración.')
    finally:
        engine.dispose()


if __name__=='__main__':
    try:
        main()
    except Exception:
        print('No se completó la carga. Revisa base demo, migraciones y prendas existentes; no se muestran credenciales.')
        raise SystemExit(1) from None
