import 'cash_api.dart';
import 'cash_store.dart';

class CashSyncSummary {
  const CashSyncSummary({required this.confirmed, required this.conflicts, required this.pending});
  final int confirmed;
  final int conflicts;
  final int pending;
}

/// CU13: confirmación siempre central; usa el UUID y el efectivo originales.
class StaffCashSync {
  StaffCashSync({required this.store, required this.api});
  final CashSaleQueue store;
  final StaffCashApi api;
  bool _busy = false;

  Future<CashSyncSummary> synchronize({
    required String token,
    required int companyId,
    required int staffId,
    required int branchId,
  }) async {
    if (_busy) return const CashSyncSummary(confirmed: 0, conflicts: 0, pending: 0);
    _busy = true;
    var confirmed = 0, conflicts = 0;
    try {
      await store.recover(companyId, staffId, branchId);
      final rows = await store.list(companyId, staffId, branchId);
      // Orden FIFO y sin reintentos automáticos de CONFLICTO ni RECHAZADA.
      for (final sale in rows.reversed.where((r) => r.retryable)) {
        if (!await store.claim(sale)) continue;
        try {
          final result = await api.sale(token, companyId, sale.payload);
          await store.finish(sale, 'CONFIRMADA',
              'Venta confirmada en servidor; comprobante central disponible.',
              code: result['codigo'] as String);
          confirmed++;
        } on CashApiError catch (e) {
          if (e.status == 409) {
            if (e.incidentId == null) {
              // En línea la API puede responder 409 sin abrir incidente CU13.
              // Evitar presentar una conciliación inexistente o reintentar
              // indefinidamente una operación comercial rechazada.
              await store.finish(sale, 'RECHAZADA',
                'Venta no confirmada: ${e.message}. Revisa el efectivo recibido con el Encargado.');
            } else {
              await store.finish(sale, 'CONFLICTO',
                'No se confirmó la venta: ${e.message} Requiere conciliación.',
                incidentId: e.incidentId);
              conflicts++;
            }
            continue;
          }
          if (e.status == 401 || e.status == 403) {
            await store.finish(sale, 'REQUIERE_ACCESO',
              'Sesión o permisos no válidos. Inicia sesión y verifica la empresa.');
            break;
          }
          if (e.status == 422 || e.status == 404) {
            await store.finish(sale, 'RECHAZADA',
              'Venta rechazada sin movimiento de stock: ${e.message}');
            continue;
          }
          await store.finish(sale, 'ERROR',
              'No confirmado. Conservado para reintentar con el mismo UUID: ${e.message}');
          break;
        } catch (_) {
          await store.finish(sale, 'ERROR',
            'No se pudo verificar el servidor. Reintenta el mismo UUID.');
          break;
        }
      }
      final pending = (await store.list(companyId, staffId, branchId))
          .where((row) => row.retryable).length;
      return CashSyncSummary(confirmed: confirmed, conflicts: conflicts, pending: pending);
    } finally {
      _busy = false;
    }
  }
}
