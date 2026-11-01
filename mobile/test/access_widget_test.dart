import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/password_policy.dart';
import 'package:vestinova_mobile/auth/session_controller.dart';
import 'package:vestinova_mobile/auth/session_store.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/main.dart';

import 'support.dart';

Future<SessionController> mount(
  WidgetTester tester,
  MockClient client, {
  SavedSession? saved,
}) async {
  final controller = SessionController(
    api: AuthApi(ApiConfig('https://api.example.test/api'), client: client),
    store: MemorySessionStore(saved),
  );
  addTearDown(controller.dispose);
  await tester.pumpWidget(VestiNovaApp(controller: controller));
  await tester.pumpAndSettle();
  return controller;
}

Future<void> tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'entrada y validación son utilizables a 360px sin desbordamiento',
    (tester) async {
      tester.view.physicalSize = const Size(360, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await mount(
        tester,
        MockClient((_) async => fail('No debe consultar datos sin tienda')),
      );
      expect(find.text('Tu tienda. Tu cuenta.'), findsOneWidget);
      await tapVisible(tester, find.text('Abrir mi tienda'));
      expect(
        find.text('Introduce un enlace o identificador de tienda válido.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      await tapVisible(tester, find.text('Acceso del personal'));
      await tapVisible(tester, find.text('Iniciar sesión'));
      expect(
        find.text('Introduce un correo electrónico válido.'),
        findsOneWidget,
      );
      expect(find.text('Introduce tu contraseña.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'registro cliente valida y muestra cuenta de su tienda sin selector administrativo',
    (tester) async {
      final requests = <http.Request>[];
      await mount(
        tester,
        MockClient((request) async {
          requests.add(request);
          if (request.url.path == '/api/tiendas/tienda-a') {
            return jsonResponse({'slug': 'tienda-a', 'nombre': 'Tienda A'});
          }
          expect(request.url.path, '/api/tiendas/tienda-a/cuenta/registro');
          expect(jsonDecode(request.body), {
            'nombre': 'Cliente real',
            'correo': 'cliente@example.test',
            'password': 'Abcdef1!',
          });
          return jsonResponse(customerAccess(), 201);
        }),
      );
      await tester.enterText(find.byType(TextFormField).first, 'tienda-a');
      await tapVisible(tester, find.text('Abrir mi tienda'));
      await tapVisible(tester, find.text('Crear cuenta de cliente'));
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Nombre completo'),
        'Cliente real',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Correo electrónico'),
        'cliente@example.test',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Contraseña'),
        'incorrecta',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Repite la contraseña'),
        'otra',
      );
      await tapVisible(tester, find.text('Crear mi cuenta'));
      expect(find.text(passwordPolicyMessage), findsNWidgets(2));
      expect(find.text('Las contraseñas no coinciden.'), findsOneWidget);
      expect(requests.length, 1);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Contraseña'),
        'Abcdef1!',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Repite la contraseña'),
        'Abcdef1!',
      );
      await tapVisible(tester, find.text('Crear mi cuenta'));
      expect(find.text('Tu cuenta'), findsOneWidget);
      expect(find.text('Cliente · Tienda A'), findsOneWidget);
      expect(find.byType(DropdownButtonFormField<int>), findsNothing);
      expect(find.text('Empresa de trabajo'), findsNothing);
      expect(find.text('Sucursales autorizadas'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'personal inicia sesión con contraseña antigua y elige empresa después',
    (tester) async {
      final controller = await mount(
        tester,
        MockClient((request) async {
          if (request.url.path.endsWith('/login')) {
            expect(jsonDecode(request.body)['password'], 'old');
            return jsonResponse(staffAccess(superadministrator: true));
          }
          if (request.url.path.endsWith('/empresas')) {
            return jsonResponse([
              companyData(1, 'ADMINISTRADOR'),
              companyData(2),
            ]);
          }
          expect(request.headers['X-Empresa-Id'], '2');
          return jsonResponse(contextData(2));
        }),
      );
      await tapVisible(tester, find.text('Acceso del personal'));
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Correo electrónico'),
        'personal@example.test',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Contraseña'),
        'old',
      );
      await tapVisible(tester, find.text('Iniciar sesión'));
      expect(find.text('Superadministrador SaaS'), findsOneWidget);
      expect(find.text('Empresa de trabajo'), findsOneWidget);
      expect(controller.context, isNull);
      await tapVisible(tester, find.byType(DropdownButtonFormField<int>));
      await tapVisible(tester, find.text('Empresa 2').last);
      expect(find.text('Cajero'), findsOneWidget);
      expect(find.text('Sucursal 2'), findsOneWidget);
      expect(controller.context!.company.id, 2);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'cierre fallido conserva cuenta y ofrece reintento; éxito retira pantalla privada',
    (tester) async {
      var failLogout = true;
      await mount(
        tester,
        MockClient((request) async {
          if (request.url.path.endsWith('/me')) {
            return jsonResponse(customerData());
          }
          return failLogout
              ? jsonResponse({'detail': 'Cierre no confirmado.'}, 503)
              : http.Response('', 204);
        }),
        saved: const SavedSession(
          apiBase: 'https://api.example.test/api',
          token: 'fixture',
          customer: true,
          storeSlug: 'tienda-a',
        ),
      );
      expect(find.text('Cliente · Tienda A'), findsOneWidget);
      await tapVisible(tester, find.text('Cerrar sesión'));
      expect(find.text('Cierre no confirmado.'), findsOneWidget);
      expect(find.text('Tu cuenta'), findsOneWidget);
      failLogout = false;
      await tapVisible(tester, find.text('Cerrar sesión'));
      expect(find.text('Tu cuenta'), findsNothing);
      expect(find.text('Sesión cerrada.'), findsOneWidget);
      expect(find.text('Tu tienda. Tu cuenta.'), findsOneWidget);
    },
  );
}
