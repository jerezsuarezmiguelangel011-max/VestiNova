import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import 'storefront_api.dart';
import 'storefront_models.dart';
import 'storefront_widgets.dart';

class StorefrontWishlistPage extends StatefulWidget {
  const StorefrontWishlistPage({super.key, required this.tienda,
    required this.api, required this.session, required this.onOpen});
  final String tienda;
  final StorefrontApi api;
  final SessionController session;
  final ValueChanged<StoreProduct> onOpen;
  @override
  State<StorefrontWishlistPage> createState() => _StorefrontWishlistPageState();
}

class _StorefrontWishlistPageState extends State<StorefrontWishlistPage> {
  List<StoreWish> _items = [];
  bool _busy = true;
  int? _removing;
  String? _error;
  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final token = widget.session.customerToken;
    if (token == null) return;
    setState(() { _busy = true; _error = null; });
    try {
      final result = await widget.api.wishes(widget.tienda, token);
      if (mounted) setState(() => _items = result);
    } catch (e) { if (mounted) setState(() => _error = '$e'); }
    finally { if (mounted) setState(() => _busy = false); }
  }

  Future<void> _remove(StoreWish wish) async {
    final token = widget.session.customerToken;
    if (token == null || _removing != null) return;
    setState(() => _removing = wish.variantId);
    try {
      await widget.api.removeWish(widget.tienda, token, wish.variantId);
      if (!mounted) return;
      setState(() => _items.removeWhere((item) => item.variantId == wish.variantId));
      notice(context, 'Prenda retirada de tus deseos.');
    } catch (e) { if (mounted) notice(context, 'No se pudo eliminar el deseo: $e'); }
    finally { if (mounted) setState(() => _removing = null); }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _load,
    child: ListView(padding: const EdgeInsets.all(16), children: [
      Text('Mis deseos', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      const Text('Guardar una prenda no reserva existencias ni congela su precio.'),
      const SizedBox(height: 12),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) StorefrontMessage(message: _error!, retry: _load),
      if (!_busy && _error == null && _items.isEmpty)
        const StorefrontMessage(message: 'Tu lista está vacía. Guarda una talla y color desde el catálogo.'),
      if (_error == null) ..._items.map((wish) => Card(
        child: Padding(padding: const EdgeInsets.all(12), child: Row(children: [
          ProductPhoto(wish.product.imageUrl, height: 88),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(wish.product.name, style: Theme.of(context).textTheme.titleMedium),
            Text('${wish.size} / ${wish.color} · ${wish.stockStatus}'),
            Text(wish.publicada ? 'Bs ${wish.product.price}' : 'Prenda despublicada'),
            Wrap(spacing: 4, children: [
              TextButton(onPressed: wish.publicada ? () => widget.onOpen(wish.product) : null,
                child: const Text('Ver prenda')),
              TextButton(onPressed: _removing == null ? () => _remove(wish) : null,
                child: const Text('Quitar')),
            ]),
          ])),
        ])),
      )),
    ]),
  );
}
