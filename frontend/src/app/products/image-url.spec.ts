import cases from '../../../../docs/contracts/image-url-cases.json';
import { validImageUrl } from './image-url';

describe('Política de imagen compartida con backend', () => {
  it.each(cases)('$value => $valid', ({ value, valid }) => {
    expect(validImageUrl(value)).toBe(valid);
  });
  it('rechaza una URL que supera el límite de 2048 caracteres', () => {
    expect(validImageUrl(`https://example.com/${'a'.repeat(2048)}`)).toBe(false);
  });
});
