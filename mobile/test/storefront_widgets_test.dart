import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vestinova_mobile/storefront/storefront_models.dart';
import 'package:vestinova_mobile/storefront/storefront_widgets.dart';

void main() {
  testWidgets('CU08 presenta prenda, precio y acciones comerciales', (tester) async {
    var opened = 0;
    var compared = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ProductRow(
      item: const StoreProduct(id: 5, slug: 'jean-recto', name: 'Jean recto', price: '189.00'),
      onOpen: () => opened++, onCompare: () => compared++,
    ))));
    expect(find.text('Jean recto'), findsOneWidget);
    expect(find.text('Bs 189.00'), findsOneWidget);
    await tester.tap(find.text('Comparar'));
    expect(compared, 1);
    await tester.tap(find.text('Ver detalle'));
    expect(opened, 1);
  });

  testWidgets('La copia offline nunca se anuncia como stock confirmado', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: CacheNotice(
      savedAt: '2026-11-08T11:00:00Z', partial: true,
    ))));
    expect(find.textContaining('posiblemente incompleto'), findsOneWidget);
    expect(find.textContaining('no son confirmación de stock'), findsOneWidget);
  });
}
