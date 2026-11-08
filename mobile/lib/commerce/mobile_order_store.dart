import 'dart:convert';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

/// Buzón local exclusivo del Cliente. Nunca guarda tarjeta, CVV o JWT.
class MobileOrderStore {
  MobileOrderStore({this.filename = 'vestinova_compras_diferidas_v1.sqlite'});
  final String filename;
  Future<Database>? _opening;
  Future<Database> get db => _opening ??= _open();

  Future<Database> _open() async => openDatabase(
    path.join(await getDatabasesPath(), filename),
    version: 1,
    onCreate: (tx, _) async {
      await tx.execute('''
        CREATE TABLE solicitudes_cu09(
          id TEXT PRIMARY KEY, tienda TEXT NOT NULL, cliente_id INTEGER NOT NULL,
          json TEXT NOT NULL, estado TEXT NOT NULL, mensaje TEXT NOT NULL,
          creado_en TEXT NOT NULL
        )
      ''');
      await tx.execute('''
        CREATE TABLE metodos_cu09(
          tienda TEXT NOT NULL, cliente_id INTEGER NOT NULL,
          preparado INTEGER NOT NULL, actualizado_en TEXT NOT NULL,
          PRIMARY KEY (tienda, cliente_id)
        )
      ''');
    },
  );

  Future<void> setPrepared(String tienda, int customerId, bool ready) async {
    final connection = await db;
    await connection.insert('metodos_cu09', {
      'tienda': tienda,
      'cliente_id': customerId,
      'preparado': ready ? 1 : 0,
      'actualizado_en': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<bool> wasPrepared(String tienda, int customerId) async {
    final connection = await db;
    final rows = await connection.query(
      'metodos_cu09',
      columns: ['preparado'],
      where: 'tienda = ? AND cliente_id = ?',
      whereArgs: [tienda, customerId],
      limit: 1,
    );
    return rows.isNotEmpty && rows.single['preparado'] == 1;
  }

  Future<void> enqueue(
    String tienda,
    int customerId,
    Map<String, dynamic> order,
  ) async {
    final connection = await db;
    await connection.insert('solicitudes_cu09', {
      'id': order['id'],
      'tienda': tienda,
      'cliente_id': customerId,
      'json': jsonEncode(order),
      'estado': 'PENDIENTE',
      'mensaje': 'Sin Internet: no hay cobro, pedido ni reserva confirmados.',
      'creado_en': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.abort);
  }

  Future<List<MobilePendingOrder>> list(String tienda, int customerId) async {
    final connection = await db;
    final rows = await connection.query(
      'solicitudes_cu09',
      where: 'tienda = ? AND cliente_id = ?',
      whereArgs: [tienda, customerId],
      orderBy: 'creado_en DESC',
    );
    return rows.map(MobilePendingOrder.fromRow).toList();
  }

  Future<void> update(String id, String state, String message) async {
    final connection = await db;
    await connection.update(
      'solicitudes_cu09',
      {'estado': state, 'mensaje': message},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> close() async {
    final pending = _opening;
    _opening = null;
    if (pending != null) await (await pending).close();
  }
}

class MobilePendingOrder {
  MobilePendingOrder(this.id, this.payload, this.state, this.message);
  factory MobilePendingOrder.fromRow(Map<String, Object?> row) {
    return MobilePendingOrder(
      row['id'] as String,
      Map<String, dynamic>.from(jsonDecode(row['json'] as String) as Map),
      row['estado'] as String,
      row['mensaje'] as String,
    );
  }
  final String id;
  final Map<String, dynamic> payload;
  final String state;
  final String message;
}
