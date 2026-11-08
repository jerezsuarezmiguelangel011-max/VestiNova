"""La semilla ampliada no duplica ni reinicia datos comerciales al repetirse."""
from sqlalchemy import func, select

from app.models import (
    Administrador, CategoriaProducto, Empresa, Existencia, MembresiaEmpresa,
    MovimientoInventario, Producto, Sucursal, VarianteProducto,
)
from scripts.seed_fashion_catalog_demo import GROUPS, STYLES, seed_catalog


def _prepare_demo_companies(db):
    for slug, tag, locations in (
        ("demo-moda-andina", "andina", ("CENTRO", "NORTE")),
        ("demo-moda-urbana", "urbana", ("CENTRO", "NORTE", "SUR")),
    ):
        company = Empresa(slug=slug, nombre=tag.title(), activo=True)
        admin = Administrador(
            correo=f"admin.{tag}@vestinova.test", nombre=f"Administrador {tag}",
            password_hash="test-hash-no-login", activo=True,
        )
        db.add_all([company, admin])
        db.flush()
        db.add(MembresiaEmpresa(
            administrador_id=admin.id, empresa_id=company.id,
            rol="ADMINISTRADOR", activo=True,
        ))
        for code in locations:
            db.add(Sucursal(
                empresa_id=company.id, codigo=code,
                nombre=f"{tag.title()} {code}", activo=True,
            ))
        jeans = CategoriaProducto(
            empresa_id=company.id, nombre="Jeans",
            nombre_clave="jeans", descripcion="Categoría antigua", activo=True,
        )
        db.add(jeans)
        db.flush()
        db.add(Producto(
            empresa_id=company.id, categoria_id=jeans.id,
            slug=f"demo-{tag}-jean-recto", nombre=f"Jean recto {tag}",
            descripcion="Registro anterior de prueba.",
            precio=199, moneda="BOB", activo=True,
        ))
    db.flush()


def test_catalogo_ampliado_por_empresa_es_repetible_y_conserva_stock(session_factory):
    with session_factory.begin() as db:
        _prepare_demo_companies(db)
        first = seed_catalog(db)
        assert len(first) == 2
        assert all(row["categorias"] == len(GROUPS) for row in first)
        assert all(row["productos"] == len(STYLES) for row in first)
        assert first[0]["sucursales"] == 2
        assert first[1]["sucursales"] == 3
        categories = db.scalars(select(CategoriaProducto).where(
            CategoriaProducto.nombre_clave == "pantalones",
        )).all()
        assert len(categories) == 2
        for tag in ("andina", "urbana"):
            original = db.scalar(select(Producto).where(
                Producto.slug == f"demo-{tag}-jean-recto",
            ))
            category = db.get(CategoriaProducto, original.categoria_id)
            assert category.nombre == "Pantalones"

        original_count = db.scalar(select(func.count()).select_from(Producto))
        variant_count = db.scalar(select(func.count()).select_from(VarianteProducto))
        movements_count = db.scalar(select(func.count()).select_from(MovimientoInventario))
        stock = db.scalar(select(Existencia).where(
            Existencia.cantidad > 2,
        ).order_by(Existencia.empresa_id, Existencia.sucursal_id))
        assert stock is not None
        example = db.scalar(select(Producto).where(
            Producto.slug == "demo-andina-catalogo-polera-manga-corta",
        ))
        assert example.imagen_url is not None
        assert example.imagen_url.startswith("https://images.pexels.com/photos/")
        assert "w=640" in example.imagen_url
        stock_key = (stock.empresa_id, stock.sucursal_id, stock.variante_id)
        stock.cantidad = 2
        stock.cantidad_comprometida = 1
        db.flush()

        again = seed_catalog(db)
        assert all(row["productos"] == 0 and row["variantes"] == 0
                   and row["existencias"] == 0 and row["movimientos"] == 0
                   for row in again)
        assert db.scalar(select(func.count()).select_from(Producto)) == original_count
        assert db.scalar(select(func.count()).select_from(VarianteProducto)) == variant_count
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == movements_count
        assert db.get(Existencia, stock_key).cantidad == 2
        assert db.get(Existencia, stock_key).cantidad_comprometida == 1


def test_semilla_contiene_variedad_de_tallas_colores_y_sin_stock(session_factory):
    with session_factory.begin() as db:
        _prepare_demo_companies(db)
        seed_catalog(db)
        andina = db.scalar(select(Empresa).where(Empresa.slug == "demo-moda-andina"))
        rows = db.execute(select(Producto, VarianteProducto).join(
            VarianteProducto, VarianteProducto.producto_id == Producto.id,
        ).where(Producto.empresa_id == andina.id,
                VarianteProducto.empresa_id == andina.id)).all()
        groups = {db.get(CategoriaProducto, product.categoria_id).nombre
                  for product, _ in rows}
        assert set(GROUPS) <= groups
        assert any(variant.talla == "M" for _, variant in rows)
        assert any(variant.talla == "40" for _, variant in rows)
        assert any(variant.talla == "39" for _, variant in rows)
        assert any(variant.color == "Azul" for _, variant in rows)
        assert all(product.imagen_url is not None
                   for product, _ in rows
                   if "catalogo-" in product.slug)
        assert db.scalar(select(func.count()).select_from(Existencia).where(
            Existencia.empresa_id == andina.id,
            Existencia.cantidad == 0,
        )) > 0
