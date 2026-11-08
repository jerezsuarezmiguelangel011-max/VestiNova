/// Modelos de CU08, CU19, CU23 y CU24; los IDs de producto y variante
/// deliberadamente NO son intercambiables.
class StoreProduct {
  const StoreProduct({
    required this.id,
    required this.slug,
    required this.name,
    required this.price,
    this.salePrice,
    this.promotion,
    this.imageUrl,
    this.category = '',
    this.categoryId,
    this.description = '',
    this.material = '',
    this.measurements = '',
    this.season = '',
    this.reasons = const [],
    this.availability = 'NO_VERIFICADA',
    this.comparisonVariants = const [],
  });

  factory StoreProduct.fromJson(Map<String, dynamic> json) {
    final id = json['id'] ?? json['producto_id'];
    if (id is! int ||
        id < 1 ||
        json['slug'] is! String ||
        json['nombre'] is! String) {
      throw const FormatException('Producto de catálogo no válido.');
    }
    final price = json['precio'];
    if (price is! String && price is! num) {
      throw const FormatException('Precio de catálogo no válido.');
    }
    final reasons = json['motivos'];
    return StoreProduct(
      id: id,
      slug: json['slug'] as String,
      name: json['nombre'] as String,
      price: price.toString(),
      salePrice: json['precio_promocional']?.toString(),
      promotion: json['promocion_nombre'] as String?,
      imageUrl: json['imagen_url'] as String?,
      category: (json['categoria_nombre'] ?? json['categoria'] ?? '') as String,
      categoryId: json['categoria_id'] as int?,
      description: (json['descripcion'] ?? '') as String,
      material: (json['material'] ?? '') as String,
      measurements: (json['medidas'] ?? '') as String,
      season: (json['temporada'] ?? '') as String,
      reasons: reasons is List
          ? reasons.whereType<String>().toList(growable: false)
          : const [],
      availability: (json['disponibilidad'] ?? 'NO_VERIFICADA') as String,
      comparisonVariants: json['variantes'] is List
          ? (json['variantes'] as List)
                .map(
                  (e) => StoreComparisonVariant.fromJson(
                    Map<String, dynamic>.from(e as Map),
                  ),
                )
                .toList()
          : const [],
    );
  }

  final int id;
  final String slug;
  final String name;
  final String price;
  final String? salePrice;
  final String? promotion;
  final String? imageUrl;
  final String category;
  final int? categoryId;
  final String description;
  final String material;
  final String measurements;
  final String season;
  final List<String> reasons;
  final String availability;
  final List<StoreComparisonVariant> comparisonVariants;
  String get effectivePrice => salePrice ?? price;
}

class StoreComparisonVariant {
  const StoreComparisonVariant({
    required this.size,
    required this.color,
    required this.branches,
  });
  factory StoreComparisonVariant.fromJson(Map<String, dynamic> json) =>
      StoreComparisonVariant(
        size: json['talla'] as String,
        color: json['color'] as String,
        branches: ((json['sucursales'] ?? []) as List).map((e) {
          final data = Map<String, dynamic>.from(e as Map);
          return '${data['sucursal']}: ${data['estado']}';
        }).toList(),
      );
  final String size;
  final String color;
  final List<String> branches;
}

class StoreVariant {
  const StoreVariant({
    required this.id,
    required this.size,
    required this.color,
  });
  factory StoreVariant.fromJson(Map<String, dynamic> json) => StoreVariant(
    id: json['id'] as int,
    size: json['talla'] as String,
    color: json['color'] as String,
  );
  final int id;
  final String size;
  final String color;
  String get label => '$size · $color';
}

class StoreStock {
  const StoreStock({
    required this.branch,
    required this.variantId,
    required this.status,
    this.branchId,
    this.updatedAt,
  });
  factory StoreStock.fromJson(Map<String, dynamic> json) => StoreStock(
    branch: (json['sucursal'] ?? '') as String,
    branchId: json['sucursal_id'] as int?,
    variantId: json['variante_id'] as int,
    status: json['saldo_registrado'] != true
        ? 'NO_VERIFICADO'
        : json['hay_disponibilidad'] == true
        ? 'DISPONIBLE'
        : 'AGOTADO',
    updatedAt: json['actualizado_en'] as String?,
  );
  final String branch;
  final int? branchId;
  final int variantId;
  final String status;
  final String? updatedAt;
}

class StoreWish {
  const StoreWish({
    required this.variantId,
    required this.product,
    required this.size,
    required this.color,
    required this.publicada,
    required this.stockStatus,
  });
  factory StoreWish.fromJson(Map<String, dynamic> json) => StoreWish(
    variantId: json['variante_id'] as int,
    product: StoreProduct.fromJson({
      'id': json['producto_id'],
      'slug': json['slug'] ?? '',
      'nombre': json['nombre'],
      'precio': json['precio_vigente'] ?? '0.00',
      'imagen_url': json['imagen_url'],
    }),
    size: json['talla'] as String,
    color: json['color'] as String,
    publicada: json['publicada'] == true,
    stockStatus: (json['disponibilidad'] ?? 'NO_VERIFICADA') as String,
  );
  final int variantId;
  final StoreProduct product;
  final String size;
  final String color;
  final bool publicada;
  final String stockStatus;
}

class StoreCategory {
  const StoreCategory({required this.id, required this.name});
  factory StoreCategory.fromJson(Map<String, dynamic> json) =>
      StoreCategory(id: json['id'] as int, name: json['nombre'] as String);
  final int id;
  final String name;
}

class StorePage {
  const StorePage({
    required this.items,
    required this.total,
    required this.limit,
    required this.offset,
  });
  factory StorePage.fromJson(Map<String, dynamic> json) => StorePage(
    items: (json['items'] as List)
        .map((e) => StoreProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList(),
    total: json['total'] as int,
    limit: json['limit'] as int,
    offset: json['offset'] as int,
  );
  final List<StoreProduct> items;
  final int total;
  final int limit;
  final int offset;
}

class StoreFilters {
  const StoreFilters({
    this.q = '',
    this.categoryId,
    this.size = '',
    this.color = '',
    this.season = '',
    this.minPrice = '',
    this.maxPrice = '',
    this.availability = '',
  });
  final String q;
  final int? categoryId;
  final String size;
  final String color;
  final String season;
  final String minPrice;
  final String maxPrice;
  /// Valores del filtro de stock vigente: DISPONIBLE, AGOTADO o vacío.
  final String availability;
  Map<String, String> toQuery() => {
    if (q.trim().isNotEmpty) 'q': q.trim(),
    if (categoryId != null) 'categoria_id': '$categoryId',
    if (size.trim().isNotEmpty) 'talla': size.trim(),
    if (color.trim().isNotEmpty) 'color': color.trim(),
    if (season.trim().isNotEmpty) 'temporada': season.trim(),
    if (minPrice.isNotEmpty) 'precio_min': minPrice,
    if (maxPrice.isNotEmpty) 'precio_max': maxPrice,
    if (availability == 'DISPONIBLE' || availability == 'AGOTADO')
      'disponibilidad': availability,
  };
}

extension StoreProductCache on StoreProduct {
  Map<String, dynamic> toJson() => {
    'id': id,
    'slug': slug,
    'nombre': name,
    'precio': price,
    'precio_promocional': salePrice,
    'promocion_nombre': promotion,
    'imagen_url': imageUrl,
    'categoria_nombre': category,
    'categoria_id': categoryId,
    'descripcion': description,
    'material': material,
    'medidas': measurements,
    'temporada': season,
    'motivos': reasons,
    'disponibilidad': availability,
  };
}

extension StoreVariantCache on StoreVariant {
  Map<String, dynamic> toJson() => {'id': id, 'talla': size, 'color': color};
}

extension StoreStockCache on StoreStock {
  Map<String, dynamic> toJson() => {
    'sucursal': branch,
    'sucursal_id': branchId,
    'variante_id': variantId,
    'saldo_registrado': status != 'NO_VERIFICADO',
    'hay_disponibilidad': status == 'DISPONIBLE',
    'actualizado_en': updatedAt,
  };
}
