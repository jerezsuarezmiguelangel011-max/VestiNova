// Opt-in only. The backend PostgreSQL runner supplies a temporary local API and
// isolated fixture stores. Never point this mutation test at the operational DB.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/auth_models.dart';
import 'package:vestinova_mobile/auth/session_controller.dart';
import 'package:vestinova_mobile/auth/session_store.dart';
import 'package:vestinova_mobile/config/api_config.dart';

import 'support.dart';

const _enabled = bool.fromEnvironment('REAL_API_TEST');
const _storeA = String.fromEnvironment('REAL_STORE_A');
const _storeB = String.fromEnvironment('REAL_STORE_B');
const _staffEmail = String.fromEnvironment('REAL_STAFF_EMAIL');
const _staffPassword = String.fromEnvironment('REAL_STAFF_PASSWORD');

void main() {
  test(
    'cliente Dart: registro por tienda, aislamiento, restauración y revocación HTTP/PostgreSQL reales',
    () async {
      final config = ApiConfig(ApiConfig.defaultBase);
      expect(
        config.endpoint('').host,
        anyOf('127.0.0.1', 'localhost', '::1'),
        reason: 'Solo API local efímera del runner.',
      );
      expect(_storeA, isNotEmpty);
      expect(_storeB, isNot(equals(_storeA)));
      final api = AuthApi(config);
      addTearDown(api.close);
      final store = await api.store(_storeA);
      expect(store.slug, _storeA);
      final email =
          'mobile-${DateTime.now().microsecondsSinceEpoch}@example.test';
      const passwordA = 'Cliente aislado A!2026';
      const passwordB = 'Cliente aislado B!2026';
      final a = await api.customerAccess(
        _storeA,
        email,
        passwordA,
        name: 'Cliente móvil aislado A',
      );
      expect(a.account.store.slug, _storeA);
      final me = await api.customerMe(_storeA, a.token);
      expect(me.id, a.account.id);
      expect(me.email, email);
      await expectLater(
        api.customerAccess(
          _storeA,
          email.toUpperCase(),
          passwordA,
          name: 'Duplicado móvil aislado',
        ),
        throwsA(
          isA<AccessException>().having((error) => error.status, 'status', 409),
        ),
      );
      final b = await api.customerAccess(
        _storeB,
        email,
        passwordB,
        name: 'Cliente móvil aislado B',
      );
      expect(b.account.store.slug, _storeB);
      expect(b.account.id, isNot(a.account.id));
      await expectLater(
        api.customerMe(_storeB, a.token),
        throwsA(isA<AccessException>()),
      );
      await expectLater(
        api.customerAccess(_storeB, email, passwordA),
        throwsA(
          isA<AccessException>().having((error) => error.status, 'status', 401),
        ),
      );

      final forbidden = await http.get(
        config.endpoint('/admin/productos'),
        headers: {'Authorization': 'Bearer ${a.token}'},
      );
      expect(forbidden.statusCode, anyOf(401, 403));
      final invalidRegistration = await http.post(
        config.endpoint('/tiendas/$_storeA/cuenta/registro'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'nombre': 'Intento de personal',
          'correo': 'role-$email',
          'password': passwordA,
          'rol': 'ADMINISTRADOR',
        }),
      );
      expect(invalidRegistration.statusCode, 422);

      // Real HTTP restore with an in-memory storage double. This does not verify
      // Android KeyStore, which requires execution on a device/emulator.
      final memory = MemorySessionStore(
        SavedSession(
          apiBase: config.base,
          token: a.token,
          customer: true,
          storeSlug: _storeA,
        ),
      );
      final session = SessionController(api: AuthApi(config), store: memory);
      addTearDown(session.dispose);
      await session.restore();
      expect(session.account, isA<CustomerAccount>());
      expect(session.account!.id, a.account.id);
      expect(session.companies, isEmpty);
      await session.logout();
      expect(session.signedIn, isFalse);
      expect(memory.value, isNull);
      await expectLater(
        api.customerMe(_storeA, a.token),
        throwsA(
          isA<AccessException>().having((error) => error.status, 'status', 401),
        ),
      );

      final againA = await api.customerAccess(_storeA, email, passwordA);
      final againB = await api.customerAccess(_storeB, email, passwordB);
      expect(againA.account.id, a.account.id);
      expect(againB.account.id, b.account.id);
      await api.logout(againA.token, slug: _storeA);
      await api.logout(againB.token, slug: _storeB);
      await api.logout(b.token, slug: _storeB);
    },
    skip: !_enabled,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'personal Dart: login, empresas, contexto, restauración y logout HTTP/PostgreSQL reales',
    () async {
      final config = ApiConfig(ApiConfig.defaultBase);
      expect(config.endpoint('').host, anyOf('127.0.0.1', 'localhost', '::1'));
      expect(_staffEmail, isNotEmpty);
      final api = AuthApi(config);
      addTearDown(api.close);
      final result = await api.staffLogin(_staffEmail, _staffPassword);
      final me = await api.staffMe(result.token);
      expect(me.id, result.account.id);
      final companies = await api.companies(result.token);
      expect(companies, isNotEmpty);
      for (final company in companies) {
        final access = await api.context(result.token, company.id);
        expect(access.company.id, company.id);
        expect(access.company.slug, company.slug);
        expect(
          access.company.role,
          anyOf('ADMINISTRADOR', 'ENCARGADO_SUCURSAL', 'CAJERO', 'OPERADOR'),
        );
      }
      final memory = MemorySessionStore(
        SavedSession(
          apiBase: config.base,
          token: result.token,
          customer: false,
          companyId: companies.first.id,
        ),
      );
      final session = SessionController(api: AuthApi(config), store: memory);
      addTearDown(session.dispose);
      await session.restore();
      expect(session.account, isA<StaffAccount>());
      expect(session.context!.company.id, companies.first.id);
      await session.logout();
      expect(memory.value, isNull);
      await expectLater(
        api.staffMe(result.token),
        throwsA(
          isA<AccessException>().having((error) => error.status, 'status', 401),
        ),
      );
    },
    skip: !_enabled,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
