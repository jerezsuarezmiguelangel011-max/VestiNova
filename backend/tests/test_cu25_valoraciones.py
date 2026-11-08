"""CU25: compra pagada no habilita valorar hasta la entrega verificada."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.compras_reservas.compras.domain import Purchase, PurchaseCommand, PurchaseContext, PurchaseItem, PurchaseLine
from app.compras_reservas.compras.persistence import add_purchase
from app.compras_reservas.compras.stripe_checkout import CheckoutAttempt
from app.inventario.domain import InventoryKey
from app.models import Cliente, Empresa, Producto, Sucursal, VarianteProducto
from app.security import hash_password


def test_cu25_compra_entrega_valoracion_y_seguridad(client, session_factory, auth):
    clave = "Clave-CU25-fixture-2026"
    with session_factory() as db:
        company = db.scalar(select(Empresa).where(Empresa.slug == "empresa-prueba"))
        customer = Cliente(empresa_id=company.id, nombre="Comprador CU25",
                           correo="cu25.cliente@vestinova.test", password_hash=hash_password(clave), activo=True)
        other = Cliente(empresa_id=company.id, nombre="Segundo CU25",
                        correo="cu25.otro@vestinova.test", password_hash=hash_password(clave), activo=True)
        branch = Sucursal(empresa_id=company.id, codigo="CU25", nombre="Central", activo=True)
        db.add_all([customer, other, branch])
        db.flush()
        product = Producto(empresa_id=company.id, slug="pantalon-hombre-cu25", nombre="Pantalón clásico hombre",
                           precio=Decimal("150.00"), moneda="BOB", activo=True)
        db.add(product)
        db.flush()
        variant = VarianteProducto(empresa_id=company.id, producto_id=product.id, talla="M", color="Azul", activo=True)
        db.add(variant)
        db.flush()
        purchase_id = uuid4()
        ctx = PurchaseContext(customer.id, company.id, customer.id, branch.id)
        fingerprint = PurchaseCommand(purchase_id, (PurchaseItem(product.id, 1),)).fingerprint
        purchase = Purchase(purchase_id, ctx, fingerprint,
                            (PurchaseLine(InventoryKey(company.id, branch.id, variant.id), product.id,
                                          product.nombre, 1, Decimal("150.00")),), datetime.now(timezone.utc))
        add_purchase(db, purchase)
        db.add(CheckoutAttempt(
            id=str(purchase_id), empresa_id=company.id, cliente_id=customer.id, sucursal_id=branch.id,
            huella="0" * 64, datos={"entrega": "RETIRO", "items": []}, monto_centavos=15000,
            estado="CONFIRMADA",
        ))
        product_id = product.id
        company_id = company.id
        db.commit()

    login = client.post("/api/tiendas/empresa-prueba/cuenta/login",
                        json={"correo": "cu25.cliente@vestinova.test", "password": clave})
    assert login.status_code == 200, login.text
    customer_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    url = "/api/tiendas/empresa-prueba/cuenta/valoraciones"
    payload = {"compra_id": str(purchase_id), "producto_id": product_id,
               "puntuacion": 5, "comentario": "Muy buena calidad."}

    early = client.post(url, json=payload, headers=customer_headers)
    assert early.status_code == 409, early.text
    assert client.get("/api/tiendas/empresa-prueba/cuenta/compras",
                      headers=customer_headers).json()["items"][0]["seguimiento_entrega"] != "ENTREGADA"

    staff_headers = {**auth, "X-Empresa-Id": str(company_id)}
    delivery_url = "/api/admin/entregas-compras/" + str(purchase_id) + "/confirmar"
    unverified = client.post(delivery_url, json={"identidad_verificada": False,
                            "comprobacion": "Prendas entregadas"}, headers=staff_headers)
    assert unverified.status_code == 422
    delivered = client.post(delivery_url, json={"identidad_verificada": True,
                            "comprobacion": "Documento de identidad comprobado"}, headers=staff_headers)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["entrega"] == "ENTREGADA"
    assert client.post(delivery_url, json={"identidad_verificada": True,
                       "comprobacion": "Documento de identidad comprobado"}, headers=staff_headers).status_code == 200
    assert client.get("/api/tiendas/empresa-prueba/cuenta/compras",
                      headers=customer_headers).json()["items"][0]["seguimiento_entrega"] == "ENTREGADA"

    created = client.post(url, json=payload, headers=customer_headers)
    assert created.status_code == 201, created.text
    assert created.json()["puntuacion"] == 5
    assert client.post(url, json=payload, headers=customer_headers).status_code == 409
    assert client.post(url, json={**payload, "puntuacion": 0}, headers=customer_headers).status_code == 422
    invalid = client.post(url, json={**payload, "producto_id": product_id + 5000}, headers=customer_headers)
    assert invalid.status_code == 409
    review_id = created.json()["id"]
    edited = client.patch(url + "/" + str(review_id),
                          json={"puntuacion": 4, "comentario": "Buen acabado"},
                          headers=customer_headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["puntuacion"] == 4
    assert len(client.get(url, headers=customer_headers).json()["items"]) == 1

    public = client.get("/api/catalogo/productos/pantalon-hombre-cu25/valoraciones",
                        params={"tienda": "empresa-prueba"})
    assert public.status_code == 200, public.text
    assert public.json()["total"] == 1
    assert "cliente_id" not in str(public.json())
    assert "correo" not in str(public.json())

    outsider = client.post("/api/tiendas/empresa-prueba/cuenta/login",
                          json={"correo": "cu25.otro@vestinova.test", "password": clave})
    assert outsider.status_code == 200
    outsider_headers = {"Authorization": "Bearer " + outsider.json()["access_token"]}
    assert client.patch(url + "/" + str(review_id), json={"puntuacion": 1},
                        headers=outsider_headers).status_code == 404
    assert client.post(url, json=payload, headers=outsider_headers).status_code == 409
