import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Eventos CU09 mostrados por Android. No dependen de Firebase ni de Internet.
/// El backend, y nunca la redirección de Stripe, decide si existe una compra.
class PurchaseNotices {
  PurchaseNotices._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static bool _initialized = false;
  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'vestinova_cu09_operaciones_v1',
      'Compras y solicitudes VestiNova',
      channelDescription:
          'Solicitudes offline, confirmaciones y conflictos de compras',
      importance: Importance.high,
      priority: Priority.high,
    ),
  );

  static Future<void> initialize({bool askPermission = false}) async {
    if (!Platform.isAndroid) return;
    if (!_initialized) {
      await _plugin.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        ),
      );
      _initialized = true;
    }
    if (askPermission) {
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
    }
  }

  static int _id(String uuid, String suffix) {
    var hash = 2166136261;
    for (final code in (uuid + suffix).codeUnits) {
      hash = (hash ^ code) * 16777619 & 0x7fffffff;
    }
    return hash;
  }

  static Future<void> saved(String uuid) => _show(
    _id(uuid, 'local'),
    'Solicitud guardada en VestiNova',
    'Se guardó sin Internet. Aún no se cobró ni reservó la prenda.',
  );

  static ({String title, String body})? outcome(String state) {
    switch (state) {
      case 'CONFIRMADA':
        return (
          title: 'Compra confirmada · Stripe TEST',
          body: 'El servidor verificó el pago. Revisa Mis compras; la entrega sigue pendiente.',
        );
      case 'CONFLICTO':
      case 'RECHAZADA':
        return (
          title: 'No se confirmó tu compra',
          body: 'Stock insuficiente, precio cambiado u otra validación fallida. Revisa el motivo; no hay compra confirmada.',
        );
      case 'INCIDENCIA':
        return (
          title: 'Compra requiere revisión',
          body: 'Stripe pudo acreditar un pago sin confirmar la compra. Revisa el estado; no repitas la solicitud.',
        );
      default:
        return null;
    }
  }

  static Future<void> finalState(String uuid, String state) async {
    final message = outcome(state);
    if (message == null) return;
    await _show(_id(uuid, 'final'), message.title, message.body);
  }

  static Future<void> _show(int id, String title, String body) async {
    if (!Platform.isAndroid) return;
    await initialize();
    await _plugin.show(id, title, body, _details);
  }
}
