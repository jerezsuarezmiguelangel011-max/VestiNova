import 'package:flutter/material.dart';

import '../auth/auth_api.dart';
import '../auth/auth_models.dart';
import '../config/api_config.dart';
import 'catalog_api.dart';
import 'fitting_page.dart';

class CatalogPage extends StatefulWidget {
  const CatalogPage({
    super.key,
    required this.store,
    required this.config,
    this.api,
  });
  final Store store;
  final ApiConfig config;
  final CatalogApi? api;
  @override
  State<CatalogPage> createState() => _CatalogPageState();
}

class _CatalogPageState extends State<CatalogPage> {
  late final api = widget.api ?? CatalogApi(widget.config);
  final search = TextEditingController();
  List<Garment> products = [];
  int offset = 0, total = 0, revision = 0;
  bool loading = true;
  String? error;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load({int page = 0}) async {
    final current = ++revision;
    setState(() {
      loading = true;
      error = null;
      products = [];
    });
    try {
      final data = await api.list(widget.store, search.text.trim(), page);
      final rows = (data['items'] as List)
          .map((e) => Garment(Map<String, dynamic>.from(e as Map)))
          .toList();
      if (mounted && current == revision) {
        setState(() {
          products = rows;
          offset = page;
          total = data['total'] as int;
        });
      }
    } on Object catch (e) {
      if (mounted && current == revision) {
        setState(
          () => error = e is AccessException
              ? e.message
              : 'No se pudo leer el catálogo.',
        );
      }
    } finally {
      if (mounted && current == revision) setState(() => loading = false);
    }
  }

  @override
  void dispose() {
    revision++;
    search.dispose();
    if (widget.api == null) api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.store.name)),
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Ropa para varón',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'Encuentra tu próxima prenda. Abre el detalle para consultar tallas, colores y vestidor.',
          ),
          const SizedBox(height: 20),
          TextField(
            controller: search,
            maxLength: 120,
            decoration: InputDecoration(
              labelText: 'Buscar una prenda',
              suffixIcon: IconButton(
                tooltip: 'Buscar',
                onPressed: loading ? null : () => load(),
                icon: const Icon(Icons.search),
              ),
            ),
            onSubmitted: (_) => load(),
          ),
          if (loading)
            const LinearProgressIndicator(semanticsLabel: 'Cargando catálogo'),
          if (error != null) ...[
            Text(error!, semanticsLabel: error),
            OutlinedButton(
              onPressed: () => load(page: offset),
              child: const Text('Reintentar'),
            ),
          ],
          if (!loading && error == null && products.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text('No hay prendas para esta búsqueda.'),
            ),
          ...products.map(
            (product) => Card(
              margin: const EdgeInsets.only(bottom: 14),
              child: InkWell(
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => GarmentPage(
                      store: widget.store,
                      slug: product.slug,
                      api: api,
                    ),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 88,
                        height: 100,
                        child: product.image == null
                            ? const Icon(Icons.checkroom, size: 44)
                            : Image.network(
                                product.image!,
                                fit: BoxFit.contain,
                                errorBuilder: (_, _, _) =>
                                    const Icon(Icons.checkroom, size: 44),
                              ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              product.name,
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 8),
                            Text(product.price),
                            const SizedBox(height: 8),
                            const Text(
                              'Ver prenda',
                              style: TextStyle(color: Color(0xFF12644E)),
                            ),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right),
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (!loading && error == null)
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              spacing: 12,
              children: [
                OutlinedButton(
                  onPressed: offset > 0 ? () => load(page: offset - 20) : null,
                  child: const Text('Anterior'),
                ),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    total == 0
                        ? '0 prendas'
                        : '${offset + 1}–${offset + products.length} de $total',
                  ),
                ),
                OutlinedButton(
                  onPressed: offset + 20 < total
                      ? () => load(page: offset + 20)
                      : null,
                  child: const Text('Siguiente'),
                ),
              ],
            ),
        ],
      ),
    ),
  );
}

class GarmentPage extends StatefulWidget {
  const GarmentPage({
    super.key,
    required this.store,
    required this.slug,
    required this.api,
    this.initialVariantId,
  });
  final Store store;
  final String slug;
  final CatalogApi api;
  final int? initialVariantId;
  @override
  State<GarmentPage> createState() => _GarmentPageState();
}

class _GarmentPageState extends State<GarmentPage> {
  Garment? product;
  Map<String, dynamic>? fitting;
  List<FittingVariant> variants = [];
  FittingVariant? selected;
  String? error;
  int revision = 0;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    final current = ++revision;
    setState(() => error = null);
    try {
      final results = await Future.wait<Object>([
        widget.api.detail(widget.store, widget.slug),
        widget.api.fitting(widget.store, widget.slug),
      ]);
      if (!mounted || current != revision) return;
      final data = results[1] as Map<String, dynamic>;
      final rows = (data['variantes'] as List)
          .map((e) => FittingVariant(Map<String, dynamic>.from(e as Map)))
          .toList();
      if (data['producto_id'] != (results[0] as Garment).id) {
        throw const FormatException();
      }
      setState(() {
        product = results[0] as Garment;
        fitting = data;
        variants = rows;
        selected = rows.where((r) => r.id == widget.initialVariantId).firstOrNull
            ?? rows.where((r) => r.compatible).firstOrNull
            ?? rows.firstOrNull;
      });
    } on Object catch (e) {
      if (mounted && current == revision) {
        setState(
          () => error = e is AccessException
              ? e.message
              : 'No se pudo preparar el detalle de la prenda.',
        );
      }
    }
  }

  @override
  void dispose() {
    revision++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Detalle de la prenda')),
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          if (error != null) ...[
            Text(error!, style: const TextStyle(color: Colors.red)),
            OutlinedButton(onPressed: load, child: const Text('Reintentar')),
          ] else if (product == null)
            const Center(child: CircularProgressIndicator())
          else ...[
            Text(
              widget.store.name,
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 12),
            Text(
              product!.name,
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 12),
            Text(product!.price, style: Theme.of(context).textTheme.titleLarge),
            if (product!.image != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: Image.network(
                  product!.image!,
                  height: 220,
                  fit: BoxFit.contain,
                  errorBuilder: (_, _, _) =>
                      const Icon(Icons.checkroom, size: 90),
                ),
              ),
            const SizedBox(height: 16),
            Text(product!.data['descripcion'] as String? ?? ''),
            for (final field in ['material', 'medidas', 'temporada'])
              if ((product!.data[field] as String? ?? '').isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(
                    '${field[0].toUpperCase()}${field.substring(1)}: ${product!.data[field]}',
                  ),
                ),
            const SizedBox(height: 24),
            if (variants.isNotEmpty)
              DropdownButtonFormField<int>(
                initialValue: selected?.id,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Talla y color'),
                items: variants
                    .map(
                      (r) => DropdownMenuItem(
                        value: r.id,
                        child: Text(r.label, overflow: TextOverflow.ellipsis),
                      ),
                    )
                    .toList(),
                onChanged: (id) => setState(
                  () => selected = variants.firstWhere((r) => r.id == id),
                ),
              ),
            const SizedBox(height: 16),
            if (selected?.compatible == true) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Image.network(
                        widget.api
                            .assetUri(selected!.config['recurso_url'] as String)
                            .toString(),
                        height: 220,
                        fit: BoxFit.contain,
                        errorBuilder: (_, _, _) => const Padding(
                          padding: EdgeInsets.all(24),
                          child: Text('No se pudo cargar la vista previa.'),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        selected!.config['demostracion'] == true
                            ? 'Imagen ilustrativa del vestidor · Demostración'
                            : 'Recurso preparado para el vestidor',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => FittingPage(
                      api: widget.api,
                      product: product!,
                      variants: variants.where((r) => r.compatible).toList(),
                      initial: selected!,
                    ),
                  ),
                ),
                icon: const Icon(Icons.view_in_ar),
                label: const Text('Probar en vestidor virtual'),
              ),
              const SizedBox(height: 10),
              const Text(
                'Vista orientativa: no garantiza talla o ajuste físico ni reserva unidades.',
              ),
            ] else ...[
              Text(
                fitting?['motivo'] as String? ?? 'Esta talla y color todavía no tienen un recurso preparado para el vestidor.',
              ),
              if (variants.any((r) => r.compatible))
                const Text(
                  'Puedes elegir otra variante con vestidor disponible.',
                ),
              if ((fitting?['alternativas'] as List? ?? []).isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  'Prendas con vestidor disponible',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                for (final item in fitting!['alternativas'] as List)
                  TextButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => GarmentPage(
                          store: widget.store,
                          slug: item['slug'] as String,
                          api: widget.api,
                        ),
                      ),
                    ),
                    child: Text(item['nombre'] as String),
                  ),
              ],
            ],
          ],
        ],
      ),
    ),
  );
}
