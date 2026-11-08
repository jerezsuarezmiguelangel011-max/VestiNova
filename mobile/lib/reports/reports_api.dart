import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../auth/auth_api.dart';
import '../config/api_config.dart';

class ReportsApi {
  ReportsApi(this.config, {http.Client? client})
    : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;
  Map<String, String> _headers(String token, int company) => {
    'Authorization': 'Bearer $token',
    'X-Empresa-Id': '$company',
    'Content-Type': 'application/json',
  };
  Future<http.Response> _send(
    String path,
    String token,
    int company, {
    Map<String, dynamic>? body,
  }) async {
    try {
      final uri = config.endpoint('/admin/reportes-ia/$path');
      final request = http.Request(body == null ? 'GET' : 'POST', uri)
        ..followRedirects = false;
      request.headers.addAll(_headers(token, company));
      if (body != null) request.body = jsonEncode(body);
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 40)),
      ).timeout(const Duration(seconds: 40));
      if (response.statusCode != 200) {
        String? message;
        try {
          final data = jsonDecode(
            utf8.decode(response.bodyBytes),
          ) as Map<String, dynamic>;
          if (data['detail'] is String) message = data['detail'] as String;
        } catch (_) {
          /* Error seguro por estado. */
        }
        throw AccessException(
          message ?? 'No se pudo consultar el reporte. Revisa tu acceso y los filtros.',
          status: response.statusCode,
        );
      }
      return response;
    } on AccessException {
      rethrow;
    } on Object {
      throw const AccessException(
        'Necesitas conexión con el servidor para generar o exportar reportes.',
      );
    }
  }

  Future<Map<String, dynamic>> options(String token, int company) async =>
      jsonDecode(
        utf8.decode((await _send('opciones', token, company)).bodyBytes),
      ) as Map<String, dynamic>;
  Future<Map<String, dynamic>> generate(
    String token,
    int company,
    String prompt,
    Map<String, dynamic> filters,
  ) async => jsonDecode(
    utf8.decode(
      (await _send(
        'generar',
        token,
        company,
        body: {'consulta': prompt, 'filtros': filters},
      )).bodyBytes,
    ),
  ) as Map<String, dynamic>;
  Future<Uint8List> export(
    String token,
    int company,
    Map<String, dynamic> report,
    String format,
  ) async => (await _send(
    'exportar',
    token,
    company,
    body: {
      'tipo': report['tipo'],
      'filtros': report['filtros'],
      'formato': format,
    },
  )).bodyBytes;
  void dispose() => _client.close();
}
