"""CU09: consulta pública de existencias referenciales sin mezclar empresas."""
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
    assert data["items"][0] == {
        "sucursal_id": scope.a1.id,
        "sucursal": scope.a1.nombre,
        "variante_id": av["id"],
        "talla": "M",
        "color": "VERDE",
        "hay_existencias_fisicas": True,
        "saldo_registrado": True,
    }
    assert data["items"][1]["sucursal_id"] == scope.a2.id
    assert data["items"][1]["hay_existencias_fisicas"] is False
    assert data["items"][1]["saldo_registrado"] is False
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
