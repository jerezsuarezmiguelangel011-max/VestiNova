import { describe, expect, it } from 'vitest';
import { formatCents, moneyToCents, normalizeCashReceived, quoteCashSale } from './cash-sale.domain';

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
  it('normaliza efectivo escrito sin decimales o con una sola cifra decimal', () => {
    const cases: Array<[string, string]> = [
      ['100', '100.00'], ['100.', '100.00'], ['100.5', '100.50'],
      ['100.50', '100.50'], ['100,5', '100.50'], ['100,50', '100.50'],
      [' 100 ', '100.00'], ['0', '0.00'], ['0.05', '0.05'],
    ];
    for (const [entry, expected] of cases) {
      expect(normalizeCashReceived(entry)).toBe(expected);
      expect(moneyToCents(normalizeCashReceived(entry)!)).not.toBeNull();
    }
    expect(moneyToCents('100')).toBeNull(); // Precios centrales continúan estrictos.
    expect(moneyToCents(normalizeCashReceived('100')!)).toBe(10000);
    expect(formatCents(10000 - 8010)).toBe('19.90');
  });

  it('rechaza efectivo mal formado, cantidades negativas y fracciones de centavo', () => {
    for (const entry of ['', ' ', '-1', '100.999', '100,999', '1,234.00',
      '1e3', 'NaN', '100000000', '1.2.3', '00', '01', '+100']) {
      expect(normalizeCashReceived(entry)).toBeNull();
    }
  });

});
