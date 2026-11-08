import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../storefront/storefront_api.dart';

/// API pública y privada del bloque 2. Los tokens solo se pasan en memoria.
class MobileCommerceApi {
  MobileCommerceApi(this.config, {http.Client? client})
      : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;
  void close() => _client.close();

  Future<dynamic> call(String method, String route, {String? token,
    Map<String, dynamic>? body, Map<String, String>? query}) async {
    final uri = config.endpoint(route).replace(queryParameters: query);
    final request = http.Request(method, uri)
      ..followRedirects = false
      ..headers['Accept'] = 'application/json';
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 15)),
      ).timeout(const Duration(seconds: 15));
      final Object? decoded = response.bodyBytes.isEmpty ? null :
          jsonDecode(utf8.decode(response.bodyBytes));
      if (response.statusCode >= 200 && response.statusCode < 300) return decoded;
      final detail = decoded is Map ? decoded['detail'] : null;
      throw StorefrontException(
        detail is String ? detail : 'Respuesta HTTP ' + response.statusCode.toString(),
        status: response.statusCode, network: response.statusCode >= 500);
    } on SocketException {
      throw const StorefrontException('Sin conexión con VestiNova.', network: true);
    } on TimeoutException {
      throw const StorefrontException('El servidor tardó demasiado.', network: true);
    } on http.ClientException {
      throw const StorefrontException('El servidor no está disponible.', network: true);
    } on FormatException {
      throw const StorefrontException('La respuesta del servidor no es válida.');
    }
  }

  String purchases(String slug) => '/tiendas/$slug/compras';
  String account(String slug) => '/tiendas/$slug/cuenta';

  Future<Map<String,dynamic>> capabilities(String slug) async =>
      Map<String,dynamic>.from(await call('GET', purchases(slug) + '/capacidades') as Map);

  Future<Map<String,dynamic>> cardStatus(String slug, String token) async =>
      Map<String,dynamic>.from(await call('GET',
          purchases(slug) + '/offline/metodo', token: token) as Map);

  Future<Map<String,dynamic>> prepareCard(String slug, String token) async =>
      Map<String,dynamic>.from(await call('POST',
          purchases(slug) + '/offline/preparar-metodo', token: token) as Map);

  Future<Map<String,dynamic>> onlineCheckout(
      String slug, String token, Map<String,dynamic> payload) async =>
      Map<String,dynamic>.from(await call('POST', purchases(slug) + '/checkout',
        token: token, body: payload) as Map);

  Future<Map<String,dynamic>> deferredCheckout(
      String slug, String token, Map<String,dynamic> payload) async =>
      Map<String,dynamic>.from(await call('POST', purchases(slug) + '/offline/sincronizar',
        token: token, body: payload) as Map);

  Future<Map<String,dynamic>> checkoutStatus(
      String slug, String token, String id, {bool reconcile = false}) async =>
      Map<String,dynamic>.from(await call(reconcile ? 'POST' : 'GET',
          purchases(slug) + '/$id/' + (reconcile ? 'reconciliar' : 'estado'),
          token: token) as Map);

  Future<List<Map<String,dynamic>>> branches(String slug) async =>
      (await call('GET', '/catalogo/sucursales', query: {'tienda':slug}) as List)
      .map((e) => Map<String,dynamic>.from(e as Map)).toList();

  Future<List<Map<String,dynamic>>> history(String slug, String token) async {
    final data = await call('GET', account(slug) + '/compras', token: token) as Map;
    return (data['items'] as List)
        .map((e) => Map<String,dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String,dynamic>>> reviews(String slug, String token) async {
    final data = await call('GET', account(slug) + '/valoraciones', token: token) as Map;
    return (data['items'] as List)
        .map((e) => Map<String,dynamic>.from(e as Map)).toList();
  }

  Future<Map<String,dynamic>> publishReview(String slug, String token, {
    required String purchaseId, required int productId,
    required int rating, required String comment, int? reviewId,
  }) async => Map<String,dynamic>.from(await call(
    reviewId == null ? 'POST' : 'PATCH',
    account(slug) + '/valoraciones' + (reviewId == null ? '' : '/$reviewId'),
    token: token,
    body: {
      if (reviewId == null) 'compra_id': purchaseId,
      if (reviewId == null) 'producto_id': productId,
      'puntuacion': rating, 'comentario': comment,
    },
  ) as Map);

  Future<Map<String,dynamic>> alertsConfig(String slug, String token) async =>
      Map<String,dynamic>.from(await call('GET',
        account(slug) + '/alertas-push/config', token: token) as Map);

  Future<List<Map<String,dynamic>>> alerts(String slug, String token) async {
    final data = await call('GET', account(slug) + '/alertas-push/avisos',
      token: token) as Map;
    return (data['items'] as List)
      .map((e) => Map<String,dynamic>.from(e as Map)).toList();
  }

  Future<Map<String,dynamic>> subscribeAlert(String slug, String token,
      int variantId, int branchId) async =>
      Map<String,dynamic>.from(await call('POST',
        account(slug) + '/alertas-push/avisos', token: token,
        body: {'variante_id': variantId, 'sucursal_id': branchId}) as Map);

  Future<void> cancelAlert(String slug, String token, int id) async {
    await call('DELETE', account(slug) + '/alertas-push/avisos/$id',
      token: token);
  }
}
