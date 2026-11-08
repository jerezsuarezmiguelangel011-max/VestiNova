"""Amplía el catálogo de las dos tiendas demo sin borrar operaciones existentes.

Uso, desde backend:
    .\\.venv\\Scripts\\python.exe -m scripts.seed_fashion_catalog_demo

Solo afecta a la base local vestinova_pruebas. No crea compras ni reservas.
Es idempotente: no sobrescribe existencias, precios ni variantes ya creados.
Las categorías son planas en el modelo actual; el subtipo está en el nombre
y la descripción de la prenda, sin simular jerarquías inexistentes.
"""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import (
    Administrador, CategoriaProducto, Empresa, Existencia, MembresiaEmpresa,
    MovimientoInventario, Producto, Sucursal, VarianteProducto,
)
from scripts.demo_environment import use_demo_database


# Categorías generales; no son categorías hijas de otras categorías.
GROUPS = {
    "Poleras": "Poleras de manga corta, manga larga, deportivas y oversize.",
    "Camisas": "Camisas de vestir, casuales y de lino.",
    "Pantalones": "Jeans, pantalones de vestir, cargo y joggers.",
    "Abrigos": "Chompas, chaquetas, blazers y prendas de invierno.",
    "Calzado": "Zapatillas, botines, zapatos formales y sandalias.",
    "Accesorios": "Gorras, chalinas, billeteras, cinturones y sombreros.",
}

# código, nombre, categoría general, subtipo, material, temporada,
# precio Andina, grupo de tallas, colores, inventario habitual aproximado.
STYLES = (
    ("polera-manga-corta", "Polera básica manga corta", "Poleras", "Manga corta", "Algodón", "Todo el año", "79.00", "superior", ("Blanco", "Negro"), 10),
    ("polera-oversize", "Polera oversize lisa", "Poleras", "Oversize", "Algodón", "Todo el año", "112.00", "superior", ("Negro", "Crema"), 8),
    ("polera-deportiva", "Polera deportiva liviana", "Poleras", "Deportiva", "Poliéster", "Verano", "99.00", "superior", ("Azul", "Gris"), 7),
    ("polera-manga-larga", "Polera manga larga", "Poleras", "Manga larga", "Algodón", "Invierno", "109.00", "superior", ("Blanco", "Verde"), 9),

    ("camisa-formal", "Camisa formal lisa", "Camisas", "Formal", "Algodón", "Todo el año", "169.00", "superior", ("Blanco", "Celeste"), 7),
    ("camisa-lino", "Camisa de lino natural", "Camisas", "Lino", "Lino", "Verano", "189.00", "superior", ("Crema", "Blanco"), 8),
    ("camisa-cuadros", "Camisa casual a cuadros", "Camisas", "Casual a cuadros", "Algodón", "Invierno", "159.00", "superior", ("Azul", "Rojo"), 7),
    ("camisa-manga-corta", "Camisa manga corta tropical", "Camisas", "Manga corta", "Viscosa", "Verano", "139.00", "superior", ("Verde", "Beige"), 9),

    ("jean-wide-leg", "Jean relaxed fit masculino", "Pantalones", "Jean amplio", "Denim", "Todo el año", "209.00", "pantalon", ("Azul", "Negro"), 8),
    ("pantalon-cargo", "Pantalón cargo urbano", "Pantalones", "Cargo", "Gabardina", "Todo el año", "199.00", "pantalon", ("Verde", "Negro"), 7),
    ("pantalon-sastre", "Pantalón de vestir", "Pantalones", "Sastre", "Poliéster", "Todo el año", "229.00", "pantalon", ("Gris", "Negro"), 6),
    ("pantalon-jogger", "Pantalón jogger cómodo", "Pantalones", "Jogger", "Algodón", "Invierno", "149.00", "pantalon", ("Negro", "Gris"), 10),
    ("pantalon-chino", "Pantalón chino casual", "Pantalones", "Chino", "Gabardina", "Todo el año", "179.00", "pantalon", ("Beige", "Azul"), 7),

    ("chompa-tejida", "Chompa tejida cuello redondo", "Abrigos", "Chompa tejida", "Acrílico", "Invierno", "179.00", "superior", ("Beige", "Gris"), 7),
    ("chaqueta-bomber", "Chaqueta bomber urbana", "Abrigos", "Bomber", "Poliéster", "Invierno", "269.00", "superior", ("Negro", "Verde"), 0),
    ("blazer-casual", "Blazer casual", "Abrigos", "Blazer", "Poliéster", "Todo el año", "299.00", "superior", ("Azul", "Negro"), 6),
    ("parka-liviana", "Parka liviana impermeable", "Abrigos", "Parka", "Poliéster", "Invierno", "329.00", "superior", ("Negro", "Beige"), 0),

    ("zapatillas-urbanas", "Zapatillas urbanas", "Calzado", "Zapatillas", "Textil", "Todo el año", "239.00", "calzado", ("Blanco", "Negro"), 8),
    ("botines-temporada", "Botines de temporada", "Calzado", "Botines", "Sintético", "Invierno", "289.00", "calzado", ("Negro", "Marrón"), 5),
    ("zapatos-vestir", "Zapatos de vestir", "Calzado", "Zapato formal", "Sintético", "Todo el año", "269.00", "calzado", ("Negro", "Marrón"), 5),
    ("sandalias-casuales", "Sandalias casuales", "Calzado", "Sandalias", "Sintético", "Verano", "149.00", "calzado", ("Negro", "Beige"), 8),

    ("gorra-lisa", "Gorra clásica lisa", "Accesorios", "Gorra", "Algodón", "Verano", "59.00", "unica", ("Negro", "Azul"), 12),
    ("chalina-tejida", "Chalina tejida", "Accesorios", "Chalina", "Acrílico", "Invierno", "69.00", "unica", ("Gris", "Beige"), 8),
    ("billetera-clasica", "Billetera clásica de hombre", "Accesorios", "Billetera", "Cuero sintético", "Todo el año", "89.00", "unica", ("Negro", "Marrón"), 7),
    ("cinturon-clasico", "Cinturón clásico", "Accesorios", "Cinturón", "Sintético", "Todo el año", "79.00", "unica", ("Negro", "Marrón"), 9),
    ("sombrero-flexible", "Sombrero de ala flexible", "Accesorios", "Sombrero", "Textil", "Verano", "89.00", "unica", ("Beige", "Negro"), 6),
)

# Fotografías de referencia para catálogo ficticio. Pexels (licencia gratuita).
# No son fotografías de inventario real ni representan el color exacto de
# todas las variantes. URLs HTTPS con compresión y ancho limitados para demo.
PHOTO_IDS = {
    "polera-manga-corta": 8979899,
    "polera-oversize": 28758240,
    "polera-deportiva": 9759713,
    "polera-manga-larga": 12738120,
    "camisa-formal": 4061725,
    "camisa-lino": 5191436,
    "camisa-cuadros": 9929712,
    "camisa-manga-corta": 7433128,
    "jean-wide-leg": 16069737,
    "pantalon-cargo": 19751093,
    "pantalon-sastre": 33633245,
    "pantalon-jogger": 19461557,
    "pantalon-chino": 7433128,
    "chompa-tejida": 16684688,
    "chaqueta-bomber": 23363491,
    "blazer-casual": 30875756,
    "parka-liviana": 9929712,
    "zapatillas-urbanas": 11757389,
    "botines-temporada": 26851197,
    "zapatos-vestir": 17286664,
    "sandalias-casuales": 12896849,
    "gorra-lisa": 3649521,
    "chalina-tejida": 7870646,
    "billetera-clasica": 4452390,
    "cinturon-clasico": 26851197,
    "sombrero-flexible": 19780087,
}
PRIOR_PHOTO_IDS = {
    "polera-manga-corta": 9775901,
    "polera-oversize": 17583618,
    "polera-deportiva": 9759713,
    "polera-manga-larga": 28079564,
    "camisa-formal": 5289086,
    "camisa-lino": 18240957,
    "camisa-cuadros": 36856701,
    "camisa-manga-corta": 3927390,
    "jean-wide-leg": 3944690,
    "pantalon-cargo": 17893807,
    "pantalon-sastre": 37691114,
    "pantalon-jogger": 3927390,
    "pantalon-chino": 20777875,
    "chompa-tejida": 5499129,
    "chaqueta-bomber": 6037957,
    "blazer-casual": 5289086,
    "parka-liviana": 10530089,
    "zapatillas-urbanas": 11962269,
    "botines-temporada": 8428528,
    "zapatos-vestir": 7289741,
    "sandalias-casuales": 36937550,
    "gorra-lisa": 3927390,
    "chalina-tejida": 8818150,
    "bolso-cruzado": 8502477,
    "cinturon-clasico": 26851197,
    "sombrero-flexible": 11446623,
}
PHOTO_LEGACY = {
    "polera-clasica": 8979899,
    "jean-recto": 16069737,
    "chaqueta-corta": 23363491,
    "polera-oversize": 28758240,
    "jean-slim": 16069737,
    "chaqueta-denim": 16277449,
}
PRIOR_PHOTO_LEGACY = {
    "polera-clasica": 9775901,
    "jean-recto": 3944690,
    "chaqueta-corta": 5499129,
    "polera-oversize": 17583618,
    "jean-slim": 33516576,
    "chaqueta-denim": 6037957,
}


def photo_url(photo_id: int) -> str:
    return (f"https://images.pexels.com/photos/{photo_id}/"
            f"pexels-photo-{photo_id}.jpeg?auto=compress&cs=tinysrgb&w=640")


SIZES = {
    "superior": ("S", "M", "L"),
    "pantalon": ("38", "40", "42"),
    "calzado": ("37", "39", "41"),
    "unica": ("Única",),
}

DEMO_STORES = (
    ("demo-moda-andina", "andina", "Andina", Decimal("0.00"), ("CENTRO", "NORTE")),
    ("demo-moda-urbana", "urbana", "Urbana", Decimal("12.00"), ("CENTRO", "NORTE", "SUR")),
)

LEGACY_CATEGORIES = {
    "jean-recto": ("Jeans", "Pantalones"),
    "jean-slim": ("Jeans", "Pantalones"),
    "chaqueta-corta": ("Chaquetas", "Abrigos"),
    "chaqueta-denim": ("Chaquetas", "Abrigos"),
}


def _ensure_category(db: Session, company_id: int, name: str, description: str) -> CategoriaProducto:
    category = db.scalar(select(CategoriaProducto).where(
        CategoriaProducto.empresa_id == company_id,
        CategoriaProducto.nombre_clave == name.casefold(),
    ))
    if category is None:
        category = CategoriaProducto(
            empresa_id=company_id, nombre=name, nombre_clave=name.casefold(),
            descripcion=description, activo=True,
        )
        db.add(category)
        db.flush()
    if not category.activo:
        raise ValueError(f"La categoría {name} está desactivada en la empresa demo.")
    return category


def _reclassify_legacy(db: Session, company_id: int, tag: str,
                       categories: dict[str, CategoriaProducto]) -> int:
    """Corrige solo cuatro referencias originales, sin tocar ventas ni stock."""
    changed = 0
    for suffix, (old, new) in LEGACY_CATEGORIES.items():
        product = db.scalar(select(Producto).where(
            Producto.slug == f"demo-{tag}-{suffix}",
            Producto.empresa_id == company_id,
        ))
        if product is None or product.categoria_id is None:
            continue
        old_category = db.get(CategoriaProducto, product.categoria_id)
        if old_category is not None and old_category.empresa_id == company_id \
                and old_category.nombre_clave == old.casefold():
            product.categoria_id = categories[new].id
            changed += 1

    # Las categorías antiguas se desactivan solo si no guardan ningún producto,
    # respetando categorías que el usuario ya haya utilizado en sus pruebas.
    db.flush()
    for name in ("Jeans", "Chaquetas"):
        category = db.scalar(select(CategoriaProducto).where(
            CategoriaProducto.empresa_id == company_id,
            CategoriaProducto.nombre_clave == name.casefold(),
        ))
        if category is not None and category.activo:
            count = db.scalar(select(func.count()).select_from(Producto).where(
                Producto.empresa_id == company_id,
                Producto.categoria_id == category.id,
            )) or 0
            if count == 0:
                category.activo = False
    return changed


def _stock_for(style_idx: int, variant_idx: int, branch_idx: int,
               baseline: int) -> int:
    if baseline == 0:
        return 0
    signature = (style_idx * 7 + variant_idx * 5 + branch_idx * 3)
    if signature % 13 == 0:
        return 0
    if signature % 11 == 0:
        return 1
    return max(2, baseline + signature % 5 - branch_idx * 2)


def seed_catalog(db: Session) -> list[dict]:
    """Pobla solo datos demo identificados; no hace commit fuera del llamador."""
    summaries = []
    for slug, tag, line, price_extra, expected_codes in DEMO_STORES:
        company = db.scalar(select(Empresa).where(Empresa.slug == slug, Empresa.activo.is_(True)))
        if company is None:
            raise ValueError(f"Falta {slug}: ejecuta scripts.seed_demo primero.")
        branches = db.scalars(select(Sucursal).where(
            Sucursal.empresa_id == company.id, Sucursal.activo.is_(True),
            Sucursal.codigo.in_(expected_codes),
        ).order_by(Sucursal.codigo)).all()
        if {branch.codigo for branch in branches} != set(expected_codes):
            raise ValueError(f"Faltan sucursales de {slug}; ejecuta scripts.seed_demo primero.")
        admin_id = db.scalar(select(Administrador.id).join(
            MembresiaEmpresa, MembresiaEmpresa.administrador_id == Administrador.id,
        ).where(
            Administrador.correo == f"admin.{tag}@vestinova.test",
            Administrador.activo.is_(True),
            MembresiaEmpresa.empresa_id == company.id,
            MembresiaEmpresa.rol == "ADMINISTRADOR",
            MembresiaEmpresa.activo.is_(True),
        ))
        if admin_id is None:
            raise ValueError(f"Falta Administrador Demo {line} para registrar inventario inicial.")

        categories = {
            name: _ensure_category(db, company.id, name, description)
            for name, description in GROUPS.items()
        }
        relabeled = _reclassify_legacy(db, company.id, tag, categories)
        # Retirar el bolso de la versión anterior del catálogo público de
        # hombre, conservando sus registros de inventario, ventas y deseos.
        previous_bag = db.scalar(select(Producto).where(
            Producto.empresa_id == company.id,
            Producto.slug == f"demo-{tag}-catalogo-bolso-cruzado",
        ))
        if previous_bag is not None and previous_bag.nombre == f"Bolso cruzado · {line}":
            previous_bag.activo = False
        # Los productos de la semilla original conservan sus datos salvo que
        # no tengan fotografía asignada y se complete solo ese campo.
        for code, photo_id in PHOTO_LEGACY.items():
            original = db.scalar(select(Producto).where(
                Producto.empresa_id == company.id,
                Producto.slug == f"demo-{tag}-{code}",
            ))
            if original is not None and (
                original.imagen_url is None
                or original.imagen_url == photo_url(PRIOR_PHOTO_LEGACY[code])
            ):
                original.imagen_url = photo_url(photo_id)
        inserted = {"productos": 0, "variantes": 0, "existencias": 0,
                    "movimientos": 0, "imagenes": 0}
        for index, (code, title, category, subtype, material, season, price,
                    sizing, colors, base_stock) in enumerate(STYLES):
            product_slug = f"demo-{tag}-catalogo-{code}"
            product = db.scalar(select(Producto).where(Producto.slug == product_slug))
            if product is None:
                product = Producto(
                    empresa_id=company.id, categoria_id=categories[category].id,
                    slug=product_slug, nombre=f"{title} · {line}",
                    descripcion=(f"Moda masculina. Tipo de prenda: {subtype}. Colección de demostración "
                                 f"{line} para explorar modelos, colores, tallas y sucursales. "
                                 "Los precios y el inventario son datos ficticios."),
                    material=material, temporada=season,
                    medidas="Tallas disponibles: " + ", ".join(SIZES[sizing]),
                    precio=Decimal(price) + price_extra, moneda="BOB",
                    imagen_url=photo_url(PHOTO_IDS[code]), activo=True,
                )
                db.add(product)
                db.flush()
                inserted["productos"] += 1
            elif product.empresa_id != company.id:
                raise ValueError(f"Colisión de identificador de producto demo: {product_slug}.")
            # Reemplazar SOLO la URL de la semilla vieja o una vacía.
            # Las imágenes modificadas manualmente permanecen intactas.
            previous_photo = PRIOR_PHOTO_IDS.get(code)
            if (product.imagen_url is None or (
                previous_photo is not None
                and product.imagen_url == photo_url(previous_photo)
            )) and product.imagen_url != photo_url(PHOTO_IDS[code]):
                product.imagen_url = photo_url(PHOTO_IDS[code])
                inserted["imagenes"] += 1
            if code == "jean-wide-leg" and product.nombre == f"Jean corte amplio · {line}":
                product.nombre = f"{title} · {line}"

            for size_index, size in enumerate(SIZES[sizing]):
                for color_index, color in enumerate(colors):
                    variant = db.scalar(select(VarianteProducto).where(
                        VarianteProducto.empresa_id == company.id,
                        VarianteProducto.producto_id == product.id,
                        VarianteProducto.talla == size, VarianteProducto.color == color,
                    ))
                    if variant is None:
                        variant = VarianteProducto(
                            empresa_id=company.id, producto_id=product.id,
                            talla=size, color=color, activo=True,
                        )
                        db.add(variant)
                        db.flush()
                        inserted["variantes"] += 1
                    variation = size_index * len(colors) + color_index
                    for branch_index, branch in enumerate(branches):
                        existing = db.get(Existencia, (company.id, branch.id, variant.id))
                        if existing is not None:
                            continue  # Nunca restablecer una venta, reserva o ajuste.
                        stock = _stock_for(index, variation, branch_index, base_stock)
                        db.add(Existencia(
                            empresa_id=company.id, sucursal_id=branch.id,
                            variante_id=variant.id, cantidad=stock,
                            cantidad_comprometida=0,
                        ))
                        inserted["existencias"] += 1
                        if stock > 0:
                            db.add(MovimientoInventario(
                                id=str(uuid4()), empresa_id=company.id,
                                sucursal_id=branch.id, variante_id=variant.id,
                                usuario_id=admin_id, cliente_id=None,
                                tipo="ENTRADA", clase="MOVIMIENTO",
                                origen_tipo=None, origen_id=None,
                                motivo="CU04 - Semilla ampliada demo: alta de inventario inicial",
                                delta=stock, saldo_resultante=stock,
                            ))
                            inserted["movimientos"] += 1
        db.flush()
        summaries.append({
            "tienda": slug, "sucursales": len(branches),
            "categorias": len(categories), "catalogo_estilos": len(STYLES),
            "productos_anteriores_reclasificados": relabeled, **inserted,
        })
    return summaries


def main() -> None:
    use_demo_database()  # Solo PostgreSQL local vestinova_pruebas.
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine).begin() as db:
            results = seed_catalog(db)
        print("Catálogo de demostración ampliado en vestinova_pruebas.")
        print("No se ha modificado vestinova_mvp.")
        for result in results:
            print(f"  {result['tienda']}: {result['sucursales']} sucursales; "
                  f"{result['categorias']} grupos; "
                  f"{result['catalogo_estilos']} estilos de catálogo.")
            print(f"    Nuevos: {result['productos']} productos, "
                  f"{result['variantes']} variantes, "
                  f"{result['existencias']} existencias, "
                  f"{result['movimientos']} movimientos, "
                  f"{result['imagenes']} imágenes nuevas.")
            print(f"    Productos antiguos reclasificados: "
                  f"{result['productos_anteriores_reclasificados']}.")
        print("Ejecución repetible: las operaciones y existencias anteriores se conservan.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(f"No se preparó la semilla ampliada: {error}")
        raise SystemExit(1) from None
