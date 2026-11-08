import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/commerce/mobile_commerce_api.dart';
import 'package:vestinova_mobile/config/api_config.dart';

void main() {
  test('CU09 envío diferido conserva UUID e importe consentido', () async {
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path,
          '/api/tiendas/demo-moda-andina/compras/offline/sincronizar');
        expect(request.headers['Authorization'], 'Bearer demo');
        final body = jsonDecode(request.body) as Map<String,dynamic>;
        expect(body['id'], 'ac8f585c-dddd-4de1-b159-4a1e5cb0c9ec');
        expect(body['autoriza_cobro_diferido'], true);
        expect(body['importe_aceptado_centavos'], 12500);
        expect(body.containsKey('tarjeta'), false);
        return http.Response(jsonEncode({
          'id': body['id'], 'estado': 'PAGO_PENDIENTE',
          'pago_verificado': false, 'reserva_confirmada': false,
        }), 200);
      }),
    );
    addTearDown(api.close);
    final result = await api.deferredCheckout('demo-moda-andina', 'demo', {
      'id': 'ac8f585c-dddd-4de1-b159-4a1e5cb0c9ec',
      'autoriza_cobro_diferido': true,
      'importe_aceptado_centavos': 12500,
      'sucursal_id': 1, 'entrega': 'RETIRO',
      'items': [{'producto_id': 1, 'variante_id': 2, 'cantidad': 1}],
      'creado_local_en': '2026-11-08T00:00:00Z',
    });
    expect(result['estado'], 'PAGO_PENDIENTE');
    expect(result['pago_verificado'], false);
  });

  test('CU16/CU25 historial incluye compras pagadas sin entrega y entregadas',
      () async {
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path,
          '/api/tiendas/demo-moda-andina/cuenta/compras');
        expect(request.url.queryParameters['limit'], '100');
        expect(request.headers['Authorization'], 'Bearer cliente');
        return http.Response.bytes(utf8.encode(jsonEncode({
          'items': [
            {
              'id': 'ddddeeee-1111-4111-8111-111111111111',
              'estado': 'CONFIRMADA',
              'seguimiento_entrega': 'PENDIENTE',
              'importe_total': '69.00',
              'items': [
                {'producto_id': 1, 'nombre': 'Chalina tejida',
                 'cantidad': 1, 'subtotal': '69.00'}
              ],
            },
            {
              'id': 'ddddeeee-2222-4222-8222-222222222222',
              'estado': 'CONFIRMADA',
              'seguimiento_entrega': 'ENTREGADA',
              'importe_total': '79.00',
              'items': [
                {'producto_id': 2, 'nombre': 'Cinturón clásico',
                 'cantidad': 1, 'subtotal': '79.00'}
              ],
            },
          ],
          'total': 2, 'limit': 100, 'offset': 0,
        })), 200, headers: {'content-type': 'application/json; charset=utf-8'});
      }),
    );
    addTearDown(api.close);
    final result = await api.history('demo-moda-andina', 'cliente');
    expect(result.length, 2);
    expect(result.first['estado'], 'CONFIRMADA');
    expect(result.first['seguimiento_entrega'], 'PENDIENTE');
    expect(result.last['seguimiento_entrega'], 'ENTREGADA');
    expect((result.first['items'] as List).first['nombre'], 'Chalina tejida');
  });

  test('CU25 publicación incluye compra y producto verificables', () async {
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.url.path,
          '/api/tiendas/demo-moda-andina/cuenta/valoraciones');
        expect(request.headers['Authorization'], 'Bearer demo');
        final body = jsonDecode(request.body) as Map<String,dynamic>;
        expect(body['compra_id'], 'ac8f585c-dddd-4de1-b159-4a1e5cb0c9ec');
        expect(body['producto_id'], 99);
        expect(body['puntuacion'], 5);
        return http.Response(jsonEncode({'id': 3, 'puntuacion': 5}), 201);
      }),
    );
    addTearDown(api.close);
    final posted = await api.publishReview('demo-moda-andina', 'demo',
      purchaseId: 'ac8f585c-dddd-4de1-b159-4a1e5cb0c9ec',
      productId: 99, rating: 5, comment: 'Buena prenda');
    expect(posted['id'], 3);
  });

  test('CU26 cancelación elimina solo la alerta indicada', () async {
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.url.path,
          '/api/tiendas/demo-moda-andina/cuenta/alertas-push/avisos/9');
        expect(request.method, 'DELETE');
        expect(request.headers['Authorization'], 'Bearer demo');
        return http.Response('', 204);
      }),
    );
    addTearDown(api.close);
    await api.cancelAlert('demo-moda-andina', 'demo', 9);
  });
}
