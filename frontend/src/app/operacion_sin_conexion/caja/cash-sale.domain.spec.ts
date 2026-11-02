import { describe, expect, it } from 'vitest';
import { formatCents, moneyToCents, quoteCashSale } from './cash-sale.domain';

describe('CU15: cálculo de caja en bolivianos', () => {
  it('calcula cantidades, total, efectivo y cambio en centavos enteros', () => {
    expect(quoteCashSale('149.90', 2, '300.00')).toEqual({
      quantity: 2, unitCents: 14990, totalCents: 29980,
      receivedCents: 30000, changeCents: 20,
    });
    expect(formatCents(20)).toBe('0.20');
    expect(formatCents(29980)).toBe('299.80');
  });

  it('rechaza efectivo insuficiente, cantidades inválidas e importes no monetarios', () => {
    for (const received of ['0.00', '299.79', '-5.00', '300', '300.999', 'NaN', '100000000.00']) {
      expect(quoteCashSale('149.90', 2, received)).toBeNull();
    }
    for (const quantity of [0, -1, 1.5, 101, NaN, Infinity]) {
      expect(quoteCashSale('149.90', quantity, '500.00')).toBeNull();
    }
    expect(quoteCashSale('0.00', 1, '10.00')).toBeNull();
    expect(moneyToCents('0.01')).toBe(1);
    expect(moneyToCents('0.10')).toBe(10);
  });
});
