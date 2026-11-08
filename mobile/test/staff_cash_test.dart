import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/staff/cash_api.dart';
import 'package:vestinova_mobile/staff/cash_models.dart';
import 'package:vestinova_mobile/staff/cash_store.dart';
import 'package:vestinova_mobile/staff/cash_sync.dart';

import 'support.dart';

const _base = 'https://api.example.test/api';
const _uuid = '52b72451-fd35-4f34-8b6e-8aa511540ca4';

Map<String, dynamic> _payload() => {
  'id': _uuid, 'sucursal_id': 10, 'cliente_id': null,
  'lineas': [
    {'variante_id': 23, 'cantidad': 2, 'precio_unitario': '80.10'},
  ],
  'efectivo': '200.00',
  'origen': 'MOVIL_OFFLINE',
  'efectivo_cobrado': true,
  'entrega_local': false,
  'creada_local_en': '2026-11-08T20:00:00Z',
};

CashLocalSale _sale([String state = 'PENDIENTE']) => CashLocalSale(
  id: _uuid, companyId: 1, staffId: 7, branchId: 10,
  payload: _payload(), state: state, message: 'Guardada localmente',
);

class _Queue implements CashSaleQueue {
  _Queue(this.current);
  CashLocalSale current;
  final writes = <String>[];

  @override
  Future<List<CashLocalSale>> list(int companyId, int staffId, int branchId) async {
    expect(companyId, 1);
    expect(staffId, 7);
    expect(branchId, 10);
    return [current];
  }

  @override
  Future<void> recover(int companyId, int staffId, int branchId) async {
    if (current.state == 'ENVIANDO') {
      current = _replace('ERROR', 'Recuperada');
    }
  }

  CashLocalSale _replace(String state, String msg, {String? incidentId, String? code}) =>
    CashLocalSale(id: current.id, companyId: current.companyId,
      staffId: current.staffId, branchId: current.branchId, payload: current.payload,
      state: state, message: msg, incidentId: incidentId, code: code);

  @override
  Future<bool> claim(CashLocalSale sale) async {
    if (!current.retryable) return false;
    current = _replace('ENVIANDO', 'Procesando');
    return true;
  }

  @override
  Future<void> finish(CashLocalSale sale, String state, String message, {
    String? incidentId, String? code,
  }) async {
    writes.add(state);
    current = _replace(state, message, incidentId: incidentId, code: code);
  }
}

void main() {
  test('montos exactos: centavos y sin flotantes', () {
    expect(cashCents('80.10'), 8010);
    expect(cashCents('1,5'), 150);
    expect(cashMoney(16020), '160.20');
    expect(cashMoney(3980), '39.80');
    expect(() => cashCents('-1'), throwsFormatException);
    expect(() => cashCents('1.123'), throwsFormatException);
  });

  test('el catálogo valida variante, talla, precio', () {
    final product = CashCatalogItem.fromJson({
      'variante_id': 23, 'nombre': 'Camisa masculina',
      'talla': 'M', 'color': 'Negro', 'precio_unitario': '80.10',
    });
    expect(product.cents, 8010);
    expect(product.label, contains('Camisa masculina'));
    expect(() => CashCatalogItem.fromJson({
      'variante_id': 0, 'nombre': 'Camisa', 'precio_unitario': '1.00',
    }), throwsFormatException);
    expect(_sale().total, '160.20');
  });

  test('CU15 usa Bearer y empresa para el catálogo, solo sucursal seleccionada', () async {
    final api = StaffCashApi(ApiConfig(_base), client: MockClient((request) async {
      expect(request.url.path, '/api/admin/caja/catalogo');
      expect(request.url.queryParameters['sucursal_id'], '10');
      expect(request.headers['Authorization'], 'Bearer staff-token');
      expect(request.headers['X-Empresa-Id'], '1');
      return jsonResponse({'empresa_id': 1, 'sucursal_id': 10, 'items': [
        {'variante_id': 23, 'nombre': 'Camisa', 'talla': 'M',
          'color': 'Negro', 'precio_unitario': '80.10'},
      ]});
    }));
    addTearDown(api.close);
    expect((await api.catalog('staff-token', 1, 10)).single.variantId, 23);
  });

  test('CU13 expone incidencia 409 y conserva UUID para conciliación', () async {
    final queue = _Queue(_sale());
    final api = StaffCashApi(ApiConfig(_base), client: MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/admin/caja/ventas');
      expect(request.headers['X-Empresa-Id'], '1');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['id'], _uuid);
      expect(body['efectivo'], '200.00');
      return jsonResponse({
        'detail': {
          'mensaje': 'Stock insuficiente para la variante 23',
          'incidencia_id': 'b6c5aabd-1fdd-49e6-8340-c6cc7d763111',
        },
      }, 409);
    }));
    addTearDown(api.close);
    final summary = await StaffCashSync(store: queue, api: api).synchronize(
      token: 'staff-token', companyId: 1, staffId: 7, branchId: 10);
    expect(summary.conflicts, 1);
    expect(queue.current.state, 'CONFLICTO');
    expect(queue.current.incidentId, isNotNull);
    expect(queue.current.retryable, isFalse);
  });

  test('CU15 no duplica ante error de red y confirma mismo UUID', () async {
    final queue = _Queue(_sale());
    var calls = 0;
    final api = StaffCashApi(ApiConfig(_base), client: MockClient((request) async {
      calls++;
      expect(jsonDecode(request.body)['id'], _uuid);
      if (calls == 1) throw http.ClientException('desconexión');
      return jsonResponse({'id': _uuid, 'estado': 'CONFIRMADA', 'codigo': 'VN-C-123'});
    }));
    addTearDown(api.close);
    final sync = StaffCashSync(store: queue, api: api);
    await sync.synchronize(token: 'staff-token', companyId: 1, staffId: 7, branchId: 10);
    expect(queue.current.state, 'ERROR');
    await sync.synchronize(token: 'staff-token', companyId: 1, staffId: 7, branchId: 10);
    expect(queue.current.state, 'CONFIRMADA');
    expect(queue.current.code, 'VN-C-123');
    await sync.synchronize(token: 'staff-token', companyId: 1, staffId: 7, branchId: 10);
    expect(calls, 2);
  });

  test('CU13 la resolución requiere Encargado y evidencia enviada al backend', () async {
    final api = StaffCashApi(ApiConfig(_base), client: MockClient((request) async {
      expect(request.url.path, '/api/admin/conciliacion/${_uuid}/resolver');
      expect(request.headers['X-Empresa-Id'], '1');
      expect(request.headers['Authorization'], 'Bearer encargado');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['decision'], 'ACUERDO_DOCUMENTADO');
      expect(body['referencia_constancia'], 'ACTA-CU13');
      return jsonResponse({'id': _uuid, 'estado': 'RESUELTO'});
    }));
    addTearDown(api.close);
    final result = await api.resolve('encargado', 1, _uuid,
      decision: 'ACUERDO_DOCUMENTADO',
      reference: 'ACTA-CU13',
      observation: 'Cliente aceptó el acuerdo documentado.');
    expect(result['estado'], 'RESUELTO');
  });
}
