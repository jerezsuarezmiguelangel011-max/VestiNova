import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vestinova_mobile/auth/auth_api.dart';
import 'package:vestinova_mobile/auth/auth_models.dart';
import 'package:vestinova_mobile/config/api_config.dart';
import 'package:vestinova_mobile/tryon/catalog_api.dart';
import 'package:vestinova_mobile/tryon/catalog_page.dart';
import 'package:vestinova_mobile/tryon/fitting_page.dart';

import 'support.dart';

final config = ApiConfig('https://example.test/api');
const store = Store(slug: 'tienda-a', name: 'Tienda A');
final product = {
  'id': 2,
  'slug': 'polera-varon',
  'nombre': 'Polera de varón',
  'precio': '119.00',
  'moneda': 'BOB',
  'descripcion': 'Descripción de prueba',
  'imagen_url': null,
};
Map<String, dynamic> variant(int id, String color) => {
  'variante_id': id,
  'talla': 'M',
  'color': color,
  'compatible': true,
  'configuracion': {
    'recurso_url': '/api/vestidor/recursos/polera-gris.png',
    'tipo_prenda': 'POLERA',
    'factor_ancho': 2.1,
    'factor_alto': 1.35,
    'anclajes': {'manga':'LARGA','hombro_izq':{'x':.32,'y':.2}},
    'offset_x': 0.0,
    'offset_y': 0.0,
    'demostracion': true,
  },
};
final fitting = {
  'tienda': 'tienda-a',
  'producto_id': 2,
  'compatible': true,
  'variantes': [variant(7, 'Gris'), variant(8, 'Azul')],
  'alternativas': [],
};

class PreparedCatalogApi extends CatalogApi {
  PreparedCatalogApi(this.bytes) : super(config);
  final Uint8List bytes;
  @override
  Future<Uint8List> png(FittingVariant variant) async => bytes;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const liveBase = String.fromEnvironment('TRYON_HTTP_API');
  test(
    'CU18 HTTP real: catálogo, cinco variantes demo y PNG desde PostgreSQL/API',
    () async {
      final uri = Uri.parse(liveBase);
      expect(uri.host, '127.0.0.1');
      expect(uri.port, 8001);
      final previous = HttpOverrides.current;
      HttpOverrides.global = null;
      addTearDown(() => HttpOverrides.global = previous);
      final api = CatalogApi(ApiConfig(liveBase));
      addTearDown(api.dispose);
      const shop = Store(slug: 'demo-moda-urbana', name: 'Moda Urbana Demo');
      final list = await api.list(shop, 'Vestidor demo', 0);
      expect(list['total'], 2);
      var count = 0;
      for (final row in list['items'] as List) {
        final product = await api.detail(shop, row['slug'] as String);
        expect(product.price, endsWith(' BOB'));
        final resource = await api.fitting(shop, product.slug);
        expect(resource['compatible'], true);
        for (final variant in resource['variantes'] as List) {
          final v = FittingVariant(Map<String, dynamic>.from(variant as Map));
          expect(await api.png(v), isNotEmpty);
          count++;
        }
      }
      expect(count, 5);
    },
    skip: liveBase.isEmpty
        ? 'Ejecutar explícitamente con --dart-define=TRYON_HTTP_API=http://127.0.0.1:8001/api'
        : false,
  );
  test('catálogo público conserva tienda, paginación, slug y precio decimal sin enviar credenciales', () async {
    final api = CatalogApi(
      config,
      client: MockClient((r) async {
        expect(r.headers.containsKey('Authorization'), isFalse);
        expect(r.followRedirects, isFalse);
        expect(r.url.queryParameters['tienda'], 'tienda-a');
        if (r.url.path.endsWith('vestidor')) return jsonResponse(fitting);
        if (r.url.path.endsWith('polera-varon')) return jsonResponse(product);
        expect(r.url.queryParameters['offset'], '20');
        expect(r.url.queryParameters['q'], 'polera');
        return jsonResponse({
          'items': [product],
          'total': 21,
          'limit': 20,
          'offset': 20,
        });
      }),
    );
    addTearDown(api.dispose);
    expect((await api.list(store, 'polera', 20))['total'], 21);
    expect((await api.detail(store, 'polera-varon')).price, '119.00 BOB');
    expect((await api.fitting(store, 'polera-varon'))['compatible'], true);
    expect(() => Garment({...product, 'precio': 119}), throwsFormatException);
  });
  test('rechaza respuestas de otra tienda y los fallos no se convierten en productos ficticios', () async {
    final api = CatalogApi(
      config,
      client: MockClient(
        (r) async => jsonResponse({...fitting, 'tienda': 'otra'}),
      ),
    );
    addTearDown(api.dispose);
    await expectLater(
      api.fitting(store, 'polera-varon'),
      throwsA(isA<AccessException>()),
    );
  });
  test('valida PNG transparente real, rechaza fotos comunes y no filtra tokens a los activos', () async {
    final bytes = File('../backend/app/vestidor_virtual/assets/polera-gris.png')
        .readAsBytesSync();
    var invalid = false;
    final api = CatalogApi(
      config,
      client: MockClient((r) async {
        expect(r.headers.containsKey('Authorization'), false);
        expect(r.followRedirects, false);
        expect(
          r.url.toString(),
          'https://example.test/api/vestidor/recursos/polera-gris.png',
        );
        return http.Response.bytes(
          invalid ? utf8.encode('foto-no-png') : bytes,
          200,
        );
      }),
    );
    addTearDown(api.dispose);
    expect(await api.png(FittingVariant(variant(7, 'Gris'))), isNotEmpty);
    invalid = true;
    await expectLater(
      api.png(FittingVariant(variant(7, 'Gris'))),
      throwsA(isA<AccessException>()),
    );
  });
  testWidgets(
    'CU18 desde CU08 conserva la talla y color elegidos al abrir el vestidor',
    (tester) async {
      final api = CatalogApi(
        config,
        client: MockClient((request) async {
          if (request.url.path.endsWith('/vestidor')) return jsonResponse(fitting);
          if (request.url.path.endsWith('/polera-varon')) return jsonResponse(product);
          throw StateError('Ruta inesperada del vestidor');
        }),
      );
      addTearDown(api.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: GarmentPage(
            store: store,
            slug: 'polera-varon',
            api: api,
            initialVariantId: 8,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<DropdownButtonFormField<int>>(
          find.byType(DropdownButtonFormField<int>),
        ).initialValue,
        8,
      );
      expect(find.text('Probar en vestidor virtual'), findsOneWidget);
    },
  );
  testWidgets(
    'lista, detalle, variantes y alternativa para una prenda sin vestidor',
    (tester) async {
      final api = CatalogApi(
        config,
        client: MockClient((r) async {
          if (r.url.path.endsWith('vestidor')) {
            return jsonResponse({
              ...fitting,
              'compatible': false,
              'variantes': [],
              'motivo': 'Prenda sin recurso de vestidor',
              'alternativas': [
                {'slug': 'camisa', 'nombre': 'Camisa con vestidor'},
              ],
            });
          }
          if (r.url.path.endsWith('polera-varon')) return jsonResponse(product);
          return jsonResponse({
            'items': [product],
            'total': 1,
            'limit': 20,
            'offset': 0,
          });
        }),
      );
      addTearDown(api.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: CatalogPage(store: store, config: config, api: api),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Ropa para varón'), findsOneWidget);
      await tester.tap(find.text('Ver prenda'));
      await tester.pumpAndSettle();
      expect(find.text('Prenda sin recurso de vestidor'), findsOneWidget);
      expect(find.text('Camisa con vestidor'), findsOneWidget);
      expect(find.text('Probar en vestidor virtual'), findsNothing);
    },
  );
  testWidgets(
    'permiso denegado explica la causa y conserva salida sin crear cámara',
    (tester) async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(
        const MethodChannel('vestinova/tryon_permission'),
        (call) async => 'denied',
      );
      addTearDown(
        () => messenger.setMockMethodCallHandler(
          const MethodChannel('vestinova/tryon_permission'),
          null,
        ),
      );
      final api = CatalogApi(
        config,
        client: MockClient(
          (_) async => throw StateError('No debe descargar sin permiso'),
        ),
      );
      addTearDown(api.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: FittingPage(
            api: api,
            product: Garment(product),
            variants: [FittingVariant(variant(7, 'Gris'))],
            initial: FittingVariant(variant(7, 'Gris')),
            cameraBuilder: (_) => throw StateError('No debe crear cámara'),
          ),
        ),
      );
      await tester.tap(find.text('Permitir cámara'));
      await tester.pumpAndSettle();
      expect(find.text('Permitir cámara'), findsOneWidget);
      expect(find.textContaining('no fue autorizado'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );
  testWidgets(
    'cámara controlada configura el PNG, reacciona a seguimiento y pausa al salir',
    (tester) async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      const permissions = MethodChannel('vestinova/tryon_permission');
      const camera = MethodChannel('vestinova/tryon/77');
      final calls = <MethodCall>[];
      messenger.setMockMethodCallHandler(
        permissions,
        (call) async => 'granted',
      );
      messenger.setMockMethodCallHandler(camera, (call) async {
        calls.add(call);
        if (call.method == 'focus') return 'fixed_focus';
        return null;
      });
      addTearDown(() {
        messenger.setMockMethodCallHandler(permissions, null);
        messenger.setMockMethodCallHandler(camera, null);
      });
      final bytes = File(
        '../backend/app/vestidor_virtual/assets/polera-gris.png',
      ).readAsBytesSync();
      final api = PreparedCatalogApi(bytes);
      addTearDown(api.dispose);
      var created = false;
      final variants = [
        FittingVariant(variant(7, 'Gris')),
        FittingVariant(variant(8, 'Azul')),
      ];
      await tester.pumpWidget(
        MaterialApp(
          home: FittingPage(
            api: api,
            product: Garment(product),
            variants: variants,
            initial: variants.first,
            cameraBuilder: (callback) {
              if (!created) {
                created = true;
                WidgetsBinding.instance.addPostFrameCallback(
                  (_) => callback(77),
                );
              }
              return const ColoredBox(color: Colors.black);
            },
          ),
        ),
      );
      await tester.tap(find.text('Permitir cámara'));
      await tester.pump();
      await tester.pump();
      await tester.pump();
      expect(calls.any((call) => call.method == 'configure'), isTrue);
      final configured =
          calls.firstWhere((c) => c.method == 'configure').arguments as Map;
      expect(configured['png'], isNotEmpty);
      expect(configured['factor_ancho'], 2.1);
      expect((configured['anclajes'] as Map)['manga'], 'LARGA');
      await messenger.handlePlatformMessage(
        camera.name,
        const StandardMethodCodec().encodeMethodCall(
          const MethodCall('state', {'estado': 'tracking'}),
        ),
        (_) {},
      );
      await tester.pump();
      expect(
        find.text('Torso y mangas siguiendo tus puntos corporales · Vista 2D'),
        findsOneWidget,
      );
      await tester.tap(find.text('Enfocar centro'));
      await tester.pump();
      await tester.pump();
      expect(calls.any((call) => call.method == 'focus'), isTrue);
      expect(find.textContaining('Esta cámara no permite ajustar el enfoque'), findsOneWidget);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pumpAndSettle();
      expect(calls.last.method, 'pause');
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );
}
