import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

class LocalCatalogVariant {
  const LocalCatalogVariant(this.values);
  final Map<String, Object?> values;
  int get branchId => values['sucursal_id'] as int;
  int get variantId => values['variante_id'] as int;
  String get branch => values['sucursal_nombre'] as String;
  String get product => values['producto_nombre'] as String;
  String get size => values['talla'] as String;
  String get color => values['color'] as String;
  String get downloadedAt => values['guardado_en'] as String;
  String get label => '$product · $size / $color · $branch';
}

class LocalReservation {
  const LocalReservation(this.values);
  final Map<String, Object?> values;
  String get id => values['id'] as String;
  String get store => values['tienda'] as String;
  int get customerId => values['cliente_id'] as int;
  int get branchId => values['sucursal_id'] as int;
  int get variantId => values['variante_id'] as int;
  int get quantity => values['cantidad'] as int;
  String get state => values['estado'] as String;
  String get createdAt => values['creado_en'] as String;
  String get label => values['etiqueta'] as String;
  String? get message => values['mensaje'] as String?;
  String? get resultCode => values['codigo_central'] as String?;
  String? get expiresAt => values['vence_en'] as String?;
}

/// Los datos permanecen en SQLite aunque Flutter se cierre o el servidor falle.
/// Nunca se almacenan tokens, contraseñas ni respuestas de pago.
class ReservationSqlite {
  ReservationSqlite({String databaseName = 'vestinova_cu10_reservas.sqlite'})
    : _name = databaseName;

  final String _name;
  Future<Database>? _opening;

  Future<Database> get database => _opening ??= _open();

  Future<Database> _open() async {
    final location = path.join(await getDatabasesPath(), _name);
    return openDatabase(
      location,
      version: 1,
      onConfigure: (db) async {
        await db.execute('PRAGMA foreign_keys = ON');
      },
      onCreate: (db, version) async {
        await db.execute('''
        CREATE TABLE variantes_conocidas (
          tienda TEXT NOT NULL,
          sucursal_id INTEGER NOT NULL,
          variante_id INTEGER NOT NULL,
          sucursal_nombre TEXT NOT NULL,
          producto_nombre TEXT NOT NULL,
          talla TEXT NOT NULL,
          color TEXT NOT NULL,
          guardado_en TEXT NOT NULL,
          disponible INTEGER NOT NULL CHECK (disponible IN (0,1)),
          PRIMARY KEY (tienda, sucursal_id, variante_id)
        )
      ''');
        await db.execute('''
        CREATE TABLE politicas_reservas (
          tienda TEXT PRIMARY KEY NOT NULL,
          vigencia_horas INTEGER NOT NULL CHECK(vigencia_horas BETWEEN 1 AND 720),
          actualizado_en TEXT NOT NULL
        )
      ''');
        await db.execute('''
        CREATE TABLE reservas_pendientes (
          id TEXT PRIMARY KEY NOT NULL,
          tienda TEXT NOT NULL,
          cliente_id INTEGER NOT NULL,
          sucursal_id INTEGER NOT NULL,
          variante_id INTEGER NOT NULL,
          cantidad INTEGER NOT NULL CHECK (cantidad > 0 AND cantidad <= 100),
          etiqueta TEXT NOT NULL,
          creado_en TEXT NOT NULL,
          actualizado_en TEXT NOT NULL,
          estado TEXT NOT NULL,
          mensaje TEXT,
          codigo_central TEXT,
          vence_en TEXT
        )
      ''');
        await db.execute(
          'CREATE INDEX ix_reservas_cliente ON reservas_pendientes(tienda, cliente_id, creado_en)',
        );
      },
    );
  }

  Future<void> replaceCatalog(
    String store,
    List<Map<String, Object?>> items,
    int hours,
  ) async {
    if (store.isEmpty || items.length > 3000 || hours < 1 || hours > 720) {
      throw const FormatException('Catálogo no válido.');
    }
    final db = await database;
    await db.transaction((txn) async {
      await txn.delete(
        'variantes_conocidas',
        where: 'tienda = ?',
        whereArgs: [store],
      );
      for (final item in items) {
        if (item['tienda'] != store) {
          throw const FormatException('Tienda incorrecta.');
        }
        await txn.insert(
          'variantes_conocidas',
          item,
          conflictAlgorithm: ConflictAlgorithm.abort,
        );
      }
      await txn.insert('politicas_reservas', {
        'tienda': store,
        'vigencia_horas': hours,
        'actualizado_en': DateTime.now().toUtc().toIso8601String(),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    });
  }

  Future<int?> policy(String store) async {
    final db = await database;
    final rows = await db.query(
      'politicas_reservas',
      where: 'tienda = ?',
      whereArgs: [store],
      limit: 1,
    );
    return rows.isEmpty ? null : rows.single['vigencia_horas'] as int;
  }

  Future<List<LocalCatalogVariant>> catalog(String store) async {
    final db = await database;
    final records = await db.query(
      'variantes_conocidas',
      where: 'tienda = ? AND disponible = 1',
      whereArgs: [store],
      orderBy: 'producto_nombre, sucursal_nombre, talla',
    );
    return records.map(LocalCatalogVariant.new).toList(growable: false);
  }

  Future<LocalReservation> enqueue({
    required String store,
    required int customerId,
    required LocalCatalogVariant variant,
    required int quantity,
  }) async {
    if (customerId <= 0 || quantity < 1 || quantity > 100 || store.isEmpty) {
      throw const FormatException('Datos de reserva no válidos.');
    }
    final db = await database;
    final now = DateTime.now().toUtc().toIso8601String();
    final id = const Uuid().v4();
    final values = <String, Object?>{
      'id': id,
      'tienda': store,
      'cliente_id': customerId,
      'sucursal_id': variant.branchId,
      'variante_id': variant.variantId,
      'cantidad': quantity,
      'etiqueta': variant.label,
      'creado_en': now,
      'actualizado_en': now,
      'estado': 'PENDIENTE',
      'mensaje': null,
      'codigo_central': null,
      'vence_en': null,
    };
    await db.insert('reservas_pendientes', values);
    return LocalReservation(values);
  }

  Future<List<LocalReservation>> list(String store, int customerId) async {
    final db = await database;
    final records = await db.query(
      'reservas_pendientes',
      where: 'tienda = ? AND cliente_id = ?',
      whereArgs: [store, customerId],
      orderBy: 'creado_en DESC',
    );
    return records.map(LocalReservation.new).toList(growable: false);
  }

  Future<void> recover(String store, int customerId) async {
    final db = await database;
    await db.update(
      'reservas_pendientes',
      {
        'estado': 'PENDIENTE',
        'mensaje': 'Reanudada después de un cierre inesperado.',
      },
      where: 'tienda = ? AND cliente_id = ? AND estado = ?',
      whereArgs: [store, customerId, 'ENVIANDO'],
    );
  }

  Future<bool> claim(LocalReservation row) async {
    final db = await database;
    final affected = await db.rawUpdate(
      '''
      UPDATE reservas_pendientes
      SET estado = 'ENVIANDO', actualizado_en = ?, mensaje = NULL
      WHERE id = ? AND tienda = ? AND cliente_id = ?
        AND estado IN ('PENDIENTE', 'ERROR', 'REQUIERE_ACCESO')
    ''',
      [
        DateTime.now().toUtc().toIso8601String(),
        row.id,
        row.store,
        row.customerId,
      ],
    );
    return affected == 1;
  }

  Future<void> finish(
    LocalReservation row,
    String state,
    String message, {
    String? code,
    String? expiresAt,
  }) async {
    const allowed = {
      'CONFIRMADA',
      'CANCELADA',
      'VENCIDA',
      'ATENDIDA',
      'CONFLICTO',
      'RECHAZADA',
      'ERROR',
      'REQUIERE_ACCESO',
    };
    if (!allowed.contains(state)) {
      throw const FormatException('Estado inválido.');
    }
    final db = await database;
    await db.update(
      'reservas_pendientes',
      {
        'estado': state,
        'mensaje': message,
        'codigo_central': code,
        'vence_en': expiresAt,
        'actualizado_en': DateTime.now().toUtc().toIso8601String(),
      },
      where: "id = ? AND tienda = ? AND cliente_id = ? AND estado = 'ENVIANDO'",
      whereArgs: [row.id, row.store, row.customerId],
    );
  }

  Future<void> retry(LocalReservation row) async {
    final db = await database;
    await db.update(
      'reservas_pendientes',
      {
        'estado': 'PENDIENTE',
        'mensaje': null,
        'actualizado_en': DateTime.now().toUtc().toIso8601String(),
      },
      where: "id = ? AND tienda = ? AND cliente_id = ? AND estado IN ('ERROR','REQUIERE_ACCESO')",
      whereArgs: [row.id, row.store, row.customerId],
    );
  }

  Future<void> close() async {
    final opening = _opening;
    _opening = null;
    if (opening == null) return;
    try {
      await (await opening).close();
    } catch (_) {
      // No abrir/reparar la base durante dispose; si no pudo abrirse no hay sesión activa.
    }
  }
}
