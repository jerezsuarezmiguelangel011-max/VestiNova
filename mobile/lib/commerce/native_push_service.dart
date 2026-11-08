import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'mobile_commerce_api.dart';
import 'purchase_notices.dart';

/// Identificadores públicos del proyecto Firebase, nunca claves privadas.
class NativePushService {
  static const appId = String.fromEnvironment('FIREBASE_ANDROID_APP_ID');
  static const apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const sender = String.fromEnvironment('FIREBASE_SENDER_ID');
  static const project = String.fromEnvironment('FIREBASE_PROJECT_ID');

  static StreamSubscription<RemoteMessage>? _foreground;
  static bool _ready = false;

  /// Disponible únicamente tras inicializar Firebase correctamente.
  /// Con google-services.json en Android no hacen falta --dart-define de Firebase.
  static bool get configured => _ready;

  static bool get _hasExplicitOptions =>
      appId.isNotEmpty &&
      apiKey.isNotEmpty &&
      sender.isNotEmpty &&
      project.isNotEmpty;

  /// Mientras la app está visible Android no presenta automáticamente el
  /// banner de mensajes FCM: mostrarlo como aviso local sin duplicarlo en
  /// segundo plano, donde lo presenta el sistema.
  static Future<void> initialize() async {
    if (!Platform.isAndroid) return;
    if (Firebase.apps.isEmpty) {
      if (_hasExplicitOptions) {
        await Firebase.initializeApp(
          options: const FirebaseOptions(
            apiKey: apiKey,
            appId: appId,
            messagingSenderId: sender,
            projectId: project,
          ),
        );
      } else {
        // Requiere Android con google-services.json y el Gradle plugin.
        await Firebase.initializeApp();
      }
    }
    _ready = Firebase.apps.isNotEmpty;
    if (!_ready) return;
    _foreground ??= FirebaseMessaging.onMessage.listen((message) async {
      final push = message.notification;
      if (push == null) return;
      try {
        await PurchaseNotices.remoteRestock(
          message.messageId ?? DateTime.now().microsecondsSinceEpoch.toString(),
          push.title ?? 'VestiNova · Aviso de reposición',
          push.body ?? 'Hay una actualización de stock en tu tienda.',
        );
      } catch (_) {
        // No bloquear las pantallas si Android deniega notificaciones.
      }
    });
  }

  static Future<void> register({
    required MobileCommerceApi api,
    required String tienda,
    required String token,
  }) async {
    try {
      await initialize();
    } catch (_) {
      throw StateError('Firebase no pudo iniciar. Comprueba el archivo google-services.json y la configuración Android.');
    }
    if (!configured) {
      throw StateError('Configura Firebase Cloud Messaging para Android antes de registrar el canal.');
    }
    final messaging = FirebaseMessaging.instance;
    final permission = await messaging.requestPermission(
      alert: true,
      sound: true,
      badge: true,
    );
    if (permission.authorizationStatus != AuthorizationStatus.authorized &&
        permission.authorizationStatus != AuthorizationStatus.provisional) {
      throw StateError('El dispositivo no autorizó las notificaciones.');
    }
    // El identificador legado funciona hasta activar el registro FID del proyecto.
    // ignore: deprecated_member_use
    final fcm = await messaging.getToken();
    if (fcm == null || fcm.isEmpty) {
      throw StateError('El dispositivo todavía no obtuvo un token FCM.');
    }
    await api.call(
      'POST',
      '/tiendas/$tienda/cuenta/alertas-push/canales-movil',
      token: token,
      body: {'token': fcm},
    );
  }
}
