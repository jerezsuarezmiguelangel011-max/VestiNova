"""Importa historial SIMULADO para CU22, solo en vestinova_pruebas local.

Son snapshots históricos de analítica: no ejecutan cobros ni ventas nuevas,
no descuentan inventario actual y no validan los flujos de CU08/CU10/CU17.
La carga es transaccional y repetible por fecha, sucursal y prenda.
"""
import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import MetaData, select

from app.analitica_ia.data_origin import DEMO_HISTORY_ORIGIN
from app.compras_reservas.compras.domain import Purchase, PurchaseCommand, PurchaseContext, PurchaseItem, PurchaseLine
from app.compras_reservas.compras.persistence import PurchaseRecord, add_purchase, _hydrate
from app.config import BACKEND_ROOT, Settings, validate_demo_database_url
from app.db import build_engine, build_session_factory
from app.inventario.domain import InventoryKey
from app.models import Cliente, Empresa, Producto, Sucursal, VarianteProducto
from scripts.demo_environment import use_demo_database

COMPANY_SLUG = "demo-moda-urbana"
PRODUCTS = ("demo-urbana-polera-oversize", "demo-urbana-jean-slim", "demo-urbana-chaqueta-denim")
BRANCHES = ("CENTRO", "NORTE", "SUR")


def seed_history(db, reference: date):
    """Solo altas; el punto de entrada valida primero el motor local demo."""
    company = db.scalar(select(Empresa).where(Empresa.slug == COMPANY_SLUG, Empresa.activo.is_(True)))
    if company is None:
        raise ValueError("Primero prepara Moda Urbana Demo con scripts.seed_demo.")
    customer = db.scalar(select(Cliente).where(Cliente.empresa_id == company.id, Cliente.correo == "cliente.urbana@vestinova.test", Cliente.activo.is_(True)))
    if customer is None:
        raise ValueError("Falta el Cliente Demo Urbana activo; no se crean cuentas ni contraseñas.")
    branches = []
    for code in BRANCHES:
        branch = db.scalar(select(Sucursal).where(Sucursal.empresa_id == company.id, Sucursal.codigo == code, Sucursal.activo.is_(True)))
        if branch is None:
            raise ValueError("Falta una sucursal demo activa; no se modifica su configuración.")
        branches.append(branch)
    products = []
    for slug in PRODUCTS:
        product = db.scalar(select(Producto).where(Producto.empresa_id == company.id, Producto.slug == slug, Producto.activo.is_(True)))
        variant = None if product is None else db.scalar(select(VarianteProducto).where(VarianteProducto.empresa_id == company.id, VarianteProducto.producto_id == product.id, VarianteProducto.activo.is_(True)).order_by(VarianteProducto.id))
        if product is None or variant is None:
            raise ValueError("Falta una prenda/variante demo activa; no se crean ni se alteran prendas.")
        products.append((product, variant))
    created, existing = 0, 0
    for offset in range(14, 0, -1):
        day = reference - timedelta(days=offset)
        for branch_index, branch in enumerate(branches):
            for product_index, (product, variant) in enumerate(products):
                baseline = ((2,1,1), (5,3,2), (1,1,1))[product_index][branch_index]
                quantity = baseline + (1 if product_index == 0 and (day.toordinal()+branch_index) % 3 == 0 else 0)
                identifier = uuid5(NAMESPACE_URL, f"{DEMO_HISTORY_ORIGIN}/{COMPANY_SLUG}/{branch.codigo}/{product.slug}/{day.isoformat()}")
                command = PurchaseCommand(identifier, (PurchaseItem(product.id, quantity),))
                current = db.get(PurchaseRecord, str(identifier))
                if current is not None:
                    hydrated = _hydrate(current)
                    if (current.contexto.get("origen") != DEMO_HISTORY_ORIGIN or hydrated.fingerprint != command.fingerprint
                            or hydrated.context.empresa_id != company.id or hydrated.context.cliente_id != customer.id
                            or hydrated.context.sucursal_id != branch.id):
                        raise ValueError("Conflicto con un historial existente; la carga se cancela sin sobrescribirlo.")
                    existing += 1
                    continue
                context = PurchaseContext(customer.id, company.id, customer.id, branch.id)
                line = PurchaseLine(InventoryKey(company.id, branch.id, variant.id), product.id, product.nombre, quantity, product.precio)
                purchase = Purchase(identifier, context, command.fingerprint, (line,), datetime.combine(day, time(15), timezone.utc))
                add_purchase(db, purchase)
                record = db.get(PurchaseRecord, str(identifier))
                record.contexto = {**record.contexto, "origen": DEMO_HISTORY_ORIGIN,
                    "naturaleza": "HISTORIAL_SIMULADO_PARA_ANALITICA", "inventario": "NO_APLICA_A_SALDOS_ACTUALES"}
                created += 1
    db.flush()
    return {"creadas": created, "existentes": existing, "desde": (reference-timedelta(days=14)).isoformat(), "hasta": (reference-timedelta(days=1)).isoformat()}


def fingerprints(db):
    metadata = MetaData()
    metadata.reflect(db.connection())
    result = {}
    for name, table in metadata.tables.items():
        result[name] = Counter(sha256(json.dumps(list(row), default=str, ensure_ascii=False).encode()).hexdigest()
                               for row in db.execute(select(table)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fecha-referencia", type=date.fromisoformat, default=None, help="YYYY-MM-DD; por defecto hoy UTC. No admite futuro.")
    args = parser.parse_args()
    reference = args.fecha_referencia or datetime.now(timezone.utc).date()
    if reference > datetime.now(timezone.utc).date():
        raise ValueError("La fecha de referencia no puede ser futura.")
    private_file = BACKEND_ROOT / ".env"
    private_hash = sha256(private_file.read_bytes()).digest()
    use_demo_database()
    settings = Settings.from_env()
    validate_demo_database_url(settings.database_url)
    engine = build_engine(settings)
    try:
        with build_session_factory(engine).begin() as db:
            before = fingerprints(db)
            result = seed_history(db, reference)
            after = fingerprints(db)
            for table, rows in before.items():
                if rows - after[table] or (table not in {"compras_digitales", "compras_digitales_lineas"} and rows != after[table]):
                    raise ValueError("La carga intentó alterar datos previos; se cancela la transacción.")
            if sha256(private_file.read_bytes()).digest() != private_hash:
                raise ValueError("La configuración privada cambió; se cancela la carga.")
        print(f"Historial DEMO CU22: {result['creadas']} compras simuladas creadas; {result['existentes']} ya existían.")
        print(f"Fechas UTC: {result['desde']} a {result['hasta']}. Moda Urbana Demo; 3 prendas y 3 sucursales.")
        print("Existencias, movimientos, usuarios, contraseñas, configuración y registros previos conservados.")
        print("No se ejecutaron pagos ni ventas nuevas. vestinova_mvp no se modificó.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        if isinstance(error, ValueError):
            print(str(error))
        else:
            print("No se completó la carga demo. Revisa la base local, migraciones y datos de scripts.seed_demo.")
        raise SystemExit(1) from None
