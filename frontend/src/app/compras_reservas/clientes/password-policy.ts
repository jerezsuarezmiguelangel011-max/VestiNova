import { AbstractControl, ValidationErrors } from '@angular/forms';

export const PASSWORD_POLICY_MESSAGE = 'La contraseña debe tener entre 8 y 128 caracteres e incluir una mayúscula, una minúscula, un número y un carácter especial.';

export function validNewPassword(value: string): boolean {
  const length = Array.from(value).length;
  return length >= 8 && length <= 128 && /\p{Uppercase}/u.test(value) && /\p{Lowercase}/u.test(value)
    && /\p{Nd}/u.test(value) && /[\p{P}\p{S}]/u.test(value);
}

export function newPassword(control: AbstractControl): ValidationErrors | null {
  return validNewPassword(String(control.value ?? '')) ? null : { passwordPolicy: true };
}
