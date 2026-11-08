import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:workmanager/workmanager.dart';

import '../auth/session_store.dart';
import '../config/api_config.dart';
import 'mobile_commerce_api.dart';
import 'mobile_order_store.dart';
import 'purchase_sync.dart';

const _task = 'vestinova_cu09_background_sync';

/// El trabajo del sistema no recibe ni almacena JWT en sus argumentos.
/// Se vuelve a verificar la identidad guardada de forma cifrada en el equipo.
@pragma('vm:entry-point')
void cu09CallbackDispatcher() {
  Workmanager().executeTask((taskName, inputData) async {
    if (taskName != _task || !Platform.isAndroid) return true;
    WidgetsFlutterBinding.ensureInitialized();
    final session = await SecureSessionStore().read();
    if (session == null || !session.customer ||
        session.apiBase != ApiConfig.defaultBase ||
        session.cachedCustomer == null ||
        session.storeSlug == null) {
      return true; // No cobrar tras salir de la cuenta o cambiar de API.
    }
    final customerId = session.cachedCustomer!['id'];
    if (customerId is! int || customerId <= 0) return true;
    if (inputData?['customerId'] != customerId ||
        inputData?['store'] != session.storeSlug) {
      return true; // Un trabajo antiguo nunca opera para otra cuenta.
    }
    final store = MobileOrderStore();
    final api = MobileCommerceApi(ApiConfig(session.apiBase));
    try {
      await const PurchaseSyncService().synchronize(
        tienda: session.storeSlug!, customerId: customerId,
        token: session.token, store: store, api: api,
      );
      return true;
    } catch (_) {
      // Android aplicará su política de backoff para el intento futuro.
      return false;
    } finally {
      api.close();
      await store.close();
    }
  });
}

/// Android determina la hora real de ejecución. No es un servicio continuo
/// ni garantiza un aviso instantáneo con la aplicación cerrada.
class PurchaseBackground {
  PurchaseBackground._();

  static Future<void> initialize() async {
    if (!Platform.isAndroid) return;
    await Workmanager().initialize(cu09CallbackDispatcher);
  }

  static Future<void> schedule(String store, int customerId) async {
    if (!Platform.isAndroid) return;
    await Workmanager().registerOneOffTask(
      'cu09_' + store + '_' + customerId.toString(),
      _task,
      inputData: {'store': store, 'customerId': customerId},
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingWorkPolicy.keep,
      backoffPolicy: BackoffPolicy.exponential,
      backoffPolicyDelay: const Duration(minutes: 5),
    );
  }
}
