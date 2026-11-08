import 'package:flutter/material.dart';

import 'storefront_api.dart';
import 'storefront_models.dart';
import 'storefront_repository.dart';
import 'storefront_widgets.dart';

class StorefrontCatalogPage extends StatefulWidget {
  const StorefrontCatalogPage({super.key, required this.tienda, required this.repository,
    required this.onOpen, required this.onCompare, required this.isSelected,
    this.home = false});
  final String tienda;
  final StorefrontRepository repository;
  final ValueChanged<StoreProduct> onOpen;
  final ValueChanged<StoreProduct> onCompare;
  final bool Function(int productId) isSelected;
  final bool home;
  @override
  State<StorefrontCatalogPage> createState() => _StorefrontCatalogPageState();
}

class _StorefrontCatalogPageState extends State<StorefrontCatalogPage> {
  final _search = TextEditingController();
  final _size = TextEditingController();
  final _color = TextEditingController();
  final _season = TextEditingController();
  final _min = TextEditingController();
  final _max = TextEditingController();
  List<StoreCategory> _categories = [];
  StorePage? _page;
  bool _loading = false;
  bool _downloading = false;
  bool _cache = false;
  bool _partial = false;
  String? _savedAt;
  String? _error;
  int? _category;
  int _revision = 0;
  @override
  void initState() {
    super.initState();
    widget.repository.warmVariants(widget.tienda).catchError((Object _) {}).then((_) { if (mounted) _load(); });
    _loadCategories();
  }
  @override
  void dispose() {
    _revision++;
    for (final c in [_search, _size, _color, _season, _min, _max]) { c.dispose(); }
    super.dispose();
  }
  StoreFilters get _filters => StoreFilters(q: _search.text, categoryId: _category,
    size: _size.text, color: _color.text, season: _season.text,
    minPrice: _min.text, maxPrice: _max.text);

  Future<void> _loadCategories() async {
    try {
      final result = await widget.repository.categories(widget.tienda);
      if (mounted) setState(() => _categories = result.value);
    } catch (_) { /* La consulta principal comunica errores de red. */ }
  }

  Future<void> _load({int offset = 0}) async {
    final id = ++_revision;
    setState(() { _loading = true; _error = null; });
    try {
      final result = await widget.repository.products(widget.tienda,
        filters: _filters, offset: offset);
      if (!mounted || id != _revision) return;
      setState(() {
        _page = result.value; _cache = result.fromCache;
        _partial = result.partial; _savedAt = result.savedAt;
      });
    } catch (error) {
      if (!mounted || id != _revision) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted && id == _revision) setState(() => _loading = false);
    }
  }

  Future<void> _download() async {
    if (_downloading) return;
    setState(() => _downloading = true);
    try {
      final count = await widget.repository.download(widget.tienda);
      if (!mounted) return;
      notice(context, '$count prendas guardadas para consulta local.');
    } catch (error) {
      if (mounted) notice(context, 'No se completó la descarga: $error. Se conserva la copia anterior.');
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  Widget _filterText(TextEditingController controller, String label) => SizedBox(
    width: 134, child: TextField(
      controller: controller, decoration: InputDecoration(labelText: label, isDense: true),
      onSubmitted: (_) => _load(),
    ),
  );

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: () => _load(),
    child: ListView(padding: const EdgeInsets.all(16), children: [
      if (widget.home) ...[
        Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(color: vnInk, borderRadius: BorderRadius.circular(16)),
          child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Moda masculina', style: TextStyle(color: Colors.white70)),
            SizedBox(height: 7),
            Text('Encuentra tu estilo', style: TextStyle(color: Colors.white,
              fontSize: 25, fontWeight: FontWeight.w600)),
            SizedBox(height: 8),
            Text('Prendas reales de tu tienda. Precio en bolivianos.',
              style: TextStyle(color: Colors.white70)),
          ]),
        ),
        const SizedBox(height: 18),
      ],
      Text(widget.home ? 'Explorar prendas' : 'Catálogo de prendas',
          style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 12),
      TextField(
        controller: _search,
        decoration: InputDecoration(
          labelText: 'Buscar prendas', prefixIcon: const Icon(Icons.search),
          suffixIcon: IconButton(icon: const Icon(Icons.close), tooltip: 'Limpiar búsqueda',
            onPressed: () { _search.clear(); _load(); }),
        ),
        onSubmitted: (_) => _load(),
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 6, children: [
        ChoiceChip(label: const Text('Todas'), selected: _category == null,
          onSelected: (_) { setState(() => _category = null); _load(); }),
        ..._categories.map((c) => ChoiceChip(label: Text(c.name), selected: _category == c.id,
          onSelected: (_) { setState(() => _category = c.id); _load(); })),
      ]),
      const SizedBox(height: 10),
      ExpansionTile(title: const Text('Filtros avanzados'),
        childrenPadding: const EdgeInsets.only(bottom: 12),
        children: [
          Wrap(spacing: 8, runSpacing: 8, children: [
            _filterText(_size, 'Talla'), _filterText(_color, 'Color'),
            _filterText(_season, 'Temporada'),
            _filterText(_min, 'Precio mín. Bs'), _filterText(_max, 'Precio máx. Bs'),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            FilledButton(onPressed: () => _load(), child: const Text('Aplicar')),
            const SizedBox(width: 10),
            TextButton(onPressed: () {
              for (final c in [_size,_color,_season,_min,_max]) { c.clear(); }
              setState(() => _category = null); _load();
            }, child: const Text('Limpiar filtros')),
          ]),
        ],
      ),
      Align(alignment: Alignment.centerLeft, child: OutlinedButton.icon(
        onPressed: _downloading ? null : _download,
        icon: _downloading ? const SizedBox(height: 17, width: 17,
          child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.download_for_offline_outlined),
        label: const Text('Preparar catálogo sin conexión'),
      )),
      if (_cache) CacheNotice(savedAt: _savedAt, partial: _partial),
      if (_loading) const LinearProgressIndicator(),
      if (_error != null) StorefrontMessage(message: _error!, retry: () => _load()),
      if (_error == null && !_loading && _page?.items.isEmpty == true)
        const StorefrontMessage(message: 'No encontramos prendas para esos filtros.'),
      if (_page case final page?) ...[
        Padding(padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text('${page.total} prendas · ${page.offset + 1}–${page.offset + page.items.length}',
            style: Theme.of(context).textTheme.bodySmall)),
        ...page.items.map((p) => ProductRow(
          item: p, onOpen: () => widget.onOpen(p),
          onCompare: () => widget.onCompare(p), inComparison: widget.isSelected(p.id),
        )),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          TextButton(onPressed: _loading || page.offset == 0 ? null
              : () => _load(offset: page.offset < StorefrontRepository.pageSize ? 0 : page.offset - StorefrontRepository.pageSize),
            child: const Text('Anterior')),
          TextButton(onPressed: _loading || page.offset + page.items.length >= page.total ? null
              : () => _load(offset: page.offset + StorefrontRepository.pageSize),
            child: const Text('Siguiente')),
        ]),
      ],
      const SizedBox(height: 30),
    ]),
  );
}
