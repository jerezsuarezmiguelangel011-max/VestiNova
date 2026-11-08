"""Escenario repetible CU19/CU20/CU23 en vestinova_pruebas (nunca en producción).

Simula visitas consentidas a poleras, dos deseos personales y tres comprobantes
ficticios de efectivo con salida de stock. Los datos quedan etiquetados DEMO.
No llama a Stripe ni supone cobros reales. Reejecutar no duplica ventas.
"""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo_publico.historial_recomendaciones import ConsentimientoCU19, VistaCU19
from app.compras_reservas.deseos import Deseo
from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import (
    AccesoSucursal, Administrador, Cliente, Empresa, Existencia, MembresiaEmpresa,
    MovimientoInventario, Producto, Sucursal, VarianteProducto, utc_now,
)
from app.operacion_sin_conexion.caja.online import CashSale
from scripts.demo_environment import use_demo_database
from scripts.seed_fashion_catalog_demo import seed_catalog

STORE_SLUG = "demo-moda-andina"
SCENARIO = "20261108-v1"
WATCHED = (
    ("polera-manga-corta", 5),
    ("polera-deportiva", 4),
    ("camisa-lino", 1),
)
WISHED = (("polera-oversize", "M", "Negro"),
          ("zapatillas-urbanas", "39", "Blanco"))
SALES = (("polera-deportiva", "M", "Azul", 2),
         ("polera-oversize", "L", "Negro", 1),
         ("camisa-lino", "M", "Crema", 1))


def _product(db: Session, company_id: int, code: str) -> Producto:
    row = db.scalar(select(Producto).where(
        Producto.empresa_id == company_id,
        Producto.slug == f"demo-andina-catalogo-{code}",
        Producto.activo.is_(True),
    ))
    if row is None:
        raise ValueError(f"Falta {code}. Ejecuta scripts.seed_fashion_catalog_demo.")
    return row


def _variant(db: Session, company_id: int, code: str,
             size: str, color: str) -> tuple[Producto, VarianteProducto]:
    product = _product(db, company_id, code)
    variant = db.scalar(select(VarianteProducto).where(
        VarianteProducto.empresa_id == company_id,
        VarianteProducto.producto_id == product.id,
        VarianteProducto.talla == size, VarianteProducto.color == color,
        VarianteProducto.activo.is_(True),
    ))
    if variant is None:
        raise ValueError(f"Falta variante demo: {code} {size}/{color}.")
    return product, variant


def seed_scenarios(db: Session) -> dict:
    # Asegurar que los productos estén disponibles sin restablecer stock anterior.
    seed_catalog(db)
    company = db.scalar(select(Empresa).where(
        Empresa.slug == STORE_SLUG, Empresa.activo.is_(True)))
    if company is None:
        raise ValueError("Falta Moda Andina Demo.")
    client = db.scalar(select(Cliente).where(
        Cliente.empresa_id == company.id,
        Cliente.correo == "cliente.andina@vestinova.test", Cliente.activo.is_(True),
    ))
    branch = db.scalar(select(Sucursal).where(
        Sucursal.empresa_id == company.id, Sucursal.codigo == "CENTRO", Sucursal.activo.is_(True),
    ))
    cashier = db.scalar(select(Administrador).join(
        MembresiaEmpresa, MembresiaEmpresa.administrador_id == Administrador.id,
    ).join(AccesoSucursal,
           (AccesoSucursal.administrador_id == Administrador.id)
           & (AccesoSucursal.empresa_id == MembresiaEmpresa.empresa_id)).where(
        Administrador.correo == "cajero.andina@vestinova.test",
        Administrador.activo.is_(True),
        MembresiaEmpresa.empresa_id == company.id,
        MembresiaEmpresa.rol == "CAJERO", MembresiaEmpresa.activo.is_(True),
        AccesoSucursal.sucursal_id == branch.id if branch is not None else False,
    ))
    if client is None or branch is None or cashier is None:
        raise ValueError("Faltan datos de las cuentas demo. Ejecuta scripts.seed_demo.")

    consent = db.get(ConsentimientoCU19, (company.id, client.id))
    if consent is None:
        consent = ConsentimientoCU19(empresa_id=company.id, cliente_id=client.id)
        db.add(consent)
    # Cuenta sintética de demostración. Para usuarios reales solo se
    # activa mediante la pantalla de consentimiento.
    consent.habilitado = True
    consent.actualizado_en = utc_now()

    viewed = []
    for code, views in WATCHED:
        product = _product(db, company.id, code)
        event = db.get(VistaCU19, (company.id, client.id, product.id))
        if event is None:
            db.add(VistaCU19(
                empresa_id=company.id, cliente_id=client.id,
                producto_id=product.id, vistas=views,
                vista_reciente_en=utc_now(),
            ))
        else:
            event.vistas = max(event.vistas, views)
        viewed.append(f"{product.nombre} ×{views}")

    new_wishes = 0
    for code, size, color in WISHED:
        _, variant = _variant(db, company.id, code, size, color)
        if db.get(Deseo, (company.id, client.id, variant.id)) is None:
            db.add(Deseo(empresa_id=company.id, cliente_id=client.id,
                         variante_id=variant.id, creado_en=utc_now()))
            new_wishes += 1

    created_sales = []
    for index, (code, size, color, qty) in enumerate(SALES, start=1):
        product, variant = _variant(db, company.id, code, size, color)
        sale_id = str(uuid5(NAMESPACE_URL,
                            f"vestinova:demo:cu20:{SCENARIO}:{company.id}:{index}"))
        previous = db.get(CashSale, sale_id)
        if previous is not None:
            if previous.empresa_id != company.id or not previous.codigo.startswith("VN-DEMO-CU20-"):
                raise ValueError("Colisión de UUID con un comprobante ajeno.")
            continue
        stock = db.get(Existencia, (company.id, branch.id, variant.id))
        if stock is None or stock.cantidad - stock.cantidad_comprometida < qty:
            raise ValueError(
                f"No hay stock disponible para simular {qty} unidad(es) de {product.nombre} "
                f"en Andina Centro. Ninguna venta de demostración se guardó."
            )
        unit = Decimal(product.precio)
        total = (unit * qty).quantize(Decimal("0.01"))
        stock.cantidad -= qty
        stock.actualizado_en = utc_now()
        move_id = str(uuid5(NAMESPACE_URL, f"vestinova:demo:cu20:mov:{sale_id}:{variant.id}"))
        db.add(MovimientoInventario(
            id=move_id, empresa_id=company.id, sucursal_id=branch.id,
            variante_id=variant.id, usuario_id=cashier.id, cliente_id=None,
            tipo="SALIDA", clase="MOVIMIENTO", origen_tipo=None, origen_id=None,
            motivo="DEMO CU20: venta ficticia para reportes (sin cobro)",
            delta=-qty, saldo_resultante=stock.cantidad,
        ))
        db.add(CashSale(
            id=sale_id, empresa_id=company.id, sucursal_id=branch.id,
            usuario_id=cashier.id, cliente_id=None,
            huella=sha256(f"demo:{sale_id}".encode()).hexdigest(),
            lineas=[{
                "variante_id": variant.id, "producto_id": product.id,
                "nombre": product.nombre, "cantidad": qty,
                "precio_unitario": f"{unit:.2f}",
                "subtotal": f"{total:.2f}",
                "movimiento_id": move_id,
            }],
            total=total, efectivo=total, cambio=Decimal("0.00"),
            codigo=f"VN-DEMO-CU20-{index:02d}", origen="EN_LINEA",
            creada_local_en=None, entrega_local=False,
            confirmada_en=utc_now(),
        ))
        created_sales.append(f"{qty} × {product.nombre} ({color}), Bs {total:.2f}")

    return {
        "empresa": company.slug,
        "cliente": client.correo,
        "sucursal": branch.nombre,
        "vistas": viewed,
        "deseos_nuevos": new_wishes,
        "ventas_nuevas": created_sales,
    }


def main():
    use_demo_database()  # Verifica entorno local y el destino vestinova_pruebas.
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine).begin() as db:
            summary = seed_scenarios(db)
        print("ESCENARIOS CU19/CU20/CU23 PREPARADOS (SOLO vestinova_pruebas)")
        print("  Cliente demo:", summary["cliente"])
        print("  CU19 - Historial de vistas ficticias:")
        for line in summary["vistas"]:
            print("   -", line)
        print("  CU20 - Nuevas ventas DEMO de efectivo (SIN COBROS REALES):")
        for line in summary["ventas_nuevas"]:
            print("   -", line)
        print("  CU23 - Deseos nuevos:", summary["deseos_nuevos"])
        print("  Sucursal reportada:", summary["sucursal"])
        print("El script es repetible: no duplica ventas ni compromete compras reales.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print("No pudo completarse la preparación demo:", error)
        raise SystemExit(1) from None
