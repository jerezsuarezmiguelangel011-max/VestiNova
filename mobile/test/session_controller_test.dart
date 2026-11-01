import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/auth_models.dart';
import 'package:vestinova_mobile/auth/session_controller.dart';
import 'package:vestinova_mobile/auth/session_store.dart';
import 'package:vestinova_mobile/config/api_config.dart';

import 'support.dart';

const base = 'https://api.example.test/api';
const savedCustomer = SavedSession(
  apiBase: base,
  token: 'customer-fixture',
  customer: true,
  storeSlug: 'tienda-a',
);

SessionController controller(MemorySessionStore store, MockClient client) =>
    SessionController(
      api: AuthApi(ApiConfig(base), client: client),
      store: store,
    );

void main() {
  test('revocación inmediata después del login retira la cuenta y token recién emitidos', () async {
    final memory = MemorySessionStore();
    final session = controller(
      memory,
      MockClient((request) async {
        if (request.url.path.endsWith('/login')) {
          return jsonResponse(staffAccess());
        }
        return jsonResponse({'detail': 'La sesión fue revocada.'}, 401);
      }),
    );
    addTearDown(session.dispose);
    await session.loginStaff('personal@example.test', 'fixture');
    expect(session.account, isNull);
    expect(memory.value, isNull);
    expect(session.error, 'La sesión fue revocada.');
  });

  test('restaurar cliente comprueba me antes de mostrar cuenta y no consulta empresas', () async {
    final pending = Completer<http.Response>();
    final memory = MemorySessionStore(savedCustomer);
    final session = controller(
      memory,
      MockClient((request) {
        expect(request.url.path, '/api/tiendas/tienda-a/cuenta/me');
        return pending.future;
      }),
    );
    addTearDown(session.dispose);
    final restoring = session.restore();
    await Future<void>.delayed(Duration.zero);
    expect(session.account, isNull);
    expect(session.restoring, isTrue);
    pending.complete(jsonResponse(customerData()));
    await restoring;
    expect(session.account, isA<CustomerAccount>());
    expect(session.companies, isEmpty);
    expect(session.context, isNull);
  });

  test('sesión revocada limpia almacenamiento e identidad', () async {
    final memory = MemorySessionStore(savedCustomer);
    final session = controller(
      memory,
      MockClient(
        (_) async => jsonResponse({'detail': 'Sesión no válida.'}, 401),
      ),
    );
    addTearDown(session.dispose);
    await session.restore();
    expect(session.account, isNull);
    expect(session.restoring, isFalse);
    expect(memory.value, isNull);
    expect(session.notice, contains('Vuelve a iniciar sesión'));
  });

  test('fallo de red al restaurar conserva token pero oculta cuenta y permite reintentar', () async {
    var networkFailure = true;
    final memory = MemorySessionStore(savedCustomer);
    final session = controller(
      memory,
      MockClient((_) async {
        if (networkFailure) throw http.ClientException('isolated fixture');
        return jsonResponse(customerData());
      }),
    );
    addTearDown(session.dispose);
    await session.restore();
    expect(session.account, isNull);
    expect(session.restoring, isTrue);
    expect(memory.value, isNotNull);
    expect(session.error, contains('No se pudo conectar'));
    networkFailure = false;
    await session.restore();
    expect(session.isCustomer, isTrue);
    expect(session.restoring, isFalse);
  });

  test(
    'un cambio de URL de API no envía un token guardado a otro servidor',
    () async {
      final memory = MemorySessionStore(
        const SavedSession(
          apiBase: 'https://otra.example.test/api',
          token: 'fixture',
          customer: true,
          storeSlug: 'tienda-a',
        ),
      );
      final session = controller(
        memory,
        MockClient((_) async => fail('No debe llamar a la API')),
      );
      addTearDown(session.dispose);
      await session.restore();
      expect(memory.value, isNull);
      expect(session.account, isNull);
    },
  );

  test('personal elige entre empresas solo después del login y obtiene contexto autorizado', () async {
    final memory = MemorySessionStore();
    final session = controller(
      memory,
      MockClient((request) async {
        if (request.url.path.endsWith('/login')) {
          return jsonResponse(staffAccess());
        }
        if (request.url.path.endsWith('/empresas')) {
          return jsonResponse([companyData(1), companyData(2)]);
        }
        expect(request.headers['X-Empresa-Id'], '2');
        return jsonResponse(contextData(2));
      }),
    );
    addTearDown(session.dispose);
    await session.loginStaff('personal@example.test', 'fixture');
    expect(session.account, isA<StaffAccount>());
    expect(session.context, isNull);
    expect(memory.value!.companyId, isNull);
    await session.selectCompany(2);
    expect(session.context!.company.id, 2);
    expect(session.context!.company.role, 'CAJERO');
    expect(session.context!.branches.single.id, 20);
    expect(memory.value!.companyId, 2);
  });

  test(
    'una sola empresa se selecciona automáticamente y mantiene rol encargado',
    () async {
      final memory = MemorySessionStore();
      final session = controller(
        memory,
        MockClient((request) async {
          if (request.url.path.endsWith('/login')) {
            return jsonResponse(staffAccess());
          }
          if (request.url.path.endsWith('/empresas')) {
            return jsonResponse([companyData(1, 'ENCARGADO_SUCURSAL')]);
          }
          return jsonResponse(contextData(1, 'ENCARGADO_SUCURSAL'));
        }),
      );
      addTearDown(session.dispose);
      await session.loginStaff('personal@example.test', 'fixture');
      expect(session.context!.company.roleLabel, 'Encargado de sucursal');
      expect(memory.value!.companyId, 1);
    },
  );

  test('superadministrador sin pertenencia no obtiene empresas o sucursales ficticias', () async {
    final memory = MemorySessionStore();
    final session = controller(
      memory,
      MockClient(
        (request) async => request.url.path.endsWith('/login')
            ? jsonResponse(staffAccess(superadministrator: true))
            : jsonResponse([]),
      ),
    );
    addTearDown(session.dispose);
    await session.loginStaff('personal@example.test', 'fixture');
    expect(session.isSuperadministrator, isTrue);
    expect(session.companies, isEmpty);
    expect(session.context, isNull);
  });

  test('preferencia empresarial revocada se descarta al restaurar', () async {
    final memory = MemorySessionStore(
      const SavedSession(
        apiBase: base,
        token: 'staff-fixture',
        customer: false,
        companyId: 99,
      ),
    );
    final session = controller(
      memory,
      MockClient((request) async {
        if (request.url.path.endsWith('/me')) return jsonResponse(staffData());
        return jsonResponse([companyData(1), companyData(2)]);
      }),
    );
    addTearDown(session.dispose);
    await session.restore();
    expect(session.context, isNull);
    expect(memory.value!.companyId, isNull);
  });

  test('no selecciona una empresa ajena por manipulación local', () async {
    final memory = MemorySessionStore();
    var requests = 0;
    final session = controller(
      memory,
      MockClient((request) async {
        requests++;
        return request.url.path.endsWith('/login')
            ? jsonResponse(staffAccess())
            : jsonResponse([]);
      }),
    );
    addTearDown(session.dispose);
    await session.loginStaff('personal@example.test', 'fixture');
    await session.selectCompany(99);
    expect(requests, 2);
    expect(session.context, isNull);
    expect(session.error, contains('accesos autorizados'));
  });

  test(
    'un logout fallido conserva sesión para reintentar y no anuncia cierre',
    () async {
      var failLogout = true;
      final memory = MemorySessionStore(savedCustomer);
      final session = controller(
        memory,
        MockClient((request) async {
          if (request.url.path.endsWith('/me')) {
            return jsonResponse(customerData());
          }
          return failLogout
              ? jsonResponse({'detail': 'Inténtalo de nuevo.'}, 503)
              : http.Response('', 204);
        }),
      );
      addTearDown(session.dispose);
      await session.restore();
      await session.logout();
      expect(session.signedIn, isTrue);
      expect(memory.value, isNotNull);
      expect(session.notice, isNull);
      expect(session.error, 'Inténtalo de nuevo.');
      failLogout = false;
      await session.logout();
      expect(session.signedIn, isFalse);
      expect(memory.value, isNull);
      expect(session.notice, 'Sesión cerrada.');
    },
  );

  test(
    'un login antiguo no reemplaza una nueva cuenta de cliente ni su token',
    () async {
      final pendingStaff = Completer<http.Response>();
      final memory = MemorySessionStore();
      final session = controller(
        memory,
        MockClient((request) async {
          if (request.url.path == '/api/tiendas/tienda-a') {
            return jsonResponse({'slug': 'tienda-a', 'nombre': 'Tienda A'});
          }
          if (request.url.path == '/api/auth/login') return pendingStaff.future;
          if (request.url.path.endsWith('/cuenta/login')) {
            return jsonResponse(customerAccess());
          }
          return fail('No debe cargar datos de la sesión anterior');
        }),
      );
      addTearDown(session.dispose);
      await session.resolveStore('tienda-a');
      final older = session.loginStaff('personal@example.test', 'fixture');
      await session.customerAccess('cliente@example.test', 'fixture');
      pendingStaff.complete(jsonResponse(staffAccess()));
      await older;
      expect(session.account, isA<CustomerAccount>());
      expect(memory.value!.customer, isTrue);
      expect(memory.value!.token, 'customer-tienda-a-fixture');
    },
  );

  test(
    'respuesta tardía de empresa A no sustituye contexto ni preferencia de B',
    () async {
      final pendingA = Completer<http.Response>();
      final memory = MemorySessionStore();
      final session = controller(
        memory,
        MockClient((request) async {
          if (request.url.path.endsWith('/login')) {
            return jsonResponse(staffAccess());
          }
          if (request.url.path.endsWith('/empresas')) {
            return jsonResponse([companyData(1), companyData(2)]);
          }
          return request.headers['X-Empresa-Id'] == '1'
              ? pendingA.future
              : jsonResponse(contextData(2));
        }),
      );
      addTearDown(session.dispose);
      await session.loginStaff('personal@example.test', 'fixture');
      final older = session.selectCompany(1);
      await session.selectCompany(2);
      pendingA.complete(jsonResponse(contextData(1)));
      await older;
      expect(session.context!.company.id, 2);
      expect(memory.value!.companyId, 2);
    },
  );

  test('revocación al consultar contexto limpia identidad y sesión', () async {
    final memory = MemorySessionStore();
    final session = controller(
      memory,
      MockClient((request) async {
        if (request.url.path.endsWith('/login')) {
          return jsonResponse(staffAccess());
        }
        if (request.url.path.endsWith('/empresas')) {
          return jsonResponse([companyData(1), companyData(2)]);
        }
        return jsonResponse({'detail': 'Sesión revocada.'}, 401);
      }),
    );
    addTearDown(session.dispose);
    await session.loginStaff('personal@example.test', 'fixture');
    await session.selectCompany(1);
    expect(session.account, isNull);
    expect(memory.value, isNull);
  });
}
