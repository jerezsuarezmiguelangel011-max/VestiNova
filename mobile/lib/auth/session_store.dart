import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SavedSession {
  const SavedSession({
    required this.apiBase,
    required this.token,
    required this.customer,
    this.storeSlug,
    this.companyId,
  });
  factory SavedSession.fromJson(Map<String, dynamic> data) {
    final customer = data['customer'] as bool;
    final slug = data['storeSlug'] as String?;
    if (customer && (slug == null || slug.isEmpty)) {
      throw const FormatException('Falta tienda en la sesión de cliente.');
    }
    return SavedSession(
      apiBase: data['apiBase'] as String,
      token: data['token'] as String,
      customer: customer,
      storeSlug: slug,
      companyId: data['companyId'] as int?,
    );
  }
  final String apiBase;
  final String token;
  final bool customer;
  final String? storeSlug;
  final int? companyId;
  SavedSession withCompany(int? value) => SavedSession(
    apiBase: apiBase,
    token: token,
    customer: customer,
    storeSlug: storeSlug,
    companyId: value,
  );
  Map<String, dynamic> toJson() => {
    'apiBase': apiBase,
    'token': token,
    'customer': customer,
    'storeSlug': storeSlug,
    'companyId': companyId,
  };
}

abstract interface class SessionStore {
  Future<SavedSession?> read();
  Future<void> write(SavedSession value);
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();
  final FlutterSecureStorage _storage;
  static const _key = 'vestinova_cu01_session_v1';

  @override
  Future<SavedSession?> read() async {
    final text = await _storage.read(key: _key);
    if (text == null) return null;
    try {
      return SavedSession.fromJson(jsonDecode(text) as Map<String, dynamic>);
    } on Object {
      await clear();
      return null;
    }
  }

  @override
  Future<void> write(SavedSession value) =>
      _storage.write(key: _key, value: jsonEncode(value.toJson()));

  @override
  Future<void> clear() => _storage.delete(key: _key);
}
