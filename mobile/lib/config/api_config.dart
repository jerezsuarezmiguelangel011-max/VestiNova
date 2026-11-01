import 'package:flutter/foundation.dart';

class ApiConfig {
  ApiConfig(String value, {bool release = kReleaseMode}) {
    final candidate = Uri.tryParse(
      value.trim().replaceFirst(RegExp(r'/+$'), ''),
    );
    if (candidate == null ||
        !['http', 'https'].contains(candidate.scheme) ||
        candidate.host.isEmpty ||
        candidate.userInfo.isNotEmpty ||
        candidate.hasQuery ||
        candidate.hasFragment ||
        candidate.path != '/api' ||
        (release && candidate.scheme != 'https')) {
      throw const FormatException(
        'Configura API_BASE_URL con una dirección válida terminada en /api. '
        'La versión de distribución requiere HTTPS.',
      );
    }
    base = candidate.toString();
  }

  late final String base;
  static const defaultBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8001/api',
  );
  static const initialStore = String.fromEnvironment('STORE_SLUG');

  Uri endpoint(String path) => Uri.parse('$base$path');

  /// An entered link supplies only a public store identifier. Its host is never
  /// used for an HTTP request; requests always use the configured VestiNova API.
  static String? storeSlug(String input) {
    var value = input.trim();
    final link = Uri.tryParse(value);
    if (link != null && link.hasScheme) {
      if (!['http', 'https'].contains(link.scheme) ||
          link.userInfo.isNotEmpty) {
        return null;
      }
      final segments = link.pathSegments;
      if (segments.length < 2 ||
          !['tienda', 'tiendas'].contains(segments.first)) {
        return null;
      }
      value = segments[1];
    }
    return value.length <= 100 &&
            RegExp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$').hasMatch(value)
        ? value
        : null;
  }
}
