import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'mobile_commerce_api.dart';

/// Identificadores públicos del proyecto Firebase, nunca claves privadas.
class NativePushService {
  static const appId = String.fromEnvironment('FIREBASE_ANDROID_APP_ID');
  static const apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const sender = String.fromEnvironment('FIREBASE_SENDER_ID');
  static const project = String.fromEnvironment('FIREBASE_PROJECT_ID');

  static bool get configured =>
      appId.isNotEmpty &&
      apiKey.isNotEmpty &&
      sender.isNotEmpty &&
      project.isNotEmpty;

  static Future<void> register({
    required MobileCommerceApi api,
    required String tienda,
    required String token,
  }) async {
    if (!configured) {
      throw StateError(
        'Configura Firebase Cloud Messaging para Android antes de registrar el canal.',
      );
    }
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: apiKey,
          appId: appId,
          messagingSenderId: sender,
          projectId: project,
        ),
      );
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
