import 'dart:convert';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

import 'cash_models.dart';

/// Cifras comerciales y UUID, nunca contraseñas, JWT ni datos de tarjetas.
abstract class CashSaleQueue {
  Future<List<CashLocalSale>> list(int companyId, int staffId, int branchId);
  Future<void> recover(int companyId, int staffId, int branchId);
  Future<bool> claim(CashLocalSale sale);
  Future<void> finish(CashLocalSale sale, String status, String message, {String? incidentId, String? code});
}

class StaffCashStore implements CashSaleQueue {
  StaffCashStore({this.filename = 'vestinova_caja_cu15_v1.sqlite'});
  final String filename;
  Future<Database>? _opening;
  Future<Database> get db => _opening ??= _open();

  Future<Database> _open() async => openDatabase(
    path.join(await getDatabasesPath(), filename),
    version: 1,
    onCreate: (db, _) async {
      await db.execute('''
        CREATE TABLE catalogo_cu15(
          empresa_id INTEGER NOT NULL, cajero_id INTEGER NOT NULL,
          sucursal_id INTEGER NOT NULL, variante_id INTEGER NOT NULL,
          json TEXT NOT NULL, actualizado_en TEXT NOT NULL,
          PRIMARY KEY (empresa_id, cajero_id, sucursal_id, variante_id)
        )
      ''');
      await db.execute('''
        CREATE TABLE ventas_cu15(
          id TEXT PRIMARY KEY NOT NULL,
          empresa_id INTEGER NOT NULL, cajero_id INTEGER NOT NULL,
          sucursal_id INTEGER NOT NULL, payload TEXT NOT NULL,
          estado TEXT NOT NULL, mensaje TEXT NOT NULL,
          incidencia_id TEXT, codigo TEXT, creado_en TEXT NOT NULL,
          actualizado_en TEXT NOT NULL
        )
      ''');
      await db.execute('''
        CREATE INDEX ix_ventas_cu15_actor
          ON ventas_cu15(empresa_id, cajero_id, sucursal_id, creado_en)
      ''');
    },
  );

  Future<void> replaceCatalog(int companyId, int staffId, int branchId, List<CashCatalogItem> items) async {
    if (companyId <= 0 || staffId <= 0 || branchId <= 0 ||
        items.length >= 300 || items.map((e) => e.variantId).toSet().length != items.length) {
      throw const FormatException('Catálogo de caja incompleto o duplicado.');
    }
    final connection = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    await connection.transaction((tx) async {
      await tx.delete('catalogo_cu15',
        where: 'empresa_id = ? AND cajero_id = ? AND sucursal_id = ?',
        whereArgs: [companyId, staffId, branchId]);
      for (final item in items) {
        await tx.insert('catalogo_cu15', {
          'empresa_id': companyId,
          'cajero_id': staffId,
          'sucursal_id': branchId,
          'variante_id': item.variantId,
          'json': jsonEncode(item.toJson()),
          'actualizado_en': now,
        });
      }
    });
  }

  Future<List<CashCatalogItem>> catalog(int companyId, int staffId, int branchId) async {
    final connection = await db;
    final rows = await connection.query('catalogo_cu15',
      where: 'empresa_id = ? AND cajero_id = ? AND sucursal_id = ?',
      whereArgs: [companyId, staffId, branchId], orderBy: 'variante_id');
    return rows.map((r) => CashCatalogItem.fromJson(
      Map<String, dynamic>.from(jsonDecode(r['json'] as String) as Map))).toList();
  }

  Future<void> enqueue(int companyId, int staffId, int branchId, Map<String, dynamic> payload) async {
    if (companyId <= 0 || staffId <= 0 || branchId <= 0 ||
        payload['sucursal_id'] != branchId || payload['id'] is! String ||
        payload['lineas'] is! List || (payload['lineas'] as List).isEmpty) {
      throw const FormatException('Venta de caja local inválida.');
    }
    final connection = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    await connection.insert('ventas_cu15', {
      'id': payload['id'], 'empresa_id': companyId, 'cajero_id': staffId,
      'sucursal_id': branchId, 'payload': jsonEncode(payload),
      'estado': 'PENDIENTE', 'mensaje': 'No confirmada por el servidor. No emitir comprobante central.',
      'incidencia_id': null, 'codigo': null,
      'creado_en': now, 'actualizado_en': now,
    }, conflictAlgorithm: ConflictAlgorithm.abort);
  }

  @override
  Future<List<CashLocalSale>> list(int companyId, int staffId, int branchId) async {
    final connection = await db;
    final rows = await connection.query('ventas_cu15',
      where: 'empresa_id = ? AND cajero_id = ? AND sucursal_id = ?',
      whereArgs: [companyId, staffId, branchId], orderBy: 'creado_en DESC');
    return rows.map(CashLocalSale.fromRow).toList();
  }

  @override
  Future<void> recover(int companyId, int staffId, int branchId) async {
    final connection = await db;
    await connection.update('ventas_cu15',
      {'estado': 'ERROR', 'mensaje': 'Envío interrumpido. Reintentar el mismo UUID.'},
      where: "empresa_id = ? AND cajero_id = ? AND sucursal_id = ? AND estado = 'ENVIANDO'",
      whereArgs: [companyId, staffId, branchId]);
  }

  @override
  Future<bool> claim(CashLocalSale sale) async {
    final connection = await db;
    final changed = await connection.rawUpdate('''
      UPDATE ventas_cu15 SET estado = 'ENVIANDO', actualizado_en = ?
      WHERE id = ? AND empresa_id = ? AND cajero_id = ? AND sucursal_id = ?
        AND estado IN ('PENDIENTE','ERROR','REQUIERE_ACCESO')
    ''', [DateTime.now().toUtc().toIso8601String(),
      sale.id, sale.companyId, sale.staffId, sale.branchId]);
    return changed == 1;
  }

  @override
  Future<void> finish(CashLocalSale sale, String state, String message, {String? incidentId, String? code}) async {
    if (!const {'CONFIRMADA', 'CONFLICTO', 'RECHAZADA', 'ERROR', 'REQUIERE_ACCESO'}.contains(state)) {
      throw const FormatException('Estado de venta no válido.');
    }
    final connection = await db;
    await connection.update('ventas_cu15', {
      'estado': state, 'mensaje': message,
      'incidencia_id': incidentId, 'codigo': code,
      'actualizado_en': DateTime.now().toUtc().toIso8601String(),
    }, where: "id = ? AND empresa_id = ? AND cajero_id = ? AND sucursal_id = ? AND estado = 'ENVIANDO'",
    whereArgs: [sale.id, sale.companyId, sale.staffId, sale.branchId]);
  }

  Future<void> close() async {
    final opening = _opening;
    _opening = null;
    if (opening != null) await (await opening).close();
  }
}
