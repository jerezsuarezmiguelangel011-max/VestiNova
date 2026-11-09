import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import 'storefront_api.dart';
import 'storefront_models.dart';
import 'storefront_repository.dart';
import 'storefront_widgets.dart';

class StorefrontDetailPage extends StatefulWidget {
  const StorefrontDetailPage({
    super.key,
    required this.tienda,
    required this.slug,
    required this.repository,
    required this.api,
    required this.controller,
    required this.onCompare,
    required this.onRecommendations,
    required this.onLoginRequired,
    required this.onPurchase,
    required this.onAlerts,
    this.selectedBranchId,
  });
  final String tienda;
  final String slug;
  final StorefrontRepository repository;
  final StorefrontApi api;
  final SessionController controller;
  final int? selectedBranchId;
  final ValueChanged<StoreProduct> onCompare;
  final ValueChanged<String> onRecommendations;
  final VoidCallback onLoginRequired;
  final void Function(StoreProduct, StoreVariant, List<StoreStock>) onPurchase;
  final void Function(StoreProduct, StoreVariant, List<StoreStock>) onAlerts;
  @override
  State<StorefrontDetailPage> createState() => _StorefrontDetailPageState();
}

class _StorefrontDetailPageState extends State<StorefrontDetailPage> {
  StorefrontResult<StoreProduct>? _detail;
  StorefrontResult<List<StoreVariant>>? _variants;
  StorefrontResult<List<StoreStock>>? _stock;
  bool _busy = true;
  bool _saving = false;
  String? _error;
  int? _variantId;
  int _loadId = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final id = ++_loadId;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final product = await widget.repository.product(
        widget.tienda,
        widget.slug,
      );
      final variants = await widget.repository.variants(
        widget.tienda,
        widget.slug,
      );
      StorefrontResult<List<StoreStock>>? stock;
      try {
        stock = await widget.repository.availability(
          widget.tienda,
          widget.slug,
        );
      } on StorefrontException catch (error) {
        if (!error.network) {
          rethrow;
        }
      }
      if (!mounted || id != _loadId) {
        return;
      }
      setState(() {
        _detail = product;
        _variants = variants;
        _stock = stock;
        if (!variants.value.any((v) => v.id == _variantId)) {
          _variantId = null;
        }
      });
      // El seguimiento se registra exclusivamente tras consentimiento explícito
      // y sesión válida; el error de seguimiento no bloquea el catálogo.
      final token = widget.controller.customerToken;
      if (token != null &&
          !widget.controller.offlineMode &&
          !product.fromCache) {
        try {
          if (await widget.api.consent(widget.tienda, token)) {
            await widget.api.recordVisit(widget.tienda, token, widget.slug);
          }
        } catch (_) {
          /* Consultar la prenda nunca depende del seguimiento. */
        }
      }
    } catch (error) {
      if (mounted && id == _loadId) {
        setState(() => _error = '$error');
      }
    } finally {
      if (mounted && id == _loadId) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _saveWish() async {
    final token = widget.controller.customerToken;
    if (token == null) {
      widget.onLoginRequired();
      return;
    }
    if (widget.controller.offlineMode) {
      notice(
        context,
        'Guardar deseos requiere conexión. No se registró ningún cambio.',
      );
      return;
    }
    if (_variantId == null) {
      notice(context, 'Selecciona una talla y color.');
      return;
    }
    if (_saving) {
      return;
    }
    setState(() => _saving = true);
    try {
      final created = await widget.api.addWish(
        widget.tienda,
        token,
        _variantId!,
      );
      if (mounted) {
        notice(
          context,
          created
              ? 'Prenda guardada en tus deseos.'
              : 'Ya estaba guardada en tus deseos.',
        );
      }
    } catch (error) {
      if (mounted) {
        notice(context, 'No se guardó el deseo: $error');
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final product = _detail?.value;
    return Scaffold(
      appBar: AppBar(title: const Text('Detalle de prenda')),
      body: _busy
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? StorefrontMessage(message: _error!, retry: _load)
          : product == null
          ? const StorefrontMessage(message: 'Prenda no disponible.')
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Center(child: ProductPhoto(product.imageUrl, height: 220)),
                const SizedBox(height: 16),
                Text(
                  product.name,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 6),
                Text(product.category),
                const SizedBox(height: 8),
                Text(
                  'Bs ${product.effectivePrice}',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: vnGreen,
                    fontSize: 24,
                  ),
                ),
                if (product.salePrice != null)
                  Text(
                    'Antes Bs ${product.price} · ${product.promotion ?? 'Promoción'}',
                  ),
                const SizedBox(height: 10),
                if (product.description.isNotEmpty) Text(product.description),
                if (product.material.isNotEmpty)
                  Text('Material: ${product.material}'),
                if (product.measurements.isNotEmpty)
                  Text('Medidas: ${product.measurements}'),
                if (product.season.isNotEmpty)
                  Text('Temporada: ${product.season}'),
                if (_detail?.fromCache == true)
                  CacheNotice(
                    savedAt: _detail?.savedAt,
                    partial: _detail?.partial ?? false,
                  ),
                const SizedBox(height: 20),
                Text(
                  'Talla y color',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 7),
                if (_variants?.fromCache == true)
                  CacheNotice(
                    savedAt: _variants?.savedAt,
                    partial: _variants?.partial ?? false,
                  ),
                if (_variants?.value.isEmpty == true)
                  const Text('No hay variantes publicadas.'),
                if (_variants case final result?)
                  if (result.value.isNotEmpty)
                    DropdownButtonFormField<int>(
                      key: ValueKey(_variantId),
                      initialValue: _variantId,
                      decoration: const InputDecoration(
                        labelText: 'Selecciona una variante',
                      ),
                      items: result.value
                          .map(
                            (v) => DropdownMenuItem<int>(
                              value: v.id,
                              child: Text(v.label),
                            ),
                          )
                          .toList(),
                      onChanged: (id) => setState(() => _variantId = id),
                    ),
                const SizedBox(height: 12),
                Text(
                  widget.selectedBranchId == null
                      ? 'Disponibilidad conocida por sucursal'
                      : 'Disponibilidad en la sucursal elegida',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (_stock?.fromCache == true)
                  CacheNotice(savedAt: _stock?.savedAt),
                if (_stock == null)
                  const Text('Disponibilidad no verificada con el servidor.'),
                if (_stock case final known?) ...[
                  ...known.value
                      .where(
                        (stock) =>
                            (_variantId == null ||
                                stock.variantId == _variantId) &&
                            (widget.selectedBranchId == null ||
                                stock.branchId == widget.selectedBranchId),
                      )
                      .map(
                        (stock) => ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(stock.branch),
                          subtitle: Text(
                            'Estado: ${stock.status} · ${stock.updatedAt ?? 'Sin saldo registrado'}',
                          ),
                        ),
                      ),
                ],
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _variantId == null || _busy
                      ? null
                      : () {
                          final selected = _variants!.value.firstWhere(
                            (v) => v.id == _variantId,
                          );
                          widget.onPurchase(
                            product,
                            selected,
                            _stock?.value ?? [],
                          );
                        },
                  icon: const Icon(Icons.shopping_bag_outlined),
                  label: const Text('Comprar · CU09'),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: _variantId == null || _busy
                      ? null
                      : () {
                          final selected = _variants!.value.firstWhere(
                            (v) => v.id == _variantId,
                          );
                          widget.onAlerts(
                            product,
                            selected,
                            _stock?.value ?? [],
                          );
                        },
                  icon: const Icon(Icons.notifications_active_outlined),
                  label: const Text('Avisarme si hay reposición · CU26'),
                ),
                const SizedBox(height: 8),
                FilledButton.icon(
                  onPressed: _saving ? null : _saveWish,
                  icon: const Icon(Icons.favorite_border),
                  label: const Text('Guardar variante en deseos'),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => widget.onCompare(product),
                  icon: const Icon(Icons.compare_arrows),
                  label: const Text('Agregar a comparación'),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => widget.onRecommendations(product.slug),
                  icon: const Icon(Icons.auto_awesome),
                  label: const Text('Ver prendas similares'),
                ),
              ],
            ),
    );
  }
}
