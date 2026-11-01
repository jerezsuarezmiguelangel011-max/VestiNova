import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:vestinova_mobile/auth/session_store.dart';

http.Response jsonResponse(dynamic value, [int status = 200]) => http.Response(
  jsonEncode(value),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

Map<String, dynamic> staffData({bool superadministrator = false}) => {
  'id': 1,
  'nombre': 'Personal de prueba',
  'correo': 'personal@example.test',
  'rol': 'ADMINISTRADOR',
  'activo': true,
  'es_superadministrador': superadministrator,
};

Map<String, dynamic> customerData([String slug = 'tienda-a', int id = 9]) => {
  'id': id,
  'nombre': 'Cliente de prueba',
  'correo': 'cliente@example.test',
  'rol': 'CLIENTE',
  'empresa': {
    'slug': slug,
    'nombre': slug == 'tienda-a' ? 'Tienda A' : 'Tienda B',
  },
};

Map<String, dynamic> companyData(int id, [String role = 'CAJERO']) => {
  'id': id,
  'nombre': 'Empresa $id',
  'slug': 'empresa-$id',
  'activo': true,
  'rol': role,
};

Map<String, dynamic> contextData(int id, [String role = 'CAJERO']) => {
  'empresa': companyData(id, role),
  'sucursales': [
    {
      'id': id * 10,
      'empresa_id': id,
      'nombre': 'Sucursal $id',
      'codigo': 'S$id',
      'activo': true,
    },
  ],
};

Map<String, dynamic> staffAccess({
  String token = 'staff-fixture',
  bool superadministrator = false,
}) => {
  'access_token': token,
  'token_type': 'bearer',
  'expires_at': '2030-01-01T00:00:00Z',
  'administrador': staffData(superadministrator: superadministrator),
};

Map<String, dynamic> customerAccess([String slug = 'tienda-a']) => {
  'access_token': 'customer-$slug-fixture',
  'token_type': 'bearer',
  'expires_at': '2030-01-01T00:00:00Z',
  'cliente': customerData(slug),
};

class MemorySessionStore implements SessionStore {
  MemorySessionStore([this.value]);
  SavedSession? value;
  @override
  Future<SavedSession?> read() async => value;
  @override
  Future<void> write(SavedSession value) async {
    this.value = value;
  }

  @override
  Future<void> clear() async {
    value = null;
  }
}
