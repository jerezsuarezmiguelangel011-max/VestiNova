"""Enriquece SOLO vestinova_pruebas sin recrear tablas ni usuarios.

Uso: python -m scripts.seed_showcase_demo
- Seguro al repetir: alta por claves estables, no cambia inventario existente.
- Solo agrega prendas faltantes y completa imágenes vacías de productos demo.
- Ilustraciones SVG originales servidas desde frontend/public/demo-fashion.
- No registra pedidos, cobros, contraseñas ni reservas inventadas.
"""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import (
    Administrador, CategoriaProducto, Empresa, Existencia, MembresiaEmpresa,
    MovimientoInventario, PlanSaaS, Producto, Promocion, PromocionProducto,
    Sucursal, SuscripcionEmpresa, VarianteProducto, utc_now,
)
from app.organizacion_empresarial.plans import subscription_state
from scripts.demo_environment import use_demo_database


# Colección original para probar UI, no marcas ni fotografías de comercios reales.
# slug, nombre, categoría, precio BOB, tipo ilustración, color 1, color 2, unidades iniciales.
SHOWCASE = {
    "demo-moda-andina": (
        ("blusa-lino", "Blusa de lino natural", "Camisas", "139.00", "camisa", "Beige", "Blanco", 12),
        ("polera-canale", "Polera de canalé", "Poleras", "99.00", "polera", "Crema", "Verde", 14),
        ("jean-amplio", "Jean corte amplio", "Jeans", "219.00", "jean", "Azul", "Negro", 10),
        ("chaqueta-ligera", "Chaqueta ligera urbana", "Chaquetas", "259.00", "chaqueta", "Oliva", "Arena", 6),
        ("vestido-midi", "Vestido midi suave", "Vestidos", "249.00", "vestido", "Rosa", "Beige", 9),
        ("falda-plisada", "Falda plisada clásica", "Faldas", "149.00", "falda", "Azul", "Crema", 13),
        ("camisa-recta", "Camisa recta de algodón", "Camisas", "169.00", "camisa", "Blanco", "Celeste", 11),
        ("polera-basica", "Polera básica esencial", "Poleras", "79.00", "polera", "Gris", "Negro", 20),
        ("jean-claro", "Jean azul claro", "Jeans", "199.00", "jean", "Celeste", "Azul", 8),
        ("chaqueta-abrigo", "Chaqueta de abrigo", "Chaquetas", "299.00", "chaqueta", "Marrón", "Negro", 5),
        ("vestido-casual", "Vestido casual diario", "Vestidos", "189.00", "vestido", "Verde", "Negro", 11),
        ("falda-denim", "Falda denim", "Faldas", "159.00", "falda", "Azul", "Negro", 9),
    ),
    "demo-moda-urbana": (
        ("polera-grafica", "Polera de corte gráfico", "Poleras", "129.00", "polera", "Negro", "Blanco", 15),
        ("jean-relajado", "Jean de corte relajado", "Jeans", "229.00", "jean", "Azul", "Negro", 11),
        ("chaqueta-boxy", "Chaqueta boxy", "Chaquetas", "319.00", "chaqueta", "Gris", "Negro", 7),
        ("camisa-urbana", "Camisa urbana", "Camisas", "199.00", "camisa", "Blanco", "Oliva", 12),
        ("vestido-minimal", "Vestido minimalista", "Vestidos", "239.00", "vestido", "Negro", "Arena", 8),
        ("falda-cargo", "Falda cargo", "Faldas", "189.00", "falda", "Oliva", "Gris", 9),
        ("polera-regular", "Polera regular", "Poleras", "109.00", "polera", "Crema", "Negro", 16),
        ("jean-oscuro", "Jean azul oscuro", "Jeans", "259.00", "jean", "Azul", "Negro", 10),
        ("chaqueta-bomber", "Chaqueta bomber", "Chaquetas", "369.00", "chaqueta", "Negro", "Verde", 6),
        ("camisa-oversize", "Camisa oversize", "Camisas", "189.00", "camisa", "Celeste", "Gris", 13),
        ("vestido-recto", "Vestido de corte recto", "Vestidos", "219.00", "vestido", "Beige", "Negro", 8),
        ("falda-corta", "Falda corta urbana", "Faldas", "169.00", "falda", "Gris", "Negro", 11),
    ),
}

ORIGINAL_DEMO_IMAGES = {
    "demo-andina-polera-clasica": "polera",
    "demo-andina-jean-recto": "jean",
    "demo-andina-chaqueta-corta": "chaqueta",
    "demo-urbana-polera-oversize": "polera",
    "demo-urbana-jean-slim": "jean",
    "demo-urbana-chaqueta-denim": "chaqueta",
}
IMAGE_PREFIX = "http://127.0.0.1:4201/demo-fashion/"


def _image(kind: str) -> str:
    if kind not in {"polera", "jean", "chaqueta", "camisa", "vestido", "falda"}:
        raise ValueError("Ilustración de demostración desconocida.")
    return IMAGE_PREFIX + kind + ".svg"


def add_showcase(db) -> dict[str, dict[str, int]]:
    """Transacción controlada por el llamador; nunca edita existencias ya registradas."""
    report: dict[str, dict[str, int]] = {}
    for slug, items in SHOWCASE.items():
        company = db.scalar(select(Empresa).where(Empresa.slug == slug, Empresa.activo.is_(True)))
        if company is None:
            raise ValueError("Falta una empresa demo activa. Ejecuta primero scripts.seed_demo.")
        subscription = db.scalar(select(SuscripcionEmpresa).where(SuscripcionEmpresa.empresa_id == company.id))
        plan = db.get(PlanSaaS, subscription.plan_id) if subscription is not None else None
        if plan is None or not plan.activo or subscription_state(subscription) != "ACTIVA":
            raise ValueError("Una empresa demo no tiene una suscripción activa.")
        tag = "andina" if slug.endswith("andina") else "urbana"
        admin = db.scalar(select(Administrador).join(MembresiaEmpresa).where(
            Administrador.correo == f"admin.{tag}@vestinova.test",
            MembresiaEmpresa.empresa_id == company.id,
            MembresiaEmpresa.activo.is_(True),
        ))
        if admin is None:
            raise ValueError("Falta un administrador demo de esta empresa.")
        branches = db.scalars(select(Sucursal).where(
            Sucursal.empresa_id == company.id, Sucursal.activo.is_(True))
            .order_by(Sucursal.id)).all()
        if not branches:
            raise ValueError("No hay sucursales activas para el catálogo demo.")
        categories = {
            row.nombre_clave: row for row in db.scalars(select(CategoriaProducto).where(
                CategoriaProducto.empresa_id == company.id)).all()
        }
        existing_products = db.scalar(select(func.count()).select_from(Producto).where(
            Producto.empresa_id == company.id, Producto.activo.is_(True))) or 0
        pending = [record for record in items if db.scalar(select(Producto.id).where(
            Producto.slug == f"demo-{tag}-vitrina-{record[0]}")) is None]
        if plan.max_productos is not None and existing_products + len(pending) > plan.max_productos:
            raise ValueError("La vitrina supera el cupo de productos del plan; no se alteró ningún dato.")

        created = 0
        added_stock = 0
        for item_slug, name, category, price, image, color_a, color_b, quantity in items:
            category_key = category.casefold()
            cat = categories.get(category_key)
            if cat is None:
                cat = CategoriaProducto(
                    empresa_id=company.id, nombre=category, nombre_clave=category_key,
                    descripcion="Categoría de la vitrina de prueba", activo=True)
                db.add(cat)
                db.flush()
                categories[category_key] = cat

            product_slug = f"demo-{tag}-vitrina-{item_slug}"
            product = db.scalar(select(Producto).where(Producto.slug == product_slug))
            if product is None:
                product = Producto(
                    empresa_id=company.id, categoria_id=cat.id, slug=product_slug,
                    nombre=name, descripcion="Prenda de la colección ilustrativa VestiNova. Consulta las variantes y el stock de cada sucursal.",
                    material="Textil de demostración", medidas="Consultar la talla de cada variante",
                    temporada="Colección demo", precio=Decimal(price), moneda="BOB",
                    imagen_url=_image(image), activo=True)
                db.add(product)
                db.flush()
                created += 1
            elif product.empresa_id != company.id:
                raise ValueError("Un slug del catálogo demo ya pertenece a otra empresa.")

            for index, (size, color) in enumerate((("S", color_a), ("M", color_a), ("L", color_b))):
                variant = db.scalar(select(VarianteProducto).where(
                    VarianteProducto.empresa_id == company.id,
                    VarianteProducto.producto_id == product.id,
                    VarianteProducto.talla == size, VarianteProducto.color == color))
                if variant is None:
                    variant = VarianteProducto(
                        empresa_id=company.id, producto_id=product.id,
                        talla=size, color=color, activo=True)
                    db.add(variant)
                    db.flush()

                for position, branch in enumerate(branches):
                    existing = db.get(Existencia, (company.id, branch.id, variant.id))
                    if existing is not None:
                        continue
                    stock = max(0, quantity - index * 3 - position * 2)
                    db.add(Existencia(
                        empresa_id=company.id, sucursal_id=branch.id,
                        variante_id=variant.id, cantidad=stock,
                        cantidad_comprometida=0, actualizado_en=utc_now()))
                    if stock > 0:
                        db.add(MovimientoInventario(
                            id=str(uuid4()), empresa_id=company.id,
                            sucursal_id=branch.id, variante_id=variant.id,
                            usuario_id=admin.id, cliente_id=None,
                            tipo="ENTRADA", clase="MOVIMIENTO",
                            motivo="Carga inicial de la vitrina demo",
                            delta=stock, saldo_resultante=stock))
                        added_stock += 1

        # Completar SOLO ilustraciones ausentes en los seis productos originales
        # del seed de demostración. No tocar atributos ni imágenes ya existentes.
        illustrated = 0
        for original_slug, image in ORIGINAL_DEMO_IMAGES.items():
            if not original_slug.startswith(f"demo-{tag}-"):
                continue
            existing = db.scalar(select(Producto).where(
                Producto.slug == original_slug, Producto.empresa_id == company.id))
            if existing is not None and existing.imagen_url is None:
                existing.imagen_url = _image(image)
                illustrated += 1

        # Promociones demo nuevas y estables; nunca edita vigencias de promociones existentes.
        for i, item in enumerate(items[:3]):
            name = f"DEMO Vitrina {tag.title()} - Oferta {i + 1}"
            promo = db.scalar(select(Promocion).where(
                Promocion.empresa_id == company.id, Promocion.nombre == name))
            if promo is None:
                now = utc_now()
                promo = Promocion(
                    empresa_id=company.id, nombre=name,
                    tipo="PORCENTAJE", valor=Decimal(str(10 + 5 * i)),
                    inicio=now - timedelta(days=1), fin=now + timedelta(days=90),
                    activo=True)
                db.add(promo)
                db.flush()
            product = db.scalar(select(Producto).where(
                Producto.empresa_id == company.id,
                Producto.slug == f"demo-{tag}-vitrina-{item[0]}"))
            relation = db.get(PromocionProducto, (company.id, promo.id, product.id))
            if relation is None:
                db.add(PromocionProducto(
                    empresa_id=company.id, promocion_id=promo.id,
                    producto_id=product.id))

        report[slug] = {"productos_nuevos": created,
                        "saldos_nuevos": added_stock,
                        "imagenes_demo_completadas": illustrated}
    db.flush()
    return report


def main() -> None:
    # Valida el destino y fija APP_ENV=demo, sin abrir vestinova_mvp.
    use_demo_database()
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine).begin() as db:
            report = add_showcase(db)
        print("Vitrina demo preparada en vestinova_pruebas.")
        for slug, results in report.items():
            print(f"  {slug}: {results}")
        print("Solo altas ausentes; no se modificaron contraseñas ni saldos existentes.")
        print("Ilustraciones locales originales: inicia Angular en http://127.0.0.1:4201.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
