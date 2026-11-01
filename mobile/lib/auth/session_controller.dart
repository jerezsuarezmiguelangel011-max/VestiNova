import 'package:flutter/foundation.dart';

import '../config/api_config.dart';
import 'auth_api.dart';
import 'auth_models.dart';
import 'session_store.dart';

class SessionController extends ChangeNotifier {
  SessionController({required this.api, required this.store});
  final AuthApi api;
  final SessionStore store;
  Account? account;
  Store? customerStore;
  List<Company> companies = const [];
  StaffContext? context;
  bool busy = false;
  bool restoring = true;
  String? error;
  String? notice;
  SavedSession? _session;
  int _revision = 0;
  bool _disposed = false;
  Future<void> _storageQueue = Future.value();

  bool get signedIn => account != null;
  bool get isCustomer => account is CustomerAccount;
  bool get isSuperadministrator =>
      account is StaffAccount && (account as StaffAccount).superadministrator;

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  bool _current(int revision) => !_disposed && revision == _revision;

  Future<void> _persist(int revision, SavedSession? value) async {
    // Serialization also protects a newer login against a delayed old write.
    final action = _storageQueue.catchError((Object _) {}).then((_) async {
      if (!_current(revision)) return;
      if (value == null) {
        await store.clear();
      } else {
        await store.write(value);
      }
    });
    _storageQueue = action;
    await action;
  }

  Future<void> restore() async {
    final revision = ++_revision;
    busy = true;
    restoring = true;
    account = null;
    context = null;
    companies = const [];
    error = null;
    _emit();
    try {
      final saved = await store.read();
      if (!_current(revision)) return;
      if (saved == null || saved.apiBase != api.config.base) {
        await _persist(revision, null);
        _session = null;
        restoring = false;
        return;
      }
      _session = saved;
      final restored = saved.customer
          ? await api.customerMe(saved.storeSlug!, saved.token)
          : await api.staffMe(saved.token);
      if (!_current(revision)) return;
      account = restored;
      restoring = false;
      if (restored is CustomerAccount) {
        customerStore = restored.store;
      } else {
        await _loadAccess(revision, saved.companyId);
      }
    } on AccessException catch (failure) {
      if (!_current(revision)) return;
      if (failure.invalidSession || failure.status == 404) {
        await _clear(revision);
        notice = 'La sesión ya no está disponible. Vuelve a iniciar sesión.';
      } else {
        error = failure.message;
      }
    } on Object {
      if (_current(revision)) {
        error = 'No se pudo leer la sesión segura. Vuelve a intentarlo.';
      }
    } finally {
      if (_current(revision)) {
        busy = false;
        _emit();
      }
    }
  }

  Future<void> resolveStore(String value) async {
    final slug = ApiConfig.storeSlug(value);
    if (slug == null) {
      error = 'Introduce el enlace o identificador público de una tienda.';
      _emit();
      return;
    }
    await _run((revision) async {
      final result = await api.store(slug);
      if (_current(revision)) customerStore = result;
    });
  }

  void leaveStore() {
    if (busy || signedIn) return;
    _revision++;
    customerStore = null;
    error = null;
    notice = null;
    _emit();
  }

  Future<void> loginStaff(String email, String password) async {
    await _run((revision) async {
      final result = await api.staffLogin(email, password);
      if (!_current(revision)) return;
      final saved = SavedSession(
        apiBase: api.config.base,
        token: result.token,
        customer: false,
      );
      await _persist(revision, saved);
      if (!_current(revision)) return;
      _session = saved;
      account = result.account;
      customerStore = null;
      restoring = false;
      try {
        await _loadAccess(revision, null);
      } on AccessException catch (failure) {
        if (failure.invalidSession && _current(revision)) {
          await _clear(revision);
        }
        rethrow;
      }
    });
  }

  Future<void> customerAccess(
    String email,
    String password, {
    String? name,
  }) async {
    final store = customerStore;
    if (store == null) return;
    await _run((revision) async {
      final result = await api.customerAccess(
        store.slug,
        email,
        password,
        name: name,
      );
      if (!_current(revision)) return;
      final saved = SavedSession(
        apiBase: api.config.base,
        token: result.token,
        customer: true,
        storeSlug: store.slug,
      );
      await _persist(revision, saved);
      if (!_current(revision)) return;
      _session = saved;
      account = result.account;
      customerStore = result.account.store;
      context = null;
      companies = const [];
      restoring = false;
      if (name != null) notice = 'Tu cuenta se creó en ${store.name}.';
    });
  }

  Future<void> _loadAccess(int revision, int? preferred) async {
    final saved = _session;
    if (saved == null || saved.customer) return;
    final authorized = await api.companies(saved.token);
    if (!_current(revision)) return;
    companies = authorized;
    final validPreference = authorized.any((item) => item.id == preferred)
        ? preferred
        : null;
    final selection =
        validPreference ??
        (authorized.length == 1 ? authorized.single.id : null);
    context = null;
    _session = saved.withCompany(null);
    if (selection == null) {
      await _persist(revision, _session);
      return;
    }
    await _select(revision, selection);
  }

  Future<void> _select(int revision, int companyId) async {
    final saved = _session;
    if (saved == null || saved.customer) return;
    context = null;
    _emit();
    final access = await api.context(saved.token, companyId);
    if (!_current(revision)) return;
    final selected = saved.withCompany(companyId);
    await _persist(revision, selected);
    if (!_current(revision)) return;
    _session = selected;
    context = access;
  }

  Future<void> selectCompany(int companyId) async {
    if (!companies.any((item) => item.id == companyId) || isCustomer) {
      error = 'La empresa no está entre tus accesos autorizados.';
      _emit();
      return;
    }
    await _run((revision) => _select(revision, companyId), authenticated: true);
  }

  Future<void> refresh() async {
    final saved = _session;
    if (saved == null) return;
    await _run((revision) async {
      if (saved.customer) {
        final current = await api.customerMe(saved.storeSlug!, saved.token);
        if (_current(revision)) {
          account = current;
          customerStore = current.store;
        }
      } else {
        final current = await api.staffMe(saved.token);
        if (!_current(revision)) return;
        account = current;
        context = null;
        companies = const [];
        await _loadAccess(revision, saved.companyId);
      }
    }, authenticated: true);
  }

  Future<void> logout() async {
    final saved = _session;
    if (saved == null) return;
    await _run((revision) async {
      await api.logout(
        saved.token,
        slug: saved.customer ? saved.storeSlug : null,
      );
      if (!_current(revision)) return;
      await _clear(revision);
      notice = 'Sesión cerrada.';
    }, authenticated: true);
  }

  Future<void> _clear(int revision) async {
    await _persist(revision, null);
    if (!_current(revision)) return;
    _session = null;
    account = null;
    context = null;
    companies = const [];
    customerStore = null;
    restoring = false;
  }

  Future<void> _run(
    Future<void> Function(int) action, {
    bool authenticated = false,
  }) async {
    final revision = ++_revision;
    busy = true;
    error = null;
    notice = null;
    _emit();
    try {
      await action(revision);
    } on AccessException catch (failure) {
      if (!_current(revision)) return;
      if (failure.invalidSession && authenticated) {
        await _clear(revision);
        notice = 'La sesión ya no está vigente. Vuelve a iniciar sesión.';
      } else {
        error = failure.message;
      }
    } on Object {
      if (_current(revision)) error = 'No se pudo completar el acceso. Comprueba la conexión y el almacenamiento seguro.';
    } finally {
      if (_current(revision)) {
        busy = false;
        _emit();
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _revision++;
    api.close();
    super.dispose();
  }
}
