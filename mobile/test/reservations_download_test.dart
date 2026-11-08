import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/reservations/reservation_mobile_service.dart';
import 'package:vestinova_mobile/reservations/reservation_sqlite.dart';

class RecordingReservations extends ReservationSqlite {
  List<Map<String, Object?>> saved = [];
  int? hours;
  int writes = 0;

  @override
  Future<void> replaceCatalog(
    String store,
    List<Map<String, Object?>> items,
    int timeHours,
  ) async {
    expect(store, 'demo-moda-andina');
    saved = items;
    hours = timeHours;
    writes++;
  }
}

void main() {
  test('CU10 precarga 101 prendas de varias paginas para reservas offline',
      () async {
    final cache = RecordingReservations();
    var productPages = 0;
    final service = MobileReservationService(
      ApiConfig('https://api.example.test/api'),
      cache,
      client: MockClient((req) async {
        if (req.url.path == '/api/catalogo/productos') {
          productPages++;
          expect(req.url.queryParameters['tienda'], 'demo-moda-andina');
          expect(req.url.queryParameters['limit'], '100');
          final offset = int.parse(req.url.queryParameters['offset']!);
          final count = offset == 0 ? 100 : 1;
          return http.Response(jsonEncode({
            'total': 101,
            'limit': 100,
            'offset': offset,
            'items': [
              for (var i = 0; i < count; i++)
                {'slug': 'prenda-${offset + i}', 'nombre': 'Prenda ${offset + i}'},
            ],
          }), 200);
        }
        if (req.url.path.endsWith('/reservas/politica')) {
          return http.Response(jsonEncode({'vigencia_horas': 48}), 200);
        }
        if (req.url.path.endsWith('/disponibilidad')) {
          return http.Response(jsonEncode({'items': [
            {
              'sucursal_id': 1, 'variante_id': 12,
              'sucursal': 'Andina Centro', 'talla': 'M',
              'color': 'Azul', 'hay_disponibilidad': true,
            },
          ]}), 200);
        }
        return http.Response('not found', 404);
      }),
    );
    addTearDown(service.close);
    final count = await service.download('demo-moda-andina');
    expect(productPages, 2);
    expect(count, 101);
    expect(cache.writes, 1);
    expect(cache.saved.length, 101);
    expect(cache.hours, 48);
    expect(cache.saved.first['producto_nombre'], 'Prenda 0');
    expect(cache.saved.last['producto_nombre'], 'Prenda 100');
  });

  test('CU10 conserva la copia anterior si hay mas de 300 prendas',
      () async {
    final cache = RecordingReservations()..saved = [
      {'producto_nombre': 'Preexistente'},
    ];
    final service = MobileReservationService(
      ApiConfig('https://api.example.test/api'),
      cache,
      client: MockClient((req) async {
        final offset = int.parse(req.url.queryParameters['offset']!);
        return http.Response(jsonEncode({
          'total': 301, 'limit': 100, 'offset': offset,
          'items': [
            for (var i = 0; i < 100; i++)
              {'slug': 'prenda-${offset + i}', 'nombre': 'Producto'},
          ],
        }), 200);
      }),
    );
    addTearDown(service.close);
    await expectLater(service.download('demo-moda-andina'),
      throwsA(isA<FormatException>()));
    expect(cache.writes, 0);
    expect(cache.saved.single['producto_nombre'], 'Preexistente');
  });
}
