import 'dart:convert';

/// Importes en centavos para que Flutter nunca calcule efectivo con double.
int cashCents(String raw) {
  final value = raw.trim().replaceAll(',', '.');
  if (!RegExp(r'^[0-9]{1,9}([.][0-9]{1,2})?$').hasMatch(value)) {
    throw const FormatException('Introduce un importe válido con hasta dos decimales.');
  }
  final parts = value.split('.');
  return int.parse(parts.first) * 100 +
      (parts.length == 1 ? 0 : int.parse(parts.last.padRight(2, '0')));
}

String cashMoney(int cents) {
  if (cents < 0) throw const FormatException('El importe no puede ser negativo.');
  return '${cents ~/ 100}.${(cents % 100).toString().padLeft(2, '0')}';
}

class CashCatalogItem {
  const CashCatalogItem({
    required this.variantId,
    required this.name,
    required this.size,
    required this.color,
    required this.price,
  });

  factory CashCatalogItem.fromJson(Map<String, dynamic> json) {
    final id = json['variante_id'];
    final name = json['nombre'];
    final price = json['precio_unitario'];
    if (id is! int || id <= 0 || name is! String ||
        name.isEmpty || price is! String || cashCents(price) <= 0) {
      throw const FormatException('Variante de caja inválida.');
    }
    return CashCatalogItem(
      variantId: id, name: name,
      size: json['talla'] as String? ?? '',
      color: json['color'] as String? ?? '',
      price: price,
    );
  }

  final int variantId;
  final String name;
  final String size;
  final String color;
  final String price;

  int get cents => cashCents(price);
  String get label => '$name · $size · $color · Bs $price';
  Map<String, dynamic> toJson() => {
    'variante_id': variantId,
    'nombre': name,
    'talla': size,
    'color': color,
    'precio_unitario': price,
  };
}

class CashLocalSale {
  const CashLocalSale({
    required this.id,
    required this.companyId,
    required this.staffId,
    required this.branchId,
    required this.payload,
    required this.state,
    required this.message,
    this.incidentId,
    this.code,
  });

  final String id;
  final int companyId;
  final int staffId;
  final int branchId;
  final Map<String, dynamic> payload;
  final String state;
  final String message;
  final String? incidentId;
  final String? code;

  bool get retryable => const {'PENDIENTE', 'ERROR', 'REQUIERE_ACCESO'}.contains(state);
  bool get terminal => const {'CONFIRMADA', 'CONFLICTO', 'RECHAZADA'}.contains(state);
  String get total {
    final lines = payload['lineas'] as List<dynamic>;
    var cents = 0;
    for (final raw in lines) {
      final item = Map<String, dynamic>.from(raw as Map);
      cents += cashCents(item['precio_unitario'] as String) * (item['cantidad'] as int);
    }
    return cashMoney(cents);
  }

  factory CashLocalSale.fromRow(Map<String, Object?> row) => CashLocalSale(
    id: row['id'] as String,
    companyId: row['empresa_id'] as int,
    staffId: row['cajero_id'] as int,
    branchId: row['sucursal_id'] as int,
    payload: Map<String, dynamic>.from(jsonDecode(row['payload'] as String) as Map),
    state: row['estado'] as String,
    message: row['mensaje'] as String,
    incidentId: row['incidencia_id'] as String?,
    code: row['codigo'] as String?,
  );
}
