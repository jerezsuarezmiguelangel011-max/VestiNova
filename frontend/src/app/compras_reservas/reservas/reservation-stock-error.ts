import { HttpErrorResponse } from '@angular/common/http';

/** El backend calcula los saldos dentro de la transacción con bloqueo de stock. */
export function shortageMessage(error: unknown): string | null {
  if (!(error instanceof HttpErrorResponse) || error.status !== 409) return null;
  const detail = error.error?.detail;
  if (!detail || typeof detail !== 'object' || !Array.isArray(detail.disponibilidades)) return null;
  type ShortageRow = { variante_id: number; disponible: number; solicitado: number };
  const received: unknown[] = detail.disponibilidades;
  const valid: ShortageRow[] = received.filter(
    (row: unknown): row is ShortageRow => {
      if (!row || typeof row !== 'object') return false;
      const v = row as Record<string, unknown>;
      return Number.isSafeInteger(v['variante_id']) && (v['variante_id'] as number) > 0 &&
        Number.isSafeInteger(v['disponible']) && (v['disponible'] as number) >= 0 &&
        Number.isSafeInteger(v['solicitado']) && (v['solicitado'] as number) > 0;
    },
  ).slice(0, 30);
  if (!valid.length) return null;
  return 'Stock insuficiente: ' + valid.map(row =>
    `variante #${row.variante_id}, disponible ${row.disponible}, solicitado ${row.solicitado}`).join('; ') + '.';
}
