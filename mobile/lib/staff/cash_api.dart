import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import 'cash_models.dart';

class CashApiError implements Exception {
  const CashApiError(this.message, {this.status = 0, this.network = false, this.incidentId});
  final String message;
  final int status;
  final bool network;
  final String? incidentId;
  @override
  String toString() => message;
}

/// Todas las peticiones de caja llevan Bearer de personal y empresa seleccionada.
class StaffCashApi {
  StaffCashApi(this.config, {http.Client? client}) : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;

  Future<dynamic> request(
    String method, String path, {
    required String token,
    required int companyId,
    Map<String, String> query = const {},
    Map<String, dynamic>? body,
  }) async {
    final uri = config.endpoint(path).replace(
      queryParameters: query.isEmpty ? null : query,
    );
    final request = http.Request(method, uri)
      ..followRedirects = false
      ..headers.addAll({
        'Accept': 'application/json',
        'Authorization': 'Bearer $token',
        'X-Empresa-Id': '$companyId',
      });
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 20)),
      ).timeout(const Duration(seconds: 20));
      final decoded = response.bodyBytes.isEmpty
          ? null
          : jsonDecode(utf8.decode(response.bodyBytes));
      if (response.statusCode >= 200 && response.statusCode < 300) return decoded;
      final detail = decoded is Map ? decoded['detail'] : null;
      final info = detail is Map ? detail : null;
      final message = detail is String
          ? detail
          : info?['mensaje'] is String
              ? info!['mensaje'] as String
              : 'La operación no fue aceptada (HTTP ${response.statusCode}).';
      throw CashApiError(
        message, status: response.statusCode,
        incidentId: info?['incidencia_id'] is String ? info!['incidencia_id'] as String : null,
      );
    } on SocketException {
      throw const CashApiError('Sin conexión al backend. Se conserva la operación local.', network: true);
    } on TimeoutException {
      throw const CashApiError('Respuesta incierta: reintenta con el mismo UUID.', network: true);
    } on http.ClientException {
      throw const CashApiError('No se pudo contactar al backend.', network: true);
    } on FormatException {
      throw const CashApiError('El backend devolvió una respuesta inválida.', network: true);
    }
  }

  Future<List<CashCatalogItem>> catalog(String token, int companyId, int branchId) async {
    final data = await request('GET', '/admin/caja/catalogo', token: token,
      companyId: companyId, query: {'sucursal_id': '$branchId', 'limit': '300'});
    if (data is! Map || data['sucursal_id'] != branchId || data['empresa_id'] != companyId ||
        data['items'] is! List) {
      throw const CashApiError('El catálogo no corresponde a esta empresa/sucursal.');
    }
    final raw = data['items'] as List;
    if (raw.length >= 300) {
      throw const CashApiError('Catálogo de caja demasiado grande; se conserva la copia anterior.');
    }
    return raw.map((v) => CashCatalogItem.fromJson(Map<String, dynamic>.from(v as Map))).toList();
  }

  Future<Map<String, dynamic>> sale(String token, int companyId, Map<String, dynamic> payload) async {
    final data = await request('POST', '/admin/caja/ventas',
      token: token, companyId: companyId, body: payload);
    if (data is! Map || data['id'] != payload['id'] ||
        data['estado'] != 'CONFIRMADA' || data['codigo'] is! String) {
      throw const CashApiError('La confirmación del servidor no es verificable.', network: true);
    }
    return Map<String, dynamic>.from(data);
  }

  Future<List<Map<String, dynamic>>> sales(String token, int companyId, int branchId) async {
    final data = await request('GET', '/admin/caja/ventas', token: token,
      companyId: companyId, query: {'sucursal_id': '$branchId', 'limit': '100'});
    if (data is! List) throw const CashApiError('Historial de caja inválido.');
    return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> incidents(String token, int companyId, int branchId, String state) async {
    final data = await request('GET', '/admin/conciliacion', token: token,
      companyId: companyId,
      query: {'sucursal_id': '$branchId', if (state != 'TODOS') 'estado': state});
    if (data is! List) throw const CashApiError('La bandeja de conciliación no es válida.');
    return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> incident(String token, int companyId, String id) async {
    final data = await request('GET', '/admin/conciliacion/${Uri.encodeComponent(id)}',
      token: token, companyId: companyId);
    if (data is! Map || data['id'] != id || data['datos_originales'] is! Map) {
      throw const CashApiError('No se pudo verificar el conflicto.');
    }
    return Map<String, dynamic>.from(data);
  }

  Future<Map<String, dynamic>> resolve(
    String token, int companyId, String id, {
    required String decision, required String reference, required String observation,
  }) async {
    final data = await request('POST', '/admin/conciliacion/${Uri.encodeComponent(id)}/resolver',
      token: token, companyId: companyId,
      body: {'decision': decision, 'referencia_constancia': reference, 'observacion': observation});
    if (data is! Map || data['id'] != id || data['estado'] != 'RESUELTO') {
      throw const CashApiError('El servidor no confirmó la resolución.', network: true);
    }
    return Map<String, dynamic>.from(data);
  }

  void close() => _client.close();
}
