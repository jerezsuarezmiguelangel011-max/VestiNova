"""CU09: consulta pública de existencias referenciales sin mezclar empresas."""
from datetime import datetime
from tests.test_tenancy_inventory import scope, product, variant, movement, post_movement


def test_availability_is_scoped_to_public_product_branch_and_variant(client, scope):
    a = product(client, scope.ah, "Camisa consulta CU09")
    av = variant(client, scope.ah, a["id"])
    variant(client, scope.ah, a["id"], talla="L", color="NEGRO", activo=False)
    b = product(client, scope.bh, "Prenda ajena CU09")
    variant(client, scope.bh, b["id"])
    post_movement(client, scope.ah, movement(scope.a1, av["id"], 8))

    response = client.get(f"/api/catalogo/productos/{a['slug']}/disponibilidad")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["producto_id"] == a["id"]
    assert data["alcance"] == "STOCK_FISICO_REFERENCIAL"
    assert data["consultado_en"]
    assert len(data["items"]) == 2
    first = data["items"][0]
    # CU10 compromete unidades sin descontar el stock físico. El catálogo
    # muestra además la disponibilidad neta y cuándo se actualizó el saldo.
    assert {key: value for key, value in first.items() if key != "actualizado_en"} == {
        "sucursal_id": scope.a1.id,
        "sucursal": scope.a1.nombre,
        "variante_id": av["id"],
        "talla": "M",
        "color": "VERDE",
        "hay_existencias_fisicas": True,
        "hay_disponibilidad": True,
        "saldo_registrado": True,
    }
    assert first["actualizado_en"] is not None
    assert datetime.fromisoformat(first["actualizado_en"])

    second = data["items"][1]
    assert second["sucursal_id"] == scope.a2.id
    assert second["hay_existencias_fisicas"] is False
    assert second["hay_disponibilidad"] is False
    assert second["actualizado_en"] is None
    assert second["saldo_registrado"] is False
    assert all(item["sucursal_id"] != scope.b1.id for item in data["items"])


def test_hidden_and_unknown_products_have_no_availability(client, scope):
    hidden = product(client, scope.ah, "Producto oculto CU09", activo=False)
    assert client.get(f"/api/catalogo/productos/{hidden['slug']}/disponibilidad").status_code == 404
    assert client.get("/api/catalogo/productos/no-existe/disponibilidad").status_code == 404


def test_inactive_branches_are_not_visible_in_availability(client, scope):
    a = product(client, scope.ah, "Producto sucursal activa")
    variant(client, scope.ah, a["id"])
    response = client.patch(f"/api/admin/sucursales/{scope.a2.id}", headers=scope.ah, json={"activo": False})
    assert response.status_code == 200
    data = client.get(f"/api/catalogo/productos/{a['slug']}/disponibilidad").json()
    assert [item["sucursal_id"] for item in data["items"]] == [scope.a1.id]


def test_catalog_filters_net_stock_and_does_not_confuse_unknown_with_out_of_stock(
    client, scope, session_factory,
):
    """CU08: filtrar antes de paginar, solo saldos conocidos y netos del tenant."""
    from sqlalchemy import select
    from app.models import Existencia

    available = product(client, scope.ah, "Disponibilidad neta CU08")
    variant_a = variant(client, scope.ah, available["id"])
    depleted = product(client, scope.ah, "Stock comprometido CU08")
    variant_d = variant(client, scope.ah, depleted["id"])
    unknown = product(client, scope.ah, "Saldo desconocido CU08")
    variant(client, scope.ah, unknown["id"])
    foreign = product(client, scope.bh, "Stock de otra empresa CU08")
    variant_f = variant(client, scope.bh, foreign["id"])

    post_movement(client, scope.ah, movement(scope.a1, variant_a["id"], 4))
    post_movement(client, scope.bh, movement(scope.b1, variant_f["id"], 5))
    with session_factory() as db:
        # Saldos conocidos cero; y la reserva compromete todas las unidades.
        db.add(Existencia(
            empresa_id=scope.a.id, sucursal_id=scope.a1.id,
            variante_id=variant_d["id"], cantidad=2, cantidad_comprometida=2,
        ))
        db.commit()

    url = "/api/catalogo/productos"
    valid = client.get(url, params={
        "tienda": scope.a.slug, "disponibilidad": "DISPONIBLE",
        "limit": 1, "offset": 0,
    })
    assert valid.status_code == 200, valid.text
    assert valid.json()["total"] == 1
    assert [x["id"] for x in valid.json()["items"]] == [available["id"]]
    assert client.get(url, params={
        "tienda": scope.a.slug, "disponibilidad": "DISPONIBLE",
        "limit": 1, "offset": 1,
    }).json()["items"] == []

    sold_out = client.get(url, params={
        "tienda": scope.a.slug, "disponibilidad": "AGOTADO",
    })
    assert sold_out.status_code == 200, sold_out.text
    assert [x["id"] for x in sold_out.json()["items"]] == [depleted["id"]]
    assert unknown["id"] not in {x["id"] for x in sold_out.json()["items"]}
    assert foreign["id"] not in {x["id"] for x in sold_out.json()["items"]}

    # Restar una reserva compromete stock sin eliminarlo físicamente.
    with session_factory() as db:
        stock = db.scalar(select(Existencia).where(
            Existencia.empresa_id == scope.a.id,
            Existencia.variante_id == variant_a["id"],
        ))
        stock.cantidad_comprometida = stock.cantidad
        db.commit()
    empty = client.get(url, params={
        "tienda": scope.a.slug, "disponibilidad": "DISPONIBLE",
    })
    assert empty.json()["total"] == 0
    assert client.get(url, params={
        "tienda": scope.a.slug, "disponibilidad": "AGOTADO",
    }).json()["total"] == 2


def test_availability_filter_uses_selected_variant_size_and_color(client, scope):
    item = product(client, scope.ah, "Talla y color filtrados CU08")
    variant_black = variant(client, scope.ah, item["id"], talla="M", color="Negro")
    variant_blue = variant(client, scope.ah, item["id"], talla="L", color="Azul")
    post_movement(client, scope.ah, movement(scope.a1, variant_blue["id"], 3))
    base = {"tienda": scope.a.slug, "disponibilidad": "DISPONIBLE"}
    assert client.get("/api/catalogo/productos", params={
        **base, "talla": variant_blue["talla"], "color": variant_blue["color"],
    }).json()["total"] == 1
    assert client.get("/api/catalogo/productos", params={
        **base, "talla": variant_black["talla"], "color": variant_black["color"],
    }).json()["total"] == 0

    # El filtro solo admite valores expresamente definidos.
    invalid = client.get("/api/catalogo/productos", params={
        **base, "disponibilidad": "DISPONIBLE_INVENTADA",
    })
    assert invalid.status_code == 422
