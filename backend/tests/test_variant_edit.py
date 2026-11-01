"""CU05: correcciones de talla/color sin alterar propiedad o historia previa."""
import pytest
from sqlalchemy import func, select

from app.models import Existencia, MovimientoInventario, VarianteProducto
from tests.test_tenancy_inventory import movement, post_movement, product, scope, variant


def test_edit_variant_persists_normalized_fields_and_preserves_identity(client, scope, session_factory):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    edited = client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah,
                          json={"talla": " l ", "color": " azul marino ", "activo": False})
    assert edited.status_code == 200, edited.text
    expected = {**original, "talla": "L", "color": "AZUL MARINO", "activo": False}
    assert edited.json() == expected
    assert client.get(f"/api/admin/productos/{garment['id']}/variantes", headers=scope.ah).json() == [expected]
    with session_factory() as db:
        stored = db.get(VarianteProducto, original["id"])
        assert (stored.empresa_id, stored.producto_id, stored.talla, stored.color, stored.activo) == (scope.a.id, garment["id"], "L", "AZUL MARINO", False)
        assert db.scalar(select(func.count()).select_from(Existencia)) == 0
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 0


def test_duplicate_edit_rolls_back_other_changes_and_can_be_corrected(client, scope):
    garment = product(client, scope.ah)
    first = variant(client, scope.ah, garment["id"])
    second = variant(client, scope.ah, garment["id"], talla="L", color="AZUL")
    conflict = client.patch(f"/api/admin/variantes/{second['id']}", headers=scope.ah,
                            json={"talla": " m ", "color": " verde ", "activo": False})
    assert conflict.status_code == 409
    assert "combinación" in conflict.json()["detail"]
    assert client.get(f"/api/admin/productos/{garment['id']}/variantes", headers=scope.ah).json() == [first, second]
    fixed = client.patch(f"/api/admin/variantes/{second['id']}", headers=scope.ah, json={"talla": " XL "})
    assert fixed.status_code == 200
    assert fixed.json()["color"] == "AZUL" and fixed.json()["talla"] == "XL"


def test_same_combination_is_allowed_on_another_garment(client, scope):
    first = product(client, scope.ah, "Primera prenda")
    second = product(client, scope.ah, "Segunda prenda")
    variant(client, scope.ah, first["id"])
    other = variant(client, scope.ah, second["id"], talla="L")
    result = client.patch(f"/api/admin/variantes/{other['id']}", headers=scope.ah, json={"talla": " m "})
    assert result.status_code == 200
    assert result.json()["producto_id"] == second["id"]


@pytest.mark.parametrize("changes", [
    {}, {"talla": None}, {"color": None}, {"activo": None},
    {"talla": " "}, {"color": "\t "}, {"talla": "x" * 31}, {"color": "x" * 61},
    {"talla": True}, {"color": 4}, {"activo": "false"}, {"activo": 0},
    {"talla": "ß" * 16}, {"color": "ß" * 31},
    {"producto_id": 999}, {"empresa_id": 999}, {"id": 999}, {"stock": 3},
])
def test_invalid_variant_patch_never_changes_stored_values(client, scope, changes):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    response = client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah, json=changes)
    assert response.status_code == 422, response.text
    assert client.get(f"/api/admin/productos/{garment['id']}/variantes", headers=scope.ah).json() == [original]


def test_exact_limits_are_valid_after_normalization(client, scope):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    response = client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah,
                            json={"talla": " a ", "color": "x" * 60})
    assert response.status_code == 200
    assert response.json()["talla"] == "A" and response.json()["color"] == "X" * 60
    assert client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah,
                        json={"talla": "x" * 30, "color": "a"}).status_code == 200


def test_variant_patch_enforces_company_role_and_current_membership(client, scope):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    path = f"/api/admin/variantes/{original['id']}"
    assert client.patch(path, json={"talla": "L"}).status_code == 401
    assert client.patch(path, headers=scope.oh, json={"talla": "L"}).status_code == 403
    assert client.patch(path, headers=scope.bh, json={"talla": "L"}).status_code == 404
    assert client.patch(path, headers={**scope.bh, "X-Empresa-Id": str(scope.a.id)}, json={"talla": "L"}).status_code == 403
    assert client.patch("/api/admin/variantes/99999", headers=scope.ah, json={"talla": "L"}).status_code == 404
    assert client.get(f"/api/admin/productos/{garment['id']}/variantes", headers=scope.ah).json() == [original]


def test_zero_balance_still_protects_variant_identity(client, scope, session_factory):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    with session_factory() as db:
        db.add(Existencia(empresa_id=scope.a.id, sucursal_id=scope.a1.id, variante_id=original["id"], cantidad=0))
        db.commit()
    result = client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah, json={"talla": "L", "activo": False})
    assert result.status_code == 409
    assert "Desactívala y crea otra variante" in result.json()["detail"]
    assert client.get(f"/api/admin/productos/{garment['id']}/variantes", headers=scope.ah).json() == [original]


def test_history_blocks_identity_but_not_state_or_unchanged_normalized_values(client, scope, session_factory):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    post_movement(client, scope.ah, movement(scope.a1, original["id"], quantity=3))
    # Una corrección no reinterpreta el historial; ni siquiera un saldo cero lo permitiría.
    post_movement(client, scope.ah, movement(scope.a1, original["id"], quantity=3, kind="SALIDA"))
    path = f"/api/admin/variantes/{original['id']}"
    assert client.patch(path, headers=scope.ah, json={"color": "ROJO"}).status_code == 409
    same_identity = client.patch(path, headers=scope.ah, json={"talla": " m ", "color": " verde ", "activo": False})
    assert same_identity.status_code == 200
    assert same_identity.json() == {**original, "activo": False}
    assert client.patch(path, headers=scope.ah, json={"activo": True}).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MovimientoInventario)) == 2
        assert db.get(Existencia, (scope.a.id, scope.a1.id, original["id"])).cantidad == 0


def test_history_without_balance_also_protects_variant_identity(client, scope, session_factory):
    garment = product(client, scope.ah)
    original = variant(client, scope.ah, garment["id"])
    post_movement(client, scope.ah, movement(scope.a1, original["id"], quantity=1))
    # Fixture deliberadamente incompleto para probar la barrera independiente del ledger.
    with session_factory() as db:
        db.delete(db.get(Existencia, (scope.a.id, scope.a1.id, original["id"])))
        db.commit()
    assert client.patch(f"/api/admin/variantes/{original['id']}", headers=scope.ah, json={"talla": "L"}).status_code == 409
