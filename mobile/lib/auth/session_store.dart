import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'auth_models.dart';

class SavedSession {
  const SavedSession({
    required this.apiBase,
    required this.token,
    required this.customer,
    this.storeSlug,
    this.companyId,
    this.cachedCustomer,
    this.cachedStaff,
    this.cachedStaffContext,
  });

  factory SavedSession.fromJson(Map<String, dynamic> data) {
    final customer = data['customer'] as bool;
    final slug = data['storeSlug'] as String?;
    if (customer && (slug == null || slug.isEmpty)) {
      throw const FormatException('Falta tienda en la sesión de cliente.');
    }
    Map<String, dynamic>? cachedCustomer, cachedStaff, cachedContext;
    if (data['cachedCustomer'] != null) {
      cachedCustomer = Map<String, dynamic>.from(data['cachedCustomer'] as Map);
      final identity = CustomerAccount.fromJson(cachedCustomer);
      if (!customer || identity.store.slug != slug) {
        throw const FormatException('Copia de identidad fuera de la tienda autorizada.');
      }
    }
    if (!customer && data['cachedStaff'] is Map) {
      cachedStaff = Map<String, dynamic>.from(data['cachedStaff'] as Map);
      StaffAccount.fromJson(cachedStaff);
    }
    if (!customer && data['cachedStaffContext'] is Map) {
      cachedContext = Map<String, dynamic>.from(data['cachedStaffContext'] as Map);
      final context = StaffContext.fromJson(cachedContext);
      if (context.company.id != data['companyId'] ||
          !const {'CAJERO', 'ENCARGADO_SUCURSAL'}.contains(context.company.role)) {
        throw const FormatException('Contexto offline de personal inválido.');
      }
    }
    return SavedSession(
      apiBase: data['apiBase'] as String,
      token: data['token'] as String,
      customer: customer,
      storeSlug: slug,
      companyId: data['companyId'] as int?,
      cachedCustomer: cachedCustomer,
      cachedStaff: cachedStaff,
      cachedStaffContext: cachedContext,
    );
  }

  final String apiBase;
  final String token;
  final bool customer;
  final String? storeSlug;
  final int? companyId;

  /// Copia verificada previamente, nunca habilita operaciones centrales offline.
  final Map<String, dynamic>? cachedCustomer;
  /// Solo en FlutterSecureStorage, nunca en SQLite: identidad y sucursales
  /// que el servidor validó anteriormente. Permiten capturar caja local.
  final Map<String, dynamic>? cachedStaff;
  final Map<String, dynamic>? cachedStaffContext;

  SavedSession withCompany(int? value) => SavedSession(
    apiBase: apiBase, token: token, customer: customer,
    storeSlug: storeSlug, companyId: value,
    cachedCustomer: cachedCustomer, cachedStaff: cachedStaff,
    cachedStaffContext: value == companyId ? cachedStaffContext : null,
  );

  SavedSession withStaff(StaffAccount staff) => SavedSession(
    apiBase: apiBase, token: token, customer: false,
    companyId: companyId,
    cachedStaff: {
      'id': staff.id, 'nombre': staff.name, 'correo': staff.email,
      'es_superadministrador': staff.superadministrator,
    },
    cachedStaffContext: cachedStaffContext,
  );

  SavedSession withStaffContext(StaffContext context) => SavedSession(
    apiBase: apiBase, token: token, customer: false,
    companyId: context.company.id, cachedStaff: cachedStaff,
    cachedStaffContext: {
      'empresa': {
        'id': context.company.id, 'nombre': context.company.name,
        'slug': context.company.slug, 'rol': context.company.role,
      },
      'sucursales': context.branches.map((b) => {
        'id': b.id, 'nombre': b.name, 'codigo': b.code,
      }).toList(growable: false),
    },
  );

  SavedSession withCustomer(CustomerAccount account) => SavedSession(
    apiBase: apiBase, token: token, customer: customer,
    storeSlug: storeSlug, companyId: companyId,
    cachedCustomer: {
      'id': account.id, 'nombre': account.name, 'correo': account.email,
      'rol': 'CLIENTE',
      'empresa': {'slug': account.store.slug, 'nombre': account.store.name},
    },
  );

  Map<String, dynamic> toJson() => {
    'apiBase': apiBase,
    'token': token,
    'customer': customer,
    'storeSlug': storeSlug,
    'companyId': companyId,
    if (cachedCustomer != null) 'cachedCustomer': cachedCustomer,
    if (cachedStaff != null) 'cachedStaff': cachedStaff,
    if (cachedStaffContext != null) 'cachedStaffContext': cachedStaffContext,
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
