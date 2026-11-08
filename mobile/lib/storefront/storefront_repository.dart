import 'storefront_api.dart';
import 'storefront_cache.dart';
import 'storefront_models.dart';

class StorefrontResult<T> {
  const StorefrontResult(this.value, {this.fromCache = false, this.savedAt, this.partial = false});
  final T value;
  final bool fromCache;
  final String? savedAt;
  final bool partial;
}

class StorefrontRepository {
  StorefrontRepository(this.api, this.cache);
  final StorefrontApi api;
  final StorefrontCache cache;
  static const pageSize = 20;

  Future<void> _save(String tienda, String key, Object data) async {
    try { await cache.write(tienda, key, data); } catch (_) {
      // Fallas del caché opcional nunca impiden una consulta pública ONLINE.
    }
  }
  Future<CachedPublicData?> _read(String tienda, String key) async {
    try { return await cache.read(tienda, key); } catch (_) { return null; }
  }

  Future<StorefrontResult<StorePage>> products(String tienda, {
    StoreFilters filters = const StoreFilters(), int offset = 0,
  }) async {
    try {
      final result = await api.products(tienda, filters: filters,
        limit: pageSize, offset: offset);
      if (offset == 0 && filters.toQuery().isEmpty) {
        final existing = await _read(tienda, 'products');
        final old = existing?.value;
        if (old is! Map || old['complete'] != true) {
          await _save(tienda, 'products', {
            'complete': result.items.length == result.total,
            'items': result.items.map((e) => e.toJson()).toList(),
          });
        }
      }
      return StorefrontResult(result);
    } on StorefrontException catch (e) {
      if (!e.network) rethrow;
      final saved = await _read(tienda, 'products');
      if (saved == null) rethrow;
      final data = Map<String, dynamic>.from(saved.value as Map);
      await warmVariants(tienda);
      final items = (data['items'] as List)
        .map((e) => StoreProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .where((product) => _matches(product, filters)).toList();
      final page = items.skip(offset).take(pageSize).toList();
      return StorefrontResult(
        StorePage(items: page, total: items.length, limit: pageSize, offset: offset),
        fromCache: true, savedAt: saved.savedAt, partial: data['complete'] != true,
      );
    }
  }

  bool _matches(StoreProduct item, StoreFilters filters) {
    if (filters.q.isNotEmpty && !item.name.toLowerCase().contains(filters.q.trim().toLowerCase())) return false;
    if (filters.categoryId != null && item.categoryId != filters.categoryId) return false;
    if (filters.season.isNotEmpty && item.season.toLowerCase() != filters.season.trim().toLowerCase()) return false;
    final min = double.tryParse(filters.minPrice);
    final max = double.tryParse(filters.maxPrice);
    final price = double.tryParse(item.price);
    if (price == null || (min != null && price < min) || (max != null && price > max)) return false;
    // No inventar variantes conocidas: si faltan no incluir el producto.
    if (filters.size.isNotEmpty || filters.color.isNotEmpty) {
      final variants = _localVariants[item.slug] ?? const <StoreVariant>[];
      if (!variants.any((v) =>
        (filters.size.isEmpty || v.size.toLowerCase() == filters.size.trim().toLowerCase()) &&
        (filters.color.isEmpty || v.color.toLowerCase() == filters.color.trim().toLowerCase()))) {
        return false;
      }
    }
    return true;
  }
  Map<String, List<StoreVariant>> _localVariants = {};

  Future<void> warmVariants(String tienda) async {
    final cached = await _read(tienda, 'variants');
    final bySlug = <String, List<StoreVariant>>{};
    if (cached != null && cached.value is Map && (cached.value as Map)['items'] is List) {
      for (final raw in (cached.value as Map)['items'] as List) {
        final data = Map<String, dynamic>.from(raw as Map);
        final slug = data['producto_slug'] as String;
        bySlug.putIfAbsent(slug, () => []).add(StoreVariant.fromJson(data));
      }
    }
    _localVariants = bySlug;
  }

  Future<StorefrontResult<List<StoreCategory>>> categories(String tienda) async {
    try {
      final result = await api.categories(tienda);
      await _save(tienda, 'categories', result.map((e) => {'id': e.id, 'nombre': e.name}).toList());
      return StorefrontResult(result);
    } on StorefrontException catch (e) {
      if (!e.network) rethrow;
      final saved = await _read(tienda, 'categories');
      if (saved == null) rethrow;
      return StorefrontResult(
        (saved.value as List).map((e) => StoreCategory.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
        fromCache: true, savedAt: saved.savedAt);
    }
  }

  Future<StorefrontResult<StoreProduct>> product(String tienda, String slug) async {
    try {
      final result = await api.product(tienda, slug);
      await _save(tienda, 'detail/$slug', result.toJson());
      return StorefrontResult(result);
    } on StorefrontException catch (e) {
      if (!e.network) rethrow;
      var saved = await _read(tienda, 'detail/$slug');
      if (saved == null) {
        final catalog = await _read(tienda, 'products');
        final raw = catalog?.value;
        if (raw is Map && raw['items'] is List) {
          for (final p in raw['items'] as List) {
            if (p is Map && p['slug'] == slug) {
              return StorefrontResult(StoreProduct.fromJson(Map<String, dynamic>.from(p)),
                fromCache: true, savedAt: catalog!.savedAt, partial: true);
            }
          }
        }
        rethrow;
      }
      return StorefrontResult(StoreProduct.fromJson(Map<String, dynamic>.from(saved.value as Map)),
        fromCache: true, savedAt: saved.savedAt);
    }
  }

  Future<StorefrontResult<List<StoreVariant>>> variants(String tienda, String slug) async {
    try {
      final result = await api.variants(tienda, slug);
      await _save(tienda, 'variants/$slug', result.map((v) => v.toJson()).toList());
      return StorefrontResult(result);
    } on StorefrontException catch (e) {
      if (!e.network) rethrow;
      final saved = await _read(tienda, 'variants/$slug');
      if (saved != null) {
        return StorefrontResult(
          (saved.value as List).map((v) => StoreVariant.fromJson(Map<String,dynamic>.from(v as Map))).toList(),
          fromCache: true, savedAt: saved.savedAt);
      }
      await warmVariants(tienda);
      final known = _localVariants[slug];
      if (known != null) return StorefrontResult(known, fromCache: true, partial: true);
      rethrow;
    }
  }

  Future<StorefrontResult<List<StoreStock>>> availability(String tienda, String slug) async {
    try {
      final result = await api.availability(tienda, slug);
      await _save(tienda, 'stock/$slug', result.map((e) => e.toJson()).toList());
      return StorefrontResult(result);
    } on StorefrontException catch (e) {
      if (!e.network) rethrow;
      final saved = await _read(tienda, 'stock/$slug');
      if (saved == null) rethrow;
      return StorefrontResult((saved.value as List)
        .map((e) => StoreStock.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
        fromCache: true, savedAt: saved.savedAt);
    }
  }

  /// Precarga datos públicos, con límite explícito. El caché se actualiza sólo
  /// al finalizar; una descarga interrumpida conserva la copia anterior.
  Future<int> download(String tienda) async {
    final products = <StoreProduct>[];
    int total = 0;
    for (var offset = 0; offset < 300; offset += 100) {
      final page = await api.products(tienda, limit: 100, offset: offset);
      total = page.total;
      products.addAll(page.items);
      if (products.length >= page.total || page.items.isEmpty) break;
    }
    final variants = <Map<String, dynamic>>[];
    int variantTotal = 0;
    for (var offset = 0; offset < 600; offset += 100) {
      final page = await api.allVariantsPage(tienda, offset);
      variantTotal = page['total'] as int;
      variants.addAll((page['items'] as List).map((e) => Map<String, dynamic>.from(e as Map)));
      if (variants.length >= variantTotal || (page['items'] as List).isEmpty) break;
    }
    final categories = await api.categories(tienda);
    await cache.writeBundle(tienda, {
      'products': {
        'complete': products.length >= total,
        'items': products.map((e) => e.toJson()).toList(),
      },
      'variants': {
        'complete': variants.length >= variantTotal,
        'items': variants,
      },
      'categories': categories.map((e) => {'id': e.id, 'nombre': e.name}).toList(),
    });
    await warmVariants(tienda);
    return products.length;
  }
}
