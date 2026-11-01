class Store {
  const Store({required this.slug, required this.name});
  factory Store.fromJson(Map<String, dynamic> data) =>
      Store(slug: data['slug'] as String, name: data['nombre'] as String);
  final String slug;
  final String name;
}

abstract interface class Account {
  int get id;
  String get name;
  String get email;
}

class StaffAccount implements Account {
  const StaffAccount({
    required this.id,
    required this.name,
    required this.email,
    required this.superadministrator,
  });
  factory StaffAccount.fromJson(Map<String, dynamic> data) => StaffAccount(
    id: data['id'] as int,
    name: data['nombre'] as String,
    email: data['correo'] as String,
    superadministrator: data['es_superadministrador'] == true,
  );
  @override
  final int id;
  @override
  final String name;
  @override
  final String email;
  final bool superadministrator;
}

class CustomerAccount implements Account {
  const CustomerAccount({
    required this.id,
    required this.name,
    required this.email,
    required this.store,
  });
  factory CustomerAccount.fromJson(Map<String, dynamic> data) {
    if (data['rol'] != 'CLIENTE') {
      throw const FormatException('Tipo de cuenta de cliente no válido.');
    }
    return CustomerAccount(
      id: data['id'] as int,
      name: data['nombre'] as String,
      email: data['correo'] as String,
      store: Store.fromJson(data['empresa'] as Map<String, dynamic>),
    );
  }
  @override
  final int id;
  @override
  final String name;
  @override
  final String email;
  final Store store;
}

class Company {
  const Company({
    required this.id,
    required this.name,
    required this.slug,
    required this.role,
  });
  factory Company.fromJson(Map<String, dynamic> data) => Company(
    id: data['id'] as int,
    name: data['nombre'] as String,
    slug: data['slug'] as String,
    role: data['rol'] as String,
  );
  final int id;
  final String name;
  final String slug;
  final String role;
  String get roleLabel => switch (role) {
    'ADMINISTRADOR' => 'Administrador de empresa',
    'ENCARGADO_SUCURSAL' => 'Encargado de sucursal',
    'CAJERO' => 'Cajero',
    'OPERADOR' => 'Operador (rol anterior)',
    _ => 'Acceso no reconocido',
  };
}

class Branch {
  const Branch({required this.id, required this.name, required this.code});
  factory Branch.fromJson(Map<String, dynamic> data) => Branch(
    id: data['id'] as int,
    name: data['nombre'] as String,
    code: data['codigo'] as String,
  );
  final int id;
  final String name;
  final String code;
}

class StaffContext {
  const StaffContext({required this.company, required this.branches});
  factory StaffContext.fromJson(Map<String, dynamic> data) => StaffContext(
    company: Company.fromJson(data['empresa'] as Map<String, dynamic>),
    branches: (data['sucursales'] as List<dynamic>)
        .map((item) => Branch.fromJson(item as Map<String, dynamic>))
        .toList(growable: false),
  );
  final Company company;
  final List<Branch> branches;
}

class AccessResult<T extends Account> {
  const AccessResult({required this.token, required this.account});
  final String token;
  final T account;
}
