import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'auth_models.dart';

class AccessException implements Exception {
  const AccessException(this.message, {this.status = 0});
  final String message;
  final int status;
  bool get invalidSession => status == 401;
  @override
  String toString() => message;
}

class AuthApi {
  AuthApi(this.config, {http.Client? client})
    : _client = client ?? http.Client();
  final ApiConfig config;
  final http.Client _client;

  String _store(String slug) => '/tiendas/${Uri.encodeComponent(slug)}';

  Future<Store> store(String slug) async =>
      Store.fromJson(await _request('GET', _store(slug)));

  Future<AccessResult<StaffAccount>> staffLogin(
    String email,
    String password,
  ) async {
    final data = await _request(
      'POST',
      '/auth/login',
      body: {'correo': email.trim().toLowerCase(), 'password': password},
    );
    return AccessResult(
      token: data['access_token'] as String,
      account: StaffAccount.fromJson(
        data['administrador'] as Map<String, dynamic>,
      ),
    );
  }

  Future<AccessResult<CustomerAccount>> customerAccess(
    String slug,
    String email,
    String password, {
    String? name,
  }) async {
    final data = await _request(
      'POST',
      '${_store(slug)}/cuenta/${name == null ? 'login' : 'registro'}',
      body: {
        if (name != null) 'nombre': name.trim(),
        'correo': email.trim().toLowerCase(),
        'password': password,
      },
    );
    final account = CustomerAccount.fromJson(
      data['cliente'] as Map<String, dynamic>,
    );
    _checkStore(account, slug);
    return AccessResult(
      token: data['access_token'] as String,
      account: account,
    );
  }

  Future<StaffAccount> staffMe(String token) async =>
      StaffAccount.fromJson(await _request('GET', '/auth/me', token: token));

  Future<CustomerAccount> customerMe(String slug, String token) async {
    final account = CustomerAccount.fromJson(
      await _request('GET', '${_store(slug)}/cuenta/me', token: token),
    );
    _checkStore(account, slug);
    return account;
  }

  void _checkStore(CustomerAccount account, String slug) {
    if (account.store.slug != slug) {
      throw const AccessException(
        'La cuenta no corresponde a esta tienda.',
        status: 401,
      );
    }
  }

  Future<List<Company>> companies(String token) async {
    final data = await _send('GET', '/empresas', token: token);
    return (data as List<dynamic>)
        .map((item) => Company.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<StaffContext> context(String token, int companyId) async {
    final result = StaffContext.fromJson(
      await _request(
        'GET',
        '/auth/contexto',
        token: token,
        companyId: companyId,
      ),
    );
    if (result.company.id != companyId) {
      throw const AccessException(
        'La respuesta no corresponde a la empresa seleccionada.',
      );
    }
    return result;
  }

  Future<void> logout(String token, {String? slug}) async {
    await _send(
      'POST',
      slug == null ? '/auth/logout' : '${_store(slug)}/cuenta/logout',
      token: token,
    );
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    String? token,
    int? companyId,
    Map<String, dynamic>? body,
  }) async => (await _send(
    method,
    path,
    token: token,
    companyId: companyId,
    body: body,
  )) as Map<String, dynamic>;

  Future<dynamic> _send(
    String method,
    String path, {
    String? token,
    int? companyId,
    Map<String, dynamic>? body,
  }) async {
    try {
      final request = http.Request(method, config.endpoint(path));
      request.followRedirects = false;
      request.headers['Accept'] = 'application/json';
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
      if (companyId != null) request.headers['X-Empresa-Id'] = '$companyId';
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final response = await _client
          .send(request)
          .then(http.Response.fromStream)
          .timeout(const Duration(seconds: 15));
      dynamic data;
      if (response.bodyBytes.isNotEmpty) {
        data = jsonDecode(utf8.decode(response.bodyBytes));
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final detail = data is Map ? data['detail'] : null;
        final message = detail is String && detail.length < 500
            ? detail
            : response.statusCode == 422
            ? 'Revisa los campos introducidos y vuelve a intentarlo.'
            : 'No se pudo completar la solicitud. Inténtalo de nuevo.';
        throw AccessException(message, status: response.statusCode);
      }
      return data;
    } on TimeoutException {
      throw const AccessException(
        'La API tardó demasiado. Comprueba tu conexión y vuelve a intentarlo.',
      );
    } on http.ClientException {
      throw const AccessException(
        'No se pudo conectar con VestiNova. Comprueba la red y la dirección de la API.',
      );
    } on FormatException {
      throw const AccessException('La API devolvió una respuesta no válida.');
    } on TypeError {
      throw const AccessException(
        'La API devolvió una respuesta no compatible.',
      );
    }
  }

  void close() => _client.close();
}
