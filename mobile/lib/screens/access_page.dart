import 'package:flutter/material.dart';

import '../auth/password_policy.dart';
import '../auth/session_controller.dart';
import '../config/api_config.dart';

class AccessPage extends StatefulWidget {
  const AccessPage({super.key, required this.controller});
  final SessionController controller;
  @override
  State<AccessPage> createState() => _AccessPageState();
}

class _AccessPageState extends State<AccessPage> {
  bool _staff = false;
  final _storeForm = GlobalKey<FormState>();
  final _storeInput = TextEditingController();
  @override
  void dispose() {
    _storeInput.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.controller;
    final store = session.customerStore;
    if (store != null && !_staff) {
      return CredentialsForm(
        key: ValueKey('customer-${store.slug}'),
        controller: session,
        storeName: store.name,
        onBack: session.busy ? null : session.leaveStore,
      );
    }
    if (_staff) {
      return CredentialsForm(
        key: const ValueKey('staff'),
        controller: session,
        onBack: session.busy ? null : () => setState(() => _staff = false),
      );
    }
    return Form(
      key: _storeForm,
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Tu tienda. Tu cuenta.',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 12),
            const Text(
              'Abre tu tienda para iniciar sesión o crear una cuenta de cliente.',
            ),
            const SizedBox(height: 28),
            TextFormField(
              controller: _storeInput,
              enabled: !session.busy,
              decoration: const InputDecoration(
                labelText: 'Enlace o identificador de la tienda',
                hintText: 'nombre-de-tienda',
              ),
              autocorrect: false,
              textInputAction: TextInputAction.go,
              validator: (value) => ApiConfig.storeSlug(value ?? '') == null
                  ? 'Introduce un enlace o identificador de tienda válido.'
                  : null,
              onFieldSubmitted: (_) => _openStore(),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: session.busy ? null : _openStore,
              child: const Text('Abrir mi tienda'),
            ),
            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 12),
            TextButton.icon(
              onPressed: session.busy
                  ? null
                  : () => setState(() => _staff = true),
              icon: const Icon(Icons.badge_outlined),
              label: const Text('Acceso del personal'),
            ),
          ],
        ),
      ),
    );
  }

  void _openStore() {
    if (!widget.controller.busy && _storeForm.currentState!.validate()) {
      widget.controller.resolveStore(_storeInput.text);
    }
  }
}

class CredentialsForm extends StatefulWidget {
  const CredentialsForm({
    super.key,
    required this.controller,
    this.storeName,
    required this.onBack,
  });
  final SessionController controller;
  final String? storeName;
  final VoidCallback? onBack;
  @override
  State<CredentialsForm> createState() => _CredentialsFormState();
}

class _CredentialsFormState extends State<CredentialsForm> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _confirmation = TextEditingController();
  bool _register = false;
  bool _obscure = true;
  bool _obscureConfirmation = true;
  bool get _customer => widget.storeName != null;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.controller.busy;
    return Form(
      key: _form,
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back),
                label: Text(_customer ? 'Cambiar tienda' : 'Volver'),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              _customer ? widget.storeName! : 'Acceso del personal',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 12),
            Text(
              _customer
                  ? (_register
                        ? 'Crea tu cuenta de cliente en esta tienda.'
                        : 'Inicia sesión con tu cuenta de esta tienda.')
                  : 'Inicia sesión. Después verás las empresas a las que tienes acceso.',
            ),
            const SizedBox(height: 28),
            if (_register) ...[
              TextFormField(
                controller: _name,
                enabled: !busy,
                autofillHints: const [AutofillHints.name],
                decoration: const InputDecoration(labelText: 'Nombre completo'),
                textCapitalization: TextCapitalization.words,
                textInputAction: TextInputAction.next,
                validator: (value) {
                  final length = (value ?? '').trim().runes.length;
                  return length >= 3 && length <= 120
                      ? null
                      : 'El nombre debe tener entre 3 y 120 caracteres.';
                },
              ),
              const SizedBox(height: 20),
            ],
            TextFormField(
              controller: _email,
              enabled: !busy,
              decoration: const InputDecoration(
                labelText: 'Correo electrónico',
              ),
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              autofillHints: const [AutofillHints.email],
              textInputAction: TextInputAction.next,
              validator: validateEmail,
            ),
            const SizedBox(height: 20),
            TextFormField(
              controller: _password,
              enabled: !busy,
              obscureText: _obscure,
              decoration: InputDecoration(
                labelText: 'Contraseña',
                suffixIcon: IconButton(
                  onPressed: busy
                      ? null
                      : () => setState(() => _obscure = !_obscure),
                  tooltip: _obscure
                      ? 'Mostrar contraseña'
                      : 'Ocultar contraseña',
                  icon: Icon(
                    _obscure
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                  ),
                ),
              ),
              keyboardType: TextInputType.visiblePassword,
              autocorrect: false,
              enableSuggestions: false,
              autofillHints: [
                _register ? AutofillHints.newPassword : AutofillHints.password,
              ],
              textInputAction: _register
                  ? TextInputAction.next
                  : TextInputAction.done,
              validator: _register
                  ? validateNewPassword
                  : (value) => (value ?? '').isEmpty
                        ? 'Introduce tu contraseña.'
                        : value!.runes.length > 1024
                        ? 'La contraseña no puede superar 1024 caracteres.'
                        : null,
              onFieldSubmitted: (_) {
                if (!_register) _submit();
              },
            ),
            if (_register) ...[
              const SizedBox(height: 12),
              const Text(passwordPolicyMessage),
              const SizedBox(height: 20),
              TextFormField(
                controller: _confirmation,
                enabled: !busy,
                obscureText: _obscureConfirmation,
                decoration: InputDecoration(
                  labelText: 'Repite la contraseña',
                  suffixIcon: IconButton(
                    onPressed: busy
                        ? null
                        : () => setState(
                            () => _obscureConfirmation = !_obscureConfirmation,
                          ),
                    tooltip: _obscureConfirmation
                        ? 'Mostrar confirmación'
                        : 'Ocultar confirmación',
                    icon: Icon(
                      _obscureConfirmation
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                  ),
                ),
                keyboardType: TextInputType.visiblePassword,
                autocorrect: false,
                enableSuggestions: false,
                autofillHints: const [AutofillHints.newPassword],
                textInputAction: TextInputAction.done,
                validator: (value) => value == _password.text
                    ? null
                    : 'Las contraseñas no coinciden.',
                onFieldSubmitted: (_) => _submit(),
              ),
            ],
            const SizedBox(height: 28),
            FilledButton(
              onPressed: busy ? null : _submit,
              child: Text(
                busy
                    ? 'Comprobando…'
                    : _register
                    ? 'Crear mi cuenta'
                    : 'Iniciar sesión',
              ),
            ),
            if (_customer) ...[
              const SizedBox(height: 16),
              TextButton(
                onPressed: busy
                    ? null
                    : () {
                        _form.currentState!.reset();
                        _password.clear();
                        _confirmation.clear();
                        setState(() => _register = !_register);
                      },
                child: Text(
                  _register ? 'Ya tengo una cuenta' : 'Crear cuenta de cliente',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (widget.controller.busy || !_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    if (_customer) {
      await widget.controller.customerAccess(
        _email.text,
        _password.text,
        name: _register ? _name.text : null,
      );
    } else {
      await widget.controller.loginStaff(_email.text, _password.text);
    }
    if (mounted && widget.controller.signedIn) {
      _password.clear();
      _confirmation.clear();
    }
  }
}
