import 'package:flutter/material.dart';

import 'storefront_api.dart';
import 'storefront_models.dart';
import 'storefront_widgets.dart';

class StorefrontComparisonPage extends StatefulWidget {
  const StorefrontComparisonPage({super.key, required this.tienda,
    required this.api, required this.selected, required this.onRemove,
    required this.onOpen});
  final String tienda;
  final StorefrontApi api;
  final List<StoreProduct> selected;
  final ValueChanged<int> onRemove;
  final ValueChanged<StoreProduct> onOpen;
  @override
  State<StorefrontComparisonPage> createState() => _StorefrontComparisonPageState();
}

class _StorefrontComparisonPageState extends State<StorefrontComparisonPage> {
  List<StoreProduct>? _compared;
  bool _busy = false;
  String? _error;
  @override
  void didUpdateWidget(covariant StorefrontComparisonPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selected.map((e) => e.id).join(',') != widget.selected.map((e) => e.id).join(',')) {
      _compared = null; _error = null;
    }
  }

  Future<void> _compare() async {
    if (widget.selected.length < 2 || widget.selected.length > 4) return;
    setState(() { _busy = true; _error = null; });
    try {
      final result = await widget.api.compare(widget.tienda,
        widget.selected.map((e) => e.id).toList());
      if (mounted) setState(() => _compared = result);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally { if (mounted) setState(() => _busy = false); }
  }

  Widget _comparisonColumn(StoreProduct p) => SizedBox(width: 205,
    child: Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Center(child: ProductPhoto(p.imageUrl, height: 140)),
        const SizedBox(height: 10),
        Text(p.name, style: const TextStyle(fontWeight: FontWeight.bold)),
        const Divider(),
        Text('Precio: Bs ${p.effectivePrice}'),
        if (p.salePrice != null) Text('Precio anterior: Bs ${p.price}'),
        Text('Categoría: ${p.category}'),
        Text('Material: ${p.material.isEmpty ? 'No indicado' : p.material}'),
        Text('Temporada: ${p.season.isEmpty ? 'No indicada' : p.season}'),
        Text('Medidas: ${p.measurements.isEmpty ? 'No indicadas' : p.measurements}'),
        const SizedBox(height: 12),
        const Text('Variantes y sucursales:', style: TextStyle(fontWeight: FontWeight.w600)),
        if (p.comparisonVariants.isEmpty) const Text('Sin variantes publicadas'),
        ...p.comparisonVariants.map((v) => Padding(
          padding: const EdgeInsets.only(top: 7),
          child: Text('${v.size} / ${v.color}\n${v.branches.join(' · ')}'),
        )),
        const SizedBox(height: 8),
        TextButton(onPressed: () => widget.onOpen(p), child: const Text('Ver prenda')),
      ]),
    )),
  );

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
    Text('Comparar prendas', style: Theme.of(context).textTheme.headlineSmall),
    const SizedBox(height: 6),
    Text('${widget.selected.length} de 4 prendas seleccionadas. Se requieren al menos 2.'),
    const SizedBox(height: 12),
    ...widget.selected.map((p) => ListTile(
      title: Text(p.name), subtitle: Text('Bs ${p.effectivePrice}'),
      trailing: IconButton(onPressed: () => widget.onRemove(p.id),
        icon: const Icon(Icons.close), tooltip: 'Quitar prenda'),
    )),
    const SizedBox(height: 12),
    FilledButton.icon(
      onPressed: _busy || widget.selected.length < 2 ? null : _compare,
      icon: const Icon(Icons.compare_arrows), label: const Text('Comparar ahora'),
    ),
    if (_busy) const LinearProgressIndicator(),
    if (_error != null) StorefrontMessage(message: _error!, retry: _compare),
    if (_compared case final compared?) ...[
      const SizedBox(height: 12),
      const Text('Información central actual. La consulta no reserva stock.'),
      const SizedBox(height: 12),
      SingleChildScrollView(scrollDirection: Axis.horizontal,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start,
          children: compared.map(_comparisonColumn).toList())),
      const SizedBox(height: 12),
      const Text('Para consultar tallas, colores y disponibilidad por sucursal, abre el detalle de cada prenda.'),
    ],
  ]);
}
