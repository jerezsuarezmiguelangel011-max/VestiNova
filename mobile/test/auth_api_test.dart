import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/password_policy.dart';
import 'package:vestinova_mobile/config/api_config.dart';

import 'support.dart';

void main() {
  test('la base requiere /api, no credenciales y HTTPS en distribución', () {
    expect(
      ApiConfig('http://10.0.2.2:8001/api/').base,
      'http://10.0.2.2:8001/api',
    );
    for (final value in [
      'https://user:secret@example.test/api',
      'https://example.test',
      'file:///api',
      'https://example.test/api?x=1',
    ]) {
      expect(() => ApiConfig(value), throwsFormatException);
    }
    expect(
      () => ApiConfig('http://example.test/api', release: true),
      throwsFormatException,
    );
    expect(
      ApiConfig('https://example.test/api', release: true).base,
      'https://example.test/api',
    );
  });

  test('el enlace suministra solo slug, nunca otro servidor de API', () {
    expect(
      ApiConfig.storeSlug('https://tienda.example.test/tienda/tienda-a/acceso'),
      'tienda-a',
    );
    expect(ApiConfig.storeSlug(' tienda-a '), 'tienda-a');
    expect(ApiConfig.storeSlug('https://example.test/otra/ruta'), isNull);
    expect(ApiConfig.storeSlug('TIENDA A'), isNull);
  });

  test('registro normaliza correo/nombre sin recortar contraseña ni enviar rol o contexto administrativo', () async {
    final api = AuthApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/tiendas/tienda-a/cuenta/registro');
        expect(request.headers.containsKey('authorization'), isFalse);
        expect(request.headers.containsKey('X-Empresa-Id'), isFalse);
        expect(request.followRedirects, isFalse);
        expect(jsonDecode(request.body), {
          'nombre': 'Cliente',
          'correo': 'cliente@example.test',
          'password': ' Abcdef1! ',
        });
        return jsonResponse(customerAccess(), 201);
      }),
    );
    addTearDown(api.close);
    final result = await api.customerAccess(
      'tienda-a',
      ' CLIENTE@example.test ',
      ' Abcdef1! ',
      name: ' Cliente ',
    );
    expect(result.account.store.slug, 'tienda-a');
  });

  test('login personal conserva contraseñas previas que no cumplen política de nuevas cuentas', () async {
    final api = AuthApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/auth/login');
        expect(jsonDecode(request.body), {
          'correo': 'personal@example.test',
          'password': 'old',
        });
        expect(request.headers.containsKey('authorization'), isFalse);
        return jsonResponse(staffAccess());
      }),
    );
    addTearDown(api.close);
    expect(
      (await api.staffLogin(' PERSONAL@example.test ', 'old')).account.id,
      1,
    );
  });

  test('solo contexto de personal lleva X-Empresa-Id', () async {
    final paths = <String>[];
    final api = AuthApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        paths.add(request.url.path);
        if (request.url.path.endsWith('/contexto')) {
          expect(request.headers['X-Empresa-Id'], '2');
          expect(request.headers['authorization'], 'Bearer personal-fixture');
          return jsonResponse(contextData(2));
        }
        expect(request.headers.containsKey('X-Empresa-Id'), isFalse);
        expect(request.headers['authorization'], 'Bearer cliente-fixture');
        return jsonResponse(customerData());
      }),
    );
    addTearDown(api.close);
    await api.context('personal-fixture', 2);
    await api.customerMe('tienda-a', 'cliente-fixture');
    expect(paths, ['/api/auth/contexto', '/api/tiendas/tienda-a/cuenta/me']);
  });

  test('rechaza respuesta de cuenta de otra tienda', () async {
    final api = AuthApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((_) async => jsonResponse(customerData('tienda-b'))),
    );
    addTearDown(api.close);
    await expectLater(
      api.customerMe('tienda-a', 'fixture'),
      throwsA(
        isA<AccessException>().having((error) => error.status, 'status', 401),
      ),
    );
  });

  test('rechaza contexto de otra empresa aunque la API responda 200', () async {
    final api = AuthApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((_) async => jsonResponse(contextData(2))),
    );
    addTearDown(api.close);
    await expectLater(
      api.context('fixture', 1),
      throwsA(isA<AccessException>()),
    );
  });

  test(
    'errores estructurados de validación no muestran datos de entrada o trazas',
    () async {
      final api = AuthApi(
        ApiConfig('https://api.example.test/api'),
        client: MockClient(
          (_) async => jsonResponse({
            'detail': [
              {'input': 'secret-fixture'},
            ],
          }, 422),
        ),
      );
      addTearDown(api.close);
      await expectLater(
        api.staffLogin('personal@example.test', 'fixture'),
        throwsA(
          isA<AccessException>().having(
            (error) => error.message,
            'mensaje',
            'Revisa los campos introducidos y vuelve a intentarlo.',
          ),
        ),
      );
    },
  );

  group('política nueva, consistente con backend y sin recortes', () {
    for (final password in [
      'Abcdef1!',
      'Äbcdef١!',
      'Ⓐbcdef1!',
      'Abcde1!😀',
      'A${'a' * 125}1!',
      ' Abcd1! ',
    ]) {
      test(
        'acepta ${password.runes.length} caracteres válidos',
        () => expect(validateNewPassword(password), isNull),
      );
    }
    for (final password in [
      'Abc1!',
      'A${'a' * 126}1!',
      'abcdef1!',
      'ABCDEF1!',
      'Abcdefg!',
      'Abcdef12',
      'Abcdef1 ',
      'Abcdef1\n',
      'Abcdef²!',
    ]) {
      test(
        'rechaza contraseña inválida de ${password.runes.length} caracteres',
        () => expect(validateNewPassword(password), passwordPolicyMessage),
      );
    }
  });
}
