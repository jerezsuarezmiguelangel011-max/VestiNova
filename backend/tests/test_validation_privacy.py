"""El rechazo de validación conserva reglas y nunca refleja credenciales."""
import pytest


@pytest.mark.parametrize('path', [
    '/api/auth/login',
    '/api/tiendas/empresa-prueba/cuenta/login',
    '/api/tiendas/empresa-prueba/cuenta/registro',
])
@pytest.mark.parametrize('password', ['SecretoPrivado!1' * 100, {'secreto': 'SecretoPrivado!1'}], ids=['demasiado-larga', 'tipo-invalido'])
def test_invalid_credentials_are_not_echoed_in_validation_errors(client, administrator, path, password):
    payload = {'correo': administrator.correo, 'password': password}
    if path.endswith('registro'):
        payload['nombre'] = 'Cliente de prueba'
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert 'SecretoPrivado' not in response.text
    assert 'input' not in response.text
    detail = response.json()['detail']
    if isinstance(detail, list):
        assert response.headers['cache-control'] == 'no-store'
        assert all(set(item) <= {'type', 'loc', 'msg'} for item in detail)


def test_general_validation_errors_keep_field_locations_without_payload(client, auth):
    response = client.post('/api/admin/productos', headers=auth, json={'nombre': 'x', 'precio': 'no-es-precio'})
    assert response.status_code == 422
    assert {tuple(item['loc']) for item in response.json()['detail']} >= {('body', 'nombre'), ('body', 'precio')}
    assert 'no-es-precio' not in response.text
