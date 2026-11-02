import { PASSWORD_POLICY_MESSAGE, validNewPassword } from './password-policy';

describe('Política de contraseña nueva de cliente', () => {
  it.each(['aA1!123', 'aA1!' + 'a'.repeat(125), 'abc123!x', 'ABC123!X', 'Abcdef!x', 'Abc12345', 'Abc123  ', 'Abc¹ef!x'])('rechaza %s', value => expect(validNewPassword(value)).toBe(false));
  it.each(['Abc123!x', 'aA1!' + 'a'.repeat(124), ' Clave1! ', 'Ábc۱۲۳!x', 'Abc123😀x'])('admite %s', value => expect(validNewPassword(value)).toBe(true));
  it('conserva exactamente el mensaje acordado', () => expect(PASSWORD_POLICY_MESSAGE).toBe('La contraseña debe tener entre 8 y 128 caracteres e incluir una mayúscula, una minúscula, un número y un carácter especial.'));
});
