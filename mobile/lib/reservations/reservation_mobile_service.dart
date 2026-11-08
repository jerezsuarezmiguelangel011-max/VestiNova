import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'reservation_sqlite.dart';

/// Se comparten los contratos REST de CU10: el servidor es la autoridad final.
class MobileReservationService {
  MobileReservationService(this.config, this.store, {http.Client? client})
    : _client = client ?? http.Client();

  final ApiConfig config;
  final ReservationSqlite store;
  final http.Client _client;
  bool _syncing = false;

  Uri _api(String route, Map<String, String> query) =>
      config.endpoint(route).replace(queryParameters: query);

  Future<dynamic> _get(Uri uri) async {
    final response = await _client
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200)
      throw const FormatException('No se pudo descargar el catálogo.');
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  /// Descarga un subconjunto acotado; no reemplaza el catálogo anterior si falla.
  Future<int> download(String tienda) async {
    if (ApiConfig.storeSlug(tienda) != tienda)
      throw const FormatException('Tienda inválida.');
    final productsData = await _get(
      _api('/catalogo/productos', {
        'tienda': tienda,
        'limit': '20',
        'offset': '0',
      }),
    );
    if (productsData is! Map || productsData['items'] is! List) {
      throw const FormatException('Lista de productos no válida.');
    }
    final policy = await _get(
      _api('/tiendas/${Uri.encodeComponent(tienda)}/reservas/politica', {}),
    );
    if (policy is! Map ||
        policy['vigencia_horas'] is! int ||
        (policy['vigencia_horas'] as int) < 1 ||
        (policy['vigencia_horas'] as int) > 720) {
      throw const FormatException('Política de reservas no válida.');
    }
    final hours = policy['vigencia_horas'] as int;
    final products = productsData['items'] as List<dynamic>;
    final now = DateTime.now().toUtc().toIso8601String();
    final items = <Map<String, Object?>>[];
    for (final value in products) {
      if (value is! Map ||
          value['slug'] is! String ||
          value['nombre'] is! String) {
        throw const FormatException('Producto de catálogo no válido.');
      }
      final slug = value['slug'] as String;
      final productName = value['nombre'] as String;
      final data = await _get(
        _api(
          '/catalogo/productos/${Uri.encodeComponent(slug)}/disponibilidad',
          {'tienda': tienda},
        ),
      );
      if (data is! Map || data['items'] is! List) {
        throw const FormatException('Disponibilidad no válida.');
      }
      for (final variant in data['items'] as List<dynamic>) {
        if (variant is! Map) throw const FormatException('Variante no válida.');
        final branchId = variant['sucursal_id'];
        final variantId = variant['variante_id'];
        if (branchId is! int ||
            branchId < 1 ||
            variantId is! int ||
            variantId < 1 ||
            variant['sucursal'] is! String ||
            variant['talla'] is! String ||
            variant['color'] is! String) {
          throw const FormatException('Variante y sucursal no válidas.');
        }
        items.add({
          'tienda': tienda,
          'sucursal_id': branchId,
          'variante_id': variantId,
          'sucursal_nombre': variant['sucursal'] as String,
          'producto_nombre': productName,
          'talla': variant['talla'] as String,
          'color': variant['color'] as String,
          'guardado_en': now,
          'disponible': variant['hay_disponibilidad'] == true ? 1 : 0,
        });
      }
    }
    await store.replaceCatalog(tienda, items, hours);
    return items.where((row) => row['disponible'] == 1).length;
  }

  Future<void> synchronize(String tienda, int customerId, String token) async {
    if (_syncing || token.isEmpty || customerId < 1) return;
    _syncing = true;
    try {
      // La recuperación y el envío nunca cambian el UUID persistente.
      await store.recover(tienda, customerId);
      final pending = (await store.list(tienda, customerId))
          .where(
            (row) => const {
              'PENDIENTE',
              'ERROR',
              'REQUIERE_ACCESO',
            }.contains(row.state),
          )
          .toList()
          .reversed;
      for (final row in pending) {
        if (!await store.claim(row)) continue;
        final uri = config.endpoint(
          '/tiendas/${Uri.encodeComponent(tienda)}/reservas',
        );
        try {
          final response = await _client
              .post(
                uri,
                headers: {
                  'Content-Type': 'application/json',
                  'Accept': 'application/json',
                  'Authorization': 'Bearer $token',
                },
                body: jsonEncode({
                  'id': row.id,
                  'sucursal_id': row.branchId,
                  'lineas': [
                    {'variante_id': row.variantId, 'cantidad': row.quantity},
                  ],
                  'solicitado_en': row.createdAt,
                  'origen': 'MOVIL_OFFLINE',
                }),
              )
              .timeout(const Duration(seconds: 15));
          if (response.statusCode == 200 || response.statusCode == 201) {
            final body = jsonDecode(utf8.decode(response.bodyBytes));
            if (body is! Map ||
                body['id'] != row.id ||
                body['codigo'] is! String ||
                body['estado'] is! String) {
              await store.finish(
                row,
                'ERROR',
                'Respuesta no verificable. Reintentar con el mismo UUID.',
              );
              continue;
            }
            final state = body['estado'] as String;
            if (!const {
              'CONFIRMADA',
              'CANCELADA',
              'VENCIDA',
              'ATENDIDA',
            }.contains(state)) {
              await store.finish(
                row,
                'ERROR',
                'Estado central inesperado. Reintentar con el mismo UUID.',
              );
              continue;
            }
            await store.finish(
              row,
              state,
              'Estado verificado por el servidor.',
              code: body['codigo'] as String,
              expiresAt: body['vence_en'] as String?,
            );
          } else if (response.statusCode == 409) {
            await store.finish(
              row,
              'CONFLICTO',
              'Stock insuficiente o UUID en conflicto; revisión necesaria.',
            );
          } else if (response.statusCode == 404 || response.statusCode == 422) {
            await store.finish(
              row,
              'RECHAZADA',
              'Solicitud rechazada por referencias o datos no válidos.',
            );
          } else if (response.statusCode == 401 || response.statusCode == 403) {
            await store.finish(
              row,
              'REQUIERE_ACCESO',
              'Reautentica o revisa los permisos.',
            );
            break;
          } else {
            await store.finish(
              row,
              'ERROR',
              'No se confirmó en el servidor. Conservada para reintento.',
            );
            if (response.statusCode >= 500) break;
          }
        } on SocketException {
          await store.finish(
            row,
            'ERROR',
            'Sin conexión. Conservada para volver a sincronizar.',
          );
          break;
        } on TimeoutException {
          await store.finish(
            row,
            'ERROR',
            'Respuesta incierta. Reenvía el mismo UUID.',
          );
          break;
        } on http.ClientException {
          await store.finish(
            row,
            'ERROR',
            'No se pudo establecer la conexión.',
          );
          break;
        } on FormatException {
          await store.finish(
            row,
            'ERROR',
            'Respuesta no válida. Se conserva la operación.',
          );
          break;
        }
      }
    } finally {
      _syncing = false;
    }
  }

  Future<List<Map<String, dynamic>>> listCentral(
    String tienda,
    String token,
  ) async {
    final uri = config.endpoint('/tiendas/$tienda/reservas');
    final response = await _client
        .get(
          uri,
          headers: {
            'Authorization': 'Bearer $token',
            'Accept': 'application/json',
          },
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw const FormatException(
        'No se pudo consultar la lista central de reservas.',
      );
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    if (data is! List)
      throw const FormatException('Reservas centrales inválidas.');
    return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<void> cancelCentral(String tienda, String token, String id) async {
    final uri = config.endpoint('/tiendas/$tienda/reservas/$id/cancelar');
    final response = await _client
        .post(
          uri,
          headers: {
            'Authorization': 'Bearer $token',
            'Accept': 'application/json',
          },
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw const FormatException(
        'No se confirmó la cancelación; actualiza la lista.',
      );
    }
  }

  void close() => _client.close();
}
