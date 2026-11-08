import 'mobile_commerce_api.dart';
import 'mobile_order_store.dart';
import 'purchase_notices.dart';
import '../storefront/storefront_api.dart';

/// La misma operación se usa en la pantalla, al reconectar y en WorkManager.
/// Stripe y FastAPI toman la decisión final; nunca se confirma por UI.
class PurchaseSyncService {
  const PurchaseSyncService();

  static bool _syncing = false;

  Future<void> synchronize({
    required String tienda,
    required int customerId,
    required String token,
    required MobileOrderStore store,
    required MobileCommerceApi api,
  }) async {
    if (_syncing || token.isEmpty || customerId <= 0) return;
    _syncing = true;
    try {
      final queue = await store.list(tienda, customerId);
      for (final item in queue.where(
        (x) => x.state == 'PENDIENTE' || x.state == 'PAGO_PENDIENTE',
      )) {
        try {
          final result = await api.deferredCheckout(tienda, token, item.payload);
          final state = result['estado']?.toString() ?? 'PAGO_PENDIENTE';
          final message = result['detalle']?.toString() ??
              'Consulta el estado central antes de asumir un cobro.';
          await store.update(item.id, state, message);
          await _noticeOnce(store, item.id, state);
        } on StorefrontException catch (error) {
          if (error.network || error.status == 503) {
            await store.update(item.id, 'PENDIENTE',
              'No se verificó el resultado. Se conserva el UUID para reintento.');
            break;
          }
          if (error.status == 409) {
            await store.update(item.id, 'CONFLICTO', error.message);
            await _noticeOnce(store, item.id, 'CONFLICTO');
          } else if (error.status == 401 || error.status == 403) {
            await store.update(item.id, 'REQUIERE_ACCESO',
              'Necesitas iniciar sesión nuevamente; no se confirmó la compra.');
            break;
          } else {
            await store.update(item.id, 'ERROR', error.message);
          }
        }
      }
    } finally {
      _syncing = false;
    }
  }

  Future<void> _noticeOnce(
    MobileOrderStore store, String id, String state,
  ) async {
    if (PurchaseNotices.outcome(state) == null) return;
    if (!await store.claimFinalNotice(id, state)) return;
    try {
      await PurchaseNotices.finalState(id, state);
    } catch (_) {
      // El estado comercial queda guardado aunque Android niegue permisos.
    }
  }
}
