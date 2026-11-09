import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:http/http.dart' as http;

import '../auth/auth_api.dart';
import '../auth/auth_models.dart';
import '../config/api_config.dart';

class Garment {
  Garment(this.data) {
    if (data['precio'] is! String || data['moneda'] != 'BOB') {
      throw const FormatException('Precio de catálogo incompatible.');
    }
  }
  final Map<String, dynamic> data;
  int get id => data['id'] as int;
  String get slug => data['slug'] as String;
  String get name => data['nombre'] as String;
  String get price => '${data['precio_promocional'] ?? data['precio']} BOB';
  String? get image => data['imagen_url'] as String?;
}

class FittingVariant {
  FittingVariant(this.data);
  final Map<String, dynamic> data;
  int get id => data['variante_id'] as int;
  String get size => data['talla'] as String;
  String get color => data['color'] as String;
  String get label => 'Talla $size · $color';
  bool get compatible =>
      data['compatible'] == true && data['configuracion'] is Map;
  Map<String, dynamic> get config =>
      Map<String, dynamic>.from(data['configuracion'] as Map);
}

class CatalogApi {
  CatalogApi(this.config, {http.Client? client})
    : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;
  Future<Map<String, dynamic>> get(
    String path,
    Map<String, String> query,
  ) async {
    try {
      final request = http.Request(
        'GET',
        config.endpoint(path).replace(queryParameters: query),
      )..followRedirects = false;
      request.headers['Accept'] = 'application/json';
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 20)),
      ).timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) {
        throw AccessException(
          response.statusCode == 404
              ? 'La tienda o la prenda ya no están disponibles.'
              : 'No se pudo consultar el catálogo. Intenta nuevamente.',
          status: response.statusCode,
        );
      }
      return Map<String, dynamic>.from(
        jsonDecode(utf8.decode(response.bodyBytes)) as Map,
      );
    } on AccessException {
      rethrow;
    } on TimeoutException {
      throw const AccessException(
        'La conexión tardó demasiado. Vuelve a intentar.',
      );
    } on Object {
      throw const AccessException(
        'No se pudo conectar con el catálogo de VestiNova.',
      );
    }
  }

  Future<Map<String, dynamic>> list(Store store, String search, int offset) =>
      get('/catalogo/productos', {
        'tienda': store.slug,
        'q': search,
        'limit': '20',
        'offset': '$offset',
      });
  Future<Garment> detail(Store store, String slug) async => Garment(
    await get('/catalogo/productos/${Uri.encodeComponent(slug)}', {
      'tienda': store.slug,
    }),
  );
  Future<Map<String, dynamic>> fitting(Store store, String slug) async {
    final data = await get(
      '/catalogo/productos/${Uri.encodeComponent(slug)}/vestidor',
      {'tienda': store.slug},
    );
    if (data['tienda'] != store.slug) {
      throw const AccessException('La respuesta no corresponde a esta tienda.');
    }
    return data;
  }

  Uri assetUri(String value) {
    final uri = Uri.parse(config.base).resolve(value);
    if (!['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasFragment) {
      throw const AccessException(
        'La imagen del vestidor no tiene una dirección válida.',
      );
    }
    return uri;
  }

  Future<Uint8List> png(FittingVariant variant) async {
    try {
      final request = http.Request(
        'GET',
        assetUri(variant.config['recurso_url'] as String),
      )..followRedirects = false;
      // Los activos son públicos: nunca se adjunta token ni contraseña a otra URL.
      final response = await _client
          .send(request)
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200 ||
          (response.contentLength ?? 0) > 6 * 1024 * 1024) {
        throw const FormatException();
      }
      final buffer = BytesBuilder(copy: false);
      await for (final chunk in response.stream.timeout(
        const Duration(seconds: 20),
      )) {
        buffer.add(chunk);
        if (buffer.length > 6 * 1024 * 1024) throw const FormatException();
      }
      final bytes = buffer.takeBytes();
      if (bytes.length < 33 ||
          bytes.sublist(0, 8).join(',') != '137,80,78,71,13,10,26,10') {
        throw const FormatException();
      }
      final header = ByteData.sublistView(bytes);
      final width = header.getUint32(16);
      final height = header.getUint32(20);
      if (width < 1 || height < 1 || width > 2048 || height > 2048) {
        throw const FormatException();
      }
      final codec = await ui.instantiateImageCodec(bytes, targetWidth: 128);
      try {
        final frame = await codec.getNextFrame();
        try {
          final rgba = await frame.image.toByteData(
            format: ui.ImageByteFormat.rawRgba,
          );
          if (rgba == null) throw const FormatException();
          var transparent = false;
          var visible = false;
          for (var i = 3; i < rgba.lengthInBytes; i += 4) {
            final alpha = rgba.getUint8(i);
            transparent |= alpha < 250;
            visible |= alpha > 0;
          }
          if (!transparent || !visible) throw const FormatException();
        } finally {
          frame.image.dispose();
        }
      } finally {
        codec.dispose();
      }
      return bytes;
    } on Object {
      throw const AccessException(
        'No se pudo cargar el PNG transparente del vestidor. La foto común del catálogo no sirve como sustituto.',
      );
    }
  }

  void dispose() => _client.close();
}
