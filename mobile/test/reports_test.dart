import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/auth_models.dart';
import 'package:vestinova_mobile/auth/session_controller.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/reports/reports_api.dart';
import 'package:vestinova_mobile/reports/reports_page.dart';

import 'support.dart';

void main() {
  test(
    'reportes envían token y empresa; exportación reenvía solo tipo y filtros',
    () async {
      var calls = 0;
      final api = ReportsApi(
        ApiConfig('https://example.test/api'),
        client: MockClient((request) async {
          expect(request.headers['Authorization'], 'Bearer fixture');
          expect(request.headers['X-Empresa-Id'], '7');
          expect(request.followRedirects, isFalse);
          if (calls++ == 0) {
            expect(jsonDecode(request.body), {
              'consulta': 'Inventario actual',
              'filtros': {'sucursal_id': 3},
            });
            return jsonResponse({'estado': 'generado'});
          }
          expect(jsonDecode(request.body), {
            'tipo': 'inventario',
            'filtros': {},
            'formato': 'pdf',
          });
          return http.Response('%PDF-fixture', 200);
        }),
      );
      addTearDown(api.dispose);
      expect(
        (await api.generate('fixture', 7, 'Inventario actual', {
          'sucursal_id': 3,
        }))['estado'],
        'generado',
      );
      expect(
        utf8.decode(
          await api.export('fixture', 7, {
            'tipo': 'inventario',
            'filtros': {},
            'filas': ['no enviar'],
          }, 'pdf'),
        ),
        startsWith('%PDF'),
      );
    },
  );
  test('permisos explícitos prevalecen sobre la etiqueta del rol', () {
    expect(
      Company.fromJson({...companyData(1, 'ADMINISTRADOR'), 'permisos': []})
          .canUseAIReports,
      isFalse,
    );
    expect(
      Company.fromJson({
        ...companyData(1, 'OPERADOR'),
        'permisos': ['reportes.ia.consultar'],
      }).canUseAIReports,
      isTrue,
    );
    expect(Company.fromJson(companyData(1, 'CAJERO')).canUseAIReports, isFalse);
  });
  test('sin conexión informa el fallo sin devolver filas ficticias', () async {
    final api = ReportsApi(
      ApiConfig('https://example.test/api'),
      client: MockClient((_) async => throw http.ClientException('fixture')),
    );
    addTearDown(api.dispose);
    await expectLater(
      api.options('fixture', 1),
      throwsA(
        isA<AccessException>().having(
          (e) => e.message,
          'mensaje',
          contains('conexión'),
        ),
      ),
    );
  });
  testWidgets(
    'formulario genera con texto y descarta una respuesta tras cierre de sesión',
    (tester) async {
      final session = SessionController(
        api: AuthApi(
          ApiConfig('https://example.test/api'),
          client: MockClient((request) async {
            if (request.url.path.endsWith('/login')) {
              return jsonResponse(staffAccess());
            }
            if (request.url.path.endsWith('/empresas')) {
              return jsonResponse([companyData(1, 'ADMINISTRADOR')]);
            }
            if (request.url.path.endsWith('/logout')) {
              return http.Response('', 204);
            }
            return jsonResponse(contextData(1, 'ADMINISTRADOR'));
          }),
        ),
        store: MemorySessionStore(),
      );
      addTearDown(session.dispose);
      await session.loginStaff('fixture@example.test', 'fixture');
      final delayed = Completer<http.Response>();
      final api = ReportsApi(
        session.api.config,
        client: MockClient((request) async {
          if (request.url.path.endsWith('/opciones')) {
            return jsonResponse({
              'profesional_vigente': true,
              'ia_configurada': true,
              'sucursales': [],
              'categorias': [],
              'productos': [],
            });
          }
          return delayed.future;
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: ReportsPage(controller: session, api: api),
        ),
      );
      await tester.pumpAndSettle();
      const voiceChannel = MethodChannel('plugin.csdcorp.com/speech_to_text');
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        voiceChannel,
        (_) async => false,
      );
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          voiceChannel,
          null,
        ),
      );
      final dictation = find.text('Dictar y revisar texto');
      await tester.ensureVisible(dictation);
      await tester.tap(dictation);
      await tester.pumpAndSettle();
      expect(
        find.textContaining(RegExp('Puedes escribir la consulta|Usa texto')),
        findsOneWidget,
      );
      await tester.enterText(find.byType(TextField).first, 'Inventario actual');
      final generate = find.text('Generar reporte');
      await tester.ensureVisible(generate);
      await tester.tap(generate);
      await tester.pump();
      await session.logout();
      await tester.pump();
      delayed.complete(
        jsonResponse({
          'estado': 'generado',
          'reporte': {'titulo': 'Resultado privado tardío'},
        }),
      );
      await tester.pumpAndSettle();
      expect(find.text('Resultado privado tardío'), findsNothing);
      expect(find.textContaining('sesión o empresa cambió'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
