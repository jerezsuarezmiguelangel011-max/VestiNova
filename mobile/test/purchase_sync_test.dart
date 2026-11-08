import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/commerce/mobile_commerce_api.dart';
import 'package:vestinova_mobile/commerce/mobile_order_store.dart';
import 'package:vestinova_mobile/commerce/purchase_notices.dart';
import 'package:vestinova_mobile/commerce/purchase_sync.dart';
import 'package:vestinova_mobile/config/api_config.dart';

class MemoryOrders extends MobileOrderStore {
  MemoryOrders(this.rows);
  final List<MobilePendingOrder> rows;
  final Map<String, String> statuses = {};
  final Map<String, int> notices = {};

  @override
  Future<List<MobilePendingOrder>> list(String tienda, int customerId) async =>
      rows.where((row) => row.payload['cliente_id'] == customerId).toList();

  @override
  Future<void> update(String uuid, String state, String msg) async {
    statuses[uuid] = state;
  }

  @override
  Future<bool> claimFinalNotice(String uuid, String state) async {
    notices.update(uuid, (v) => v + 1, ifAbsent: () => 1);
    return notices[uuid] == 1;
  }
}

MobilePendingOrder order(String id) => MobilePendingOrder(
  id,
  {
    'id': id,
    'cliente_id': 77,
    'sucursal_id': 10,
    'entrega': 'RETIRO',
    'items': [{'producto_id': 9, 'variante_id': 11, 'cantidad': 1}],
    'autoriza_cobro_diferido': true,
    'importe_aceptado_centavos': 6900,
    'creado_local_en': '2026-11-08T21:00:00Z',
  },
  'PENDIENTE',
  'Sin Internet',
);

void main() {
  test('Notificaciones nunca describen PENDIENTE como pagado', () {
    expect(PurchaseNotices.outcome('PENDIENTE'), isNull);
    expect(PurchaseNotices.outcome('PAGO_PENDIENTE'), isNull);
    expect(PurchaseNotices.outcome('CONFIRMADA')!.title,
      contains('Compra confirmada'));
    expect(PurchaseNotices.outcome('CONFLICTO')!.title,
      contains('No se confirmó'));
    expect(PurchaseNotices.outcome('RECHAZADA')!.title,
      contains('No se confirmó'));
    expect(PurchaseNotices.outcome('INCIDENCIA')!.title,
      contains('requiere revisión'));
  });

  test('Sincronización confirma exclusivamente según API y conserva UUID',
      () async {
    final id = 'ab3a786f-cc11-4b27-8dc6-b59bd9b48999';
    final storage = MemoryOrders([order(id)]);
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path,
          '/api/tiendas/demo-moda-andina/compras/offline/sincronizar');
        expect(request.headers['Authorization'], 'Bearer cliente');
        expect(jsonDecode(request.body)['id'], id);
        return http.Response(jsonEncode({
          'id': id, 'estado': 'CONFIRMADA', 'pago_verificado': true,
          'reserva_confirmada': false,
        }), 200);
      }),
    );
    addTearDown(api.close);
    await const PurchaseSyncService().synchronize(
      tienda: 'demo-moda-andina', customerId: 77,
      token: 'cliente', store: storage, api: api);
    expect(storage.statuses[id], 'CONFIRMADA');
    expect(storage.notices[id], 1);
  });

  test('Sin stock (HTTP 409) termina CONFLICTO, no confirma pago', () async {
    final id = 'b0454ad2-1190-4e1a-920b-eb14a2aab121';
    final storage = MemoryOrders([order(id)]);
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((_) async =>
        http.Response(jsonEncode({'detail': 'No hay stock suficiente.'}), 409)),
    );
    addTearDown(api.close);
    await const PurchaseSyncService().synchronize(
      tienda: 'demo-moda-andina', customerId: 77,
      token: 'cliente', store: storage, api: api);
    expect(storage.statuses[id], 'CONFLICTO');
    expect(storage.notices[id], 1);
  });

  test('Sin red mantiene UUID PENDIENTE sin inventar compra', () async {
    final id = 'fd1c1f9c-b58a-4808-a731-12a8a5887cec';
    final storage = MemoryOrders([order(id)]);
    final api = MobileCommerceApi(
      ApiConfig('https://api.example.test/api'),
      client: MockClient((_) async => throw const SocketException('Sin red')),
    );
    addTearDown(api.close);
    await const PurchaseSyncService().synchronize(
      tienda: 'demo-moda-andina', customerId: 77,
      token: 'cliente', store: storage, api: api);
    expect(storage.statuses[id], 'PENDIENTE');
    expect(storage.notices.containsKey(id), false);
  });
}
