import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'storefront_models.dart';

class StorefrontException implements Exception {
  const StorefrontException(
    this.message, {
    this.status = 0,
    this.network = false,
  });
  final String message;
  final int status;
  final bool network;
  @override
  String toString() => message;
}

/// Cliente REST multiplataforma. El servidor decide tienda, precio, stock y permisos.
class StorefrontApi {
  StorefrontApi(this.config, {http.Client? client})
    : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;
  void close() => _client.close();

  Future<dynamic> _call(
    String method,
    String path, {
    Map<String, String> query = const {},
    Map<String, dynamic>? body,
    String? token,
  }) async {
    final url = config
        .endpoint(path)
        .replace(queryParameters: query.isEmpty ? null : query);
    final req = http.Request(method, url)
      ..followRedirects = false
      ..headers['Accept'] = 'application/json';
    if (token != null && token.isNotEmpty) {
      req.headers['Authorization'] = 'Bearer $token';
    }
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await _client.send(req).timeout(const Duration(seconds: 15)),
      ).timeout(const Duration(seconds: 15));
      final dynamic data = response.bodyBytes.isEmpty
          ? null
          : jsonDecode(utf8.decode(response.bodyBytes));
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return data;
      }
      final detail = data is Map ? data['detail'] : null;
      final msg = detail is String
          ? detail
          : 'La operación no pudo completarse (${response.statusCode}).';
      throw StorefrontException(
        msg,
        status: response.statusCode,
        network: response.statusCode >= 500,
      );
    } on SocketException {
      throw const StorefrontException(
        'Sin conexión con VestiNova.',
        network: true,
      );
    } on TimeoutException {
      throw const StorefrontException(
        'La conexión tardó demasiado.',
        network: true,
      );
    } on http.ClientException {
      throw const StorefrontException(
        'No se pudo contactar con el servidor.',
        network: true,
      );
    } on FormatException {
      throw const StorefrontException(
        'El servidor devolvió información no válida.',
      );
    }
  }

  Map<String, dynamic> _obj(dynamic value) {
    if (value is! Map<String, dynamic>) {
      throw const StorefrontException('Formato de respuesta inesperado.');
    }
    return value;
  }

  List<dynamic> _array(dynamic value) {
    if (value is! List) {
      throw const StorefrontException('Listado no válido.');
    }
    return value;
  }

  Future<StorePage> products(
    String tienda, {
    StoreFilters filters = const StoreFilters(),
    int limit = 20,
    int offset = 0,
  }) async {
    final data = await _call(
      'GET',
      '/catalogo/productos',
      query: {
        'tienda': tienda,
        ...filters.toQuery(),
        'limit': '$limit',
        'offset': '$offset',
      },
    );
    return StorePage.fromJson(_obj(data));
  }

  Future<List<StoreCategory>> categories(String tienda) async =>
      _array(
            await _call(
              'GET',
              '/catalogo/categorias',
              query: {'tienda': tienda},
            ),
          )
          .map(
            (e) => StoreCategory.fromJson(Map<String, dynamic>.from(e as Map)),
          )
          .toList();

  Future<StoreProduct> product(String tienda, String slug) async =>
      StoreProduct.fromJson(
        _obj(
          await _call(
            'GET',
            '/catalogo/productos/${Uri.encodeComponent(slug)}',
            query: {'tienda': tienda},
          ),
        ),
      );

  Future<List<StoreVariant>> variants(String tienda, String slug) async =>
      _array(
            await _call(
              'GET',
              '/catalogo/productos/${Uri.encodeComponent(slug)}/variantes',
              query: {'tienda': tienda},
            ),
          )
          .map(
            (e) => StoreVariant.fromJson(Map<String, dynamic>.from(e as Map)),
          )
          .toList();

  Future<List<StoreStock>> availability(String tienda, String slug) async =>
      _array(
            _obj(
              await _call(
                'GET',
                '/catalogo/productos/${Uri.encodeComponent(slug)}/disponibilidad',
                query: {'tienda': tienda},
              ),
            )['items'],
          )
          .map((e) => StoreStock.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();

  Future<Map<String, dynamic>> allVariantsPage(
    String tienda,
    int offset,
  ) async => _obj(
    await _call(
      'GET',
      '/catalogo/variantes',
      query: {'tienda': tienda, 'limit': '100', 'offset': '$offset'},
    ),
  );

  Future<List<StoreProduct>> recommendations(
    String tienda, {
    String? reference,
    String? size,
    String? color,
    int? branchId,
  }) async {
    final payload = _obj(
      await _call(
        'GET',
        '/catalogo/recomendaciones',
        query: {
          'tienda': tienda,
          'limit': '12',
          'producto_slug': ?reference,
          if (size != null && size.isNotEmpty) 'talla': size,
          if (color != null && color.isNotEmpty) 'color': color,
          if (branchId != null) 'sucursal_id': '$branchId',
        },
      ),
    );
    return _array(payload['items'])
        .map((e) => StoreProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<List<StoreProduct>> personalized(String tienda, String token) async {
    final payload = _obj(
      await _call(
        'GET',
        '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/recomendaciones/sugerencias',
        token: token,
      ),
    );
    return _array(payload['items'])
        .map((e) => StoreProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<bool> consent(String tienda, String token) async =>
      _obj(
        await _call(
          'GET',
          '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/recomendaciones/preferencias',
          token: token,
        ),
      )['habilitado'] ==
      true;

  Future<bool> setConsent(String tienda, String token, bool enabled) async =>
      _obj(
        await _call(
          'PUT',
          '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/recomendaciones/preferencias',
          token: token,
          body: {'habilitado': enabled},
        ),
      )['habilitado'] ==
      true;

  Future<void> recordVisit(
    String tienda,
    String token,
    String productSlug,
  ) async {
    await _call(
      'POST',
      '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/recomendaciones/visitas',
      token: token,
      body: {'producto_slug': productSlug},
    );
  }

  Future<List<StoreProduct>> compare(
    String tienda,
    List<int> productIds,
  ) async {
    if (productIds.length < 2 ||
        productIds.length > 4 ||
        productIds.toSet().length != productIds.length) {
      throw const StorefrontException(
        'Selecciona entre dos y cuatro prendas diferentes.',
      );
    }
    final result = _obj(
      await _call(
        'POST',
        '/catalogo/comparar',
        body: {'tienda': tienda, 'producto_ids': productIds},
      ),
    );
    return _array(result['items'])
        .map((e) => StoreProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<List<StoreWish>> wishes(String tienda, String token) async {
    final result = _obj(
      await _call(
        'GET',
        '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/deseos',
        token: token,
      ),
    );
    return _array(result['items'])
        .map((e) => StoreWish.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<bool> addWish(String tienda, String token, int variantId) async =>
      _obj(
        await _call(
          'POST',
          '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/deseos',
          token: token,
          body: {'variante_id': variantId},
        ),
      )['agregado'] ==
      true;

  Future<void> removeWish(String tienda, String token, int variantId) async {
    await _call(
      'DELETE',
      '/tiendas/${Uri.encodeComponent(tienda)}/cuenta/deseos/$variantId',
      token: token,
    );
  }
}
