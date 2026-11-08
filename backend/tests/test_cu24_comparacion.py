"""CU24: rechazo de selecciones manipuladas y comparación pública aislada."""
from decimal import Decimal

from app.models import Empresa, Existencia, Producto, Sucursal, VarianteProducto


def test_cu24_comparacion_y_disponibilidad(client, session_factory):
    with session_factory() as db:
        company = Empresa(slug="comparacion-andina", nombre="Comparación Andina", activo=True)
        another = Empresa(slug="comparacion-urbana", nombre="Comparación Urbana", activo=True)
        db.add_all([company, another])
        db.flush()
        first = Producto(empresa_id=company.id, slug="camisa-cu24", nombre="Camisa masculina",
                         precio=Decimal("100.00"), moneda="BOB", activo=True)
        second = Producto(empresa_id=company.id, slug="pantalon-cu24", nombre="Pantalón masculino",
                          precio=Decimal("180.00"), moneda="BOB", activo=True)
        foreign = Producto(empresa_id=another.id, slug="camisa-externa-cu24", nombre="Producto externo",
                           precio=Decimal("90.00"), moneda="BOB", activo=True)
        db.add_all([first, second, foreign])
        db.flush()
        branch = Sucursal(empresa_id=company.id, codigo="CENTRO-CU24", nombre="Central", activo=True)
        variant = VarianteProducto(empresa_id=company.id, producto_id=first.id,
                                  talla="M", color="Azul", activo=True)
        db.add_all([branch, variant])
        db.flush()
        db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id, variante_id=variant.id,
                         cantidad=3, cantidad_comprometida=1))
        ids = [first.id, second.id]
        other_id = foreign.id
        db.commit()
    payload = {"tienda": "comparacion-andina", "producto_ids": ids}
    response = client.post("/api/catalogo/comparar", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tienda"] == "comparacion-andina"
    assert [p["id"] for p in body["items"]] == ids
    assert body["items"][0]["precio"] == "100.00"
    assert body["items"][0]["variantes"][0]["sucursales"][0]["estado"] == "DISPONIBLE"
    assert response.headers["cache-control"] == "no-store"
    for invalid in ([ids[0]], [ids[0], ids[0]], ids + [other_id]):
        reply = client.post("/api/catalogo/comparar",
                            json={"tienda": "comparacion-andina", "producto_ids": invalid})
        assert reply.status_code in (409, 422)
        assert "Producto externo" not in reply.text
