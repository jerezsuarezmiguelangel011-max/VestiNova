import 'dart:convert';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

/// Caché exclusivamente público y aislado por tienda. Nunca guarda JWT, deseos,
/// datos privados del cliente, ni cambia la BD SQLite de CU10.
class StorefrontCache {
  StorefrontCache({String name = 'vestinova_catalogo_publico_v1.sqlite'}) : _name = name;
  final String _name;
  Future<Database>? _pending;
  Future<Database> get _db => _pending ??= _open();

  Future<Database> _open() async => openDatabase(
    path.join(await getDatabasesPath(), _name),
    version: 1,
    onCreate: (db, _) async {
      await db.execute('''
        CREATE TABLE catalogo_publico_cache (
          tienda TEXT NOT NULL,
          clave TEXT NOT NULL,
          json TEXT NOT NULL,
          guardado_en TEXT NOT NULL,
          PRIMARY KEY (tienda, clave)
        )
      ''');
    },
  );

  Future<void> write(String tienda, String key, Object value) async {
    final db = await _db;
    await db.insert('catalogo_publico_cache', {
      'tienda': tienda, 'clave': key, 'json': jsonEncode(value),
      'guardado_en': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<CachedPublicData?> read(String tienda, String key) async {
    final db = await _db;
    final rows = await db.query('catalogo_publico_cache',
      where: 'tienda = ? AND clave = ?', whereArgs: [tienda, key], limit: 1);
    if (rows.isEmpty) return null;
    return CachedPublicData(
      jsonDecode(rows.single['json'] as String),
      rows.single['guardado_en'] as String,
    );
  }

  Future<void> writeBundle(String tienda, Map<String, Object> entries) async {
    final db = await _db;
    final at = DateTime.now().toUtc().toIso8601String();
    await db.transaction((tx) async {
      for (final entry in entries.entries) {
        await tx.insert('catalogo_publico_cache', {
          'tienda': tienda, 'clave': entry.key,
          'json': jsonEncode(entry.value), 'guardado_en': at,
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    });
  }

  Future<void> close() async {
    final pending = _pending;
    _pending = null;
    try { if (pending != null) await (await pending).close(); } catch (_) {}
  }
}

class CachedPublicData {
  const CachedPublicData(this.value, this.savedAt);
  final dynamic value;
  final String savedAt;
}
