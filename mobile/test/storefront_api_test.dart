import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/storefront/storefront_api.dart';
import 'package:vestinova_mobile/storefront/storefront_models.dart';

http.Response jsonResponse(dynamic body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

Map<String, dynamic> product(int id, String slug) => {
  'id': id,
  'slug': slug,
  'nombre': 'Camisa masculina $id',
  'precio': '180.00',
  'categoria_id': 2,
  'categoria_nombre': 'Camisas',
  'imagen_url': null,
  'moneda': 'BOB',
};

void main() {
  test(
    'consulta sucursales reales por tienda y sin token administrativo',
    () async {
      final api = StorefrontApi(
        ApiConfig('https://api.example.test/api'),
        client: MockClient((request) async {
          expect(request.url.path, '/api/catalogo/sucursales');
          expect(request.url.queryParameters['tienda'], 'tienda-a');
          expect(request.headers.containsKey('Authorization'), false);
          return jsonResponse([
            {'id': 7, 'nombre': 'Sucursal Centro'},
          ]);
        }),
      );
      addTearDown(api.close);
      final branches = await api.publicBranches('tienda-a');
      expect(branches.single.id, 7);
      expect(branches.single.name, 'Sucursal Centro');
    },
  );

  test('CU08 consulta catálogo filtrado exclusivamente por tienda', () async {
    final api = StorefrontApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/catalogo/productos');
        expect(request.url.queryParameters['tienda'], 'tienda-a');
        expect(request.url.queryParameters['categoria_id'], '2');
        expect(request.url.queryParameters['talla'], 'L');
        expect(request.headers.containsKey('Authorization'), false);
        return jsonResponse({
          'items': [product(6, 'camisa-lino')],
          'total': 1,
          'limit': 20,
          'offset': 0,
        });
      }),
    );
    addTearDown(api.close);
    final result = await api.products(
      'tienda-a',
      filters: const StoreFilters(categoryId: 2, size: 'L'),
    );
    expect(result.total, 1);
    expect(result.items.single.slug, 'camisa-lino');
  });

  test(
    'CU19 usa recomendaciones públicas reales y no atribuye preferencias',
    () async {
      final api = StorefrontApi(
        ApiConfig('https://api.example.test/api'),
        client: MockClient((request) async {
          expect(request.url.path, '/api/catalogo/recomendaciones');
          expect(request.url.queryParameters['tienda'], 'tienda-a');
          expect(request.url.queryParameters['producto_slug'], 'camisa-lino');
          return jsonResponse({
            'items': [
              {
                ...product(9, 'camisa-azul'),
                'producto_id': 9,
                'motivos': ['Categoría similar'],
              },
            ],
            'tienda': 'tienda-a',
          });
        }),
      );
      addTearDown(api.close);
      final result = await api.recommendations(
        'tienda-a',
        reference: 'camisa-lino',
      );
      expect(result.single.reasons.first, 'Categoría similar');
    },
  );

  test(
    'CU23 envía sesión únicamente en la API privada y variante_id correcto',
    () async {
      final calls = <String>[];
      final api = StorefrontApi(
        ApiConfig('https://api.example.test/api'),
        client: MockClient((request) async {
          calls.add('${request.method} ${request.url.path}');
          expect(request.headers['Authorization'], 'Bearer valid-token');
          if (request.method == 'POST') {
            expect(jsonDecode(request.body), {'variante_id': 41});
            return jsonResponse({'variante_id': 41, 'agregado': true}, 201);
          }
          return http.Response('', 204);
        }),
      );
      addTearDown(api.close);
      expect(await api.addWish('tienda-a', 'valid-token', 41), true);
      await api.removeWish('tienda-a', 'valid-token', 41);
      expect(calls, [
        'POST /api/tiendas/tienda-a/cuenta/deseos',
        'DELETE /api/tiendas/tienda-a/cuenta/deseos/41',
      ]);
    },
  );

  test('CU24 acepta dos a cuatro productos, rechaza duplicados y usa IDs de producto', () async {
    final api = StorefrontApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/catalogo/comparar');
        expect(jsonDecode(request.body), {
          'tienda': 'tienda-a',
          'producto_ids': [8, 9],
        });
        return jsonResponse({
          'items': [product(8, 'pantalon'), product(9, 'jean')],
        });
      }),
    );
    addTearDown(api.close);
    await expectLater(
      api.compare('tienda-a', [8, 8]),
      throwsA(isA<StorefrontException>()),
    );
    await expectLater(
      api.compare('tienda-a', [8]),
      throwsA(isA<StorefrontException>()),
    );
    final result = await api.compare('tienda-a', [8, 9]);
    expect(result.map((e) => e.id), [8, 9]);
  });

  test(
    'rechaza por separado errores de negocio y pérdida de conexión',
    () async {
      final api = StorefrontApi(
        ApiConfig('https://api.example.test/api'),
        client: MockClient(
          (_) async => jsonResponse({'detail': 'Tienda no disponible.'}, 404),
        ),
      );
      addTearDown(api.close);
      await expectLater(
        api.products('otra-tienda'),
        throwsA(
          isA<StorefrontException>()
              .having((e) => e.network, 'network', false)
              .having((e) => e.status, 'status', 404),
        ),
      );
    },
  );
}
