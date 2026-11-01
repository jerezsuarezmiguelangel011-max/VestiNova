const passwordPolicyMessage =
    'La contraseña debe tener entre 8 y 128 caracteres e incluir una mayúscula, '
    'una minúscula, un número y un carácter especial.';

final _uppercase = RegExp(r'\p{Uppercase}', unicode: true);
final _lowercase = RegExp(r'\p{Lowercase}', unicode: true);
final _decimal = RegExp(r'\p{Nd}', unicode: true);
final _special = RegExp(r'[\p{P}\p{S}]', unicode: true);

/// Mirrors backend/password_policy.py. Never trim or apply this to login.
String? validateNewPassword(String? value) {
  final password = value ?? '';
  final length = password.runes.length;
  return length >= 8 &&
          length <= 128 &&
          _uppercase.hasMatch(password) &&
          _lowercase.hasMatch(password) &&
          _decimal.hasMatch(password) &&
          _special.hasMatch(password)
      ? null
      : passwordPolicyMessage;
}

String? validateEmail(String? value) {
  final email = (value ?? '').trim();
  return email.length <= 254 &&
          RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)
      ? null
      : 'Introduce un correo electrónico válido.';
}
