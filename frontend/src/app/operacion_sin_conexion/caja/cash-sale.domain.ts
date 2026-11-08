/**
 * CU15: preparación de venta presencial. No representa un cobro ni altera inventario.
 * El servidor deberá validar promociones, efectivo, stock e idempotencia antes de
 * cualquier comprobante definitivo.
 */
export interface CashQuote {
  quantity: number;
  unitCents: number;
  totalCents: number;
  receivedCents: number;
  changeCents: number;
}

export function moneyToCents(value: string): number | null {
  if (!/^(?:0|[1-9]\d{0,7})\.\d{2}$/.test(value)) return null;
  const [integer, fraction] = value.split('.');
  const cents = Number(integer) * 100 + Number(fraction);
  return Number.isSafeInteger(cents) ? cents : null;
}

/** Formatea el efectivo ingresado por el Cajero, sin usar floats.
 * Acepta bolivianos enteros y hasta dos decimales con punto o coma.
 * Los precios del catálogo siguen requiriendo el formato estricto N.NN.
 */
export function normalizeCashReceived(value: string): string | null {
  const entry = value.trim();
  if (!/^(?:0|[1-9]\d{0,7})(?:[.,]\d{0,2})?$/.test(entry)) return null;
  const [bolivianos, centavos = ''] = entry.replace(',', '.').split('.');
  return `${bolivianos}.${centavos.padEnd(2, '0')}`;
}

export function formatCents(cents: number): string {
  if (!Number.isSafeInteger(cents) || cents < 0) throw new Error('Importe monetario inválido.');
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
}

export function quoteCashSale(unitPrice: string, quantity: number, received: string): CashQuote | null {
  const unitCents = moneyToCents(unitPrice);
  const receivedCents = moneyToCents(received);
  if (unitCents === null || unitCents <= 0 || receivedCents === null
    || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > 100) return null;
  const totalCents = unitCents * quantity;
  if (!Number.isSafeInteger(totalCents) || receivedCents < totalCents) return null;
  return { quantity, unitCents, totalCents, receivedCents, changeCents: receivedCents - totalCents };
}

export function cashPriceValid(value: string): boolean {
  const cents = moneyToCents(value);
  return cents !== null && cents > 0;
}
