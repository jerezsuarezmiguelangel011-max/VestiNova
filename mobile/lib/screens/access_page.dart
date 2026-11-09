import 'package:flutter/material.dart';

import '../auth/auth_models.dart';
import '../auth/password_policy.dart';
import '../auth/session_controller.dart';
import '../config/api_config.dart';

class AccessPage extends StatefulWidget {
  const AccessPage({
    super.key,
    required this.controller,
    this.startWithStaff = false,
    this.onLeaveStaff,
  });
  final SessionController controller;

  /// Permite abrir directamente el login del personal desde una tienda pública.
  final bool startWithStaff;
  final VoidCallback? onLeaveStaff;
  @override
  State<AccessPage> createState() => _AccessPageState();
}

class _AccessPageState extends State<AccessPage> {
  bool _staff = false;

  @override
  void initState() {
    super.initState();
    _staff = widget.startWithStaff;
  }

  bool _shopsLoading = false;
  bool _shopsLoaded = false;
  String? _shopsError;
  List<Store> _shops = const [];
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
        onBack: session.busy
            ? null
            : () {
                setState(() => _staff = false);
                widget.onLeaveStaff?.call();
              },
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF153F30), Color(0xFF32735B)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(24),
          ),
          padding: const EdgeInsets.fromLTRB(24, 26, 24, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Wrap(
                spacing: 8,
                runSpacing: 7,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Icon(
                    Icons.checkroom_outlined,
                    color: Color(0xFFE5EBDA),
                    size: 27,
                  ),
                  SizedBox(width: 10),
                  Text(
                    'VESTINOVA  /  MENSWEAR',
                    style: TextStyle(
                      color: Color(0xFFD2E5D6),
                      letterSpacing: 2.0,
                      fontWeight: FontWeight.w700,
                      fontSize: 10,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 28),
              Text(
                'Tu tienda. Tu cuenta.',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: Colors.white,
                  fontFamily: 'serif',
                  fontWeight: FontWeight.w600,
                  height: 1.14,
                  fontSize: 35,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Moda masculina para cada estilo. Explora tiendas, '
                'elige tu sucursal y descubre tu próxima prenda.',
                style: TextStyle(color: Color(0xFFE2EBDF), height: 1.5),
              ),
            ],
          ),
        ),
        const SizedBox(height: 22),
        _panel(
          context: context,
          title: 'Explorar tiendas',
          subtitle: 'Encuentra las tiendas disponibles en VestiNova.',
          icon: Icons.storefront_outlined,
          body: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              OutlinedButton.icon(
                onPressed: session.busy || _shopsLoading ? null : _loadShops,
                icon: const Icon(Icons.storefront),
                label: Text(
                  _shopsLoading
                      ? 'Consultando tiendas…'
                      : 'Ver tiendas disponibles',
                ),
              ),
              if (_shopsLoading) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              if (_shopsError != null) ...[
                const SizedBox(height: 12),
                Text(
                  _shopsError!,
                  style: const TextStyle(color: Color(0xFF9A4C3B)),
                ),
              ],
              if (_shopsLoaded && _shops.isEmpty && !_shopsLoading)
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Text(
                    'Todavía no hay tiendas disponibles. Puedes usar el identificador.',
                  ),
                ),
              for (final shop in _shops) ...[
                const SizedBox(height: 10),
                Material(
                  color: const Color(0xFFF4F7F0),
                  borderRadius: BorderRadius.circular(14),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: session.busy
                        ? null
                        : () => session.resolveStore(shop.slug),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 15,
                        vertical: 14,
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFFDFEDE1),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(
                              Icons.store_mall_directory_outlined,
                              color: Color(0xFF1B4935),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  shop.name,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                Text(
                                  shop.slug,
                                  style: const TextStyle(
                                    color: Color(0xFF648070),
                                    fontSize: 11,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const Icon(Icons.arrow_forward_ios, size: 15),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 16),
        _panel(
          context: context,
          title: '¿Tienes un enlace de tienda?',
          subtitle: 'También puedes ingresar directamente su identificador.',
          icon: Icons.link_rounded,
          body: Form(
            key: _storeForm,
            child: AutofillGroup(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    controller: _storeInput,
                    enabled: !session.busy,
                    decoration: const InputDecoration(
                      labelText: 'Enlace o identificador de la tienda',
                      hintText: 'nombre-de-tienda',
                      prefixIcon: Icon(Icons.search_rounded),
                    ),
                    autocorrect: false,
                    textInputAction: TextInputAction.go,
                    validator: (value) =>
                        ApiConfig.storeSlug(value ?? '') == null
                        ? 'Introduce un enlace o identificador de tienda válido.'
                        : null,
                    onFieldSubmitted: (_) => _openStore(),
                  ),
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    onPressed: session.busy ? null : _openStore,
                    icon: const Icon(Icons.arrow_forward_rounded),
                    label: const Text('Abrir mi tienda'),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 17),
        Container(
          padding: const EdgeInsets.fromLTRB(19, 19, 19, 14),
          decoration: BoxDecoration(
            color: const Color(0xFFE8EEE6),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: const Color(0xFFC9DACA)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(
                    Icons.admin_panel_settings_outlined,
                    color: Color(0xFF275A43),
                  ),
                  SizedBox(width: 9),
                  Expanded(
                    child: Text(
                      '¿Administras una tienda?',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                'Administradores, encargados y personal autorizado '
                'pueden ingresar con sus propias credenciales.',
                style: TextStyle(height: 1.45),
              ),
              const SizedBox(height: 11),
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
        const SizedBox(height: 12),
      ],
    );
  }

  Widget _panel({
    required BuildContext context,
    required String title,
    required String subtitle,
    required IconData icon,
    required Widget body,
  }) {
    return Container(
      padding: const EdgeInsets.all(19),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFDDE6DD)),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: const Color(0xFF276347), size: 22),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 17,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Text(
            subtitle,
            style: const TextStyle(
              color: Color(0xFF647668),
              height: 1.45,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 17),
          body,
        ],
      ),
    );
  }

  Future<void> _loadShops() async {
    if (_shopsLoading) return;
    setState(() {
      _shopsLoading = true;
      _shopsError = null;
    });
    try {
      final stores = await widget.controller.api.publicStores();
      if (!mounted) return;
      setState(() {
        _shops = stores;
        _shopsLoaded = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(
        () => _shopsError = 'No pudimos cargar las tiendas. Revisa tu conexión e inténtalo de nuevo.',
      );
    } finally {
      if (mounted) setState(() => _shopsLoading = false);
    }
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
    final heading = _customer ? widget.storeName! : 'Acceso administrativo';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back_rounded),
            label: Text(_customer ? 'Cambiar tienda' : 'Volver a VestiNova'),
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.fromLTRB(23, 25, 23, 27),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF163D2E), Color(0xFF316D54)],
            ),
            borderRadius: BorderRadius.circular(23),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                _customer
                    ? Icons.storefront_outlined
                    : Icons.admin_panel_settings_outlined,
                color: const Color(0xFFE9EEE0),
                size: 34,
              ),
              const SizedBox(height: 18),
              Text(
                _customer ? 'TU TIENDA' : 'VESTINOVA · PERSONAL',
                style: const TextStyle(
                  fontSize: 10,
                  letterSpacing: 2,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFFD2E6D4),
                ),
              ),
              const SizedBox(height: 7),
              Text(
                heading,
                style: const TextStyle(
                  fontFamily: 'serif',
                  fontSize: 31,
                  height: 1.2,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 11),
              Text(
                _customer
                    ? (_register
                          ? 'Crea tu cuenta para disfrutar esta colección.'
                          : 'Inicia sesión para continuar con tus compras y deseos.')
                    : 'Ingresa como superadministrador SaaS, administrador, encargado o cajero. '
                          'Tus permisos se validarán en el servidor.',
                style: const TextStyle(color: Color(0xFFE2ECE4), height: 1.5),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.fromLTRB(20, 25, 20, 24),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: const Color(0xFFDCE6DC)),
            borderRadius: BorderRadius.circular(19),
          ),
          child: Form(
            key: _form,
            child: AutofillGroup(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    _register ? 'Crea tu cuenta' : 'Bienvenido de nuevo',
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 20,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Completa tus datos para continuar de forma segura.',
                    style: TextStyle(fontSize: 12, color: Color(0xFF688071)),
                  ),
                  const SizedBox(height: 22),
                  if (_register) ...[
                    TextFormField(
                      controller: _name,
                      enabled: !busy,
                      autofillHints: const [AutofillHints.name],
                      decoration: const InputDecoration(
                        labelText: 'Nombre completo',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                      textCapitalization: TextCapitalization.words,
                      textInputAction: TextInputAction.next,
                      validator: (value) {
                        final length = (value ?? '').trim().runes.length;
                        return length >= 3 && length <= 120
                            ? null
                            : 'El nombre debe tener entre 3 y 120 caracteres.';
                      },
                    ),
                    const SizedBox(height: 17),
                  ],
                  TextFormField(
                    controller: _email,
                    enabled: !busy,
                    decoration: const InputDecoration(
                      labelText: 'Correo electrónico',
                      prefixIcon: Icon(Icons.alternate_email_rounded),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    autofillHints: const [AutofillHints.email],
                    textInputAction: TextInputAction.next,
                    validator: validateEmail,
                  ),
                  const SizedBox(height: 18),
                  TextFormField(
                    controller: _password,
                    enabled: !busy,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      prefixIcon: const Icon(Icons.lock_outline_rounded),
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
                      _register
                          ? AutofillHints.newPassword
                          : AutofillHints.password,
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
                    const SizedBox(height: 18),
                    TextFormField(
                      controller: _confirmation,
                      enabled: !busy,
                      obscureText: _obscureConfirmation,
                      decoration: InputDecoration(
                        labelText: 'Repite la contraseña',
                        prefixIcon: const Icon(Icons.verified_user_outlined),
                        suffixIcon: IconButton(
                          onPressed: busy
                              ? null
                              : () => setState(
                                  () => _obscureConfirmation =
                                      !_obscureConfirmation,
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
                  const SizedBox(height: 23),
                  FilledButton.icon(
                    onPressed: busy ? null : _submit,
                    icon: const Icon(Icons.login_rounded),
                    label: Text(
                      busy
                          ? 'Comprobando…'
                          : _register
                          ? 'Crear mi cuenta'
                          : 'Iniciar sesión',
                    ),
                  ),
                  if (_customer) ...[
                    const SizedBox(height: 13),
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
                        _register
                            ? 'Ya tengo una cuenta'
                            : 'Crear cuenta de cliente',
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 14),
        if (!_customer)
          const Center(
            child: Text(
              'El acceso depende de tus permisos y empresas autorizadas.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Color(0xFF64786A)),
            ),
          ),
      ],
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
