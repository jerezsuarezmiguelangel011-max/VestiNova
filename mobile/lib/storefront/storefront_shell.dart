import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import '../screens/access_page.dart';
import '../screens/account_page.dart';
import 'storefront_api.dart';
import 'storefront_cache.dart';
import 'storefront_catalog.dart';
import 'storefront_comparison.dart';
import 'storefront_detail.dart';
import 'storefront_models.dart';
import 'storefront_recommendations.dart';
import 'storefront_repository.dart';
import 'storefront_widgets.dart';
import 'storefront_wishlist.dart';

/// Pantalla comercial CU08/CU19/CU23/CU24. La sesión, roles y CU10 continúan
/// bajo los controladores y páginas originales de la aplicación.
class StorefrontShell extends StatefulWidget {
  const StorefrontShell({super.key, required this.controller, required this.slug,
    required this.storeName});
  final SessionController controller;
  final String slug;
  final String storeName;
  @override
  State<StorefrontShell> createState() => _StorefrontShellState();
}

class _StorefrontShellState extends State<StorefrontShell> {
  late final StorefrontApi _api;
  late final StorefrontCache _cache;
  late final StorefrontRepository _repository;
  final List<StoreProduct> _compare = [];
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    _api = StorefrontApi(widget.controller.api.config);
    _cache = StorefrontCache();
    _repository = StorefrontRepository(_api, _cache);
  }

  @override
  void dispose() {
    _api.close();
    _cache.close();
    super.dispose();
  }

  bool _selected(int id) => _compare.any((p) => p.id == id);

  void _addCompare(StoreProduct product) {
    if (_selected(product.id)) {
      notice(context, 'La prenda ya está seleccionada.');
      return;
    }
    if (_compare.length >= 4) {
      notice(context, 'Puedes comparar hasta cuatro prendas diferentes.');
      return;
    }
    setState(() => _compare.add(product));
    notice(context, 'Prenda añadida a la comparación (${_compare.length}/4).');
  }

  void _removeCompare(int productId) {
    setState(() => _compare.removeWhere((p) => p.id == productId));
  }

  void _openDetail(StoreProduct item) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => StorefrontDetailPage(
      key: ValueKey('${widget.slug}/${item.slug}'),
      tienda: widget.slug, slug: item.slug,
      repository: _repository, api: _api,
      controller: widget.controller, onCompare: _addCompare,
      onRecommendations: _openRecommendations,
      onLoginRequired: () {
        Navigator.of(context).popUntil((route) => route.isFirst);
        if (!widget.controller.signedIn) {
          setState(() => _tab = 4);
          notice(context, 'Inicia sesión como Cliente para guardar deseos.');
        } else {
          notice(context, 'Solo una cuenta de Cliente puede guardar deseos.');
        }
      },
    )));
  }

  void _openRecommendations([String? slug]) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => Scaffold(
      appBar: AppBar(title: const Text('Prendas para ti')),
      body: StorefrontRecommendationsPage(
        tienda: widget.slug, api: _api, session: widget.controller,
        reference: slug, onOpen: _openDetail, onCompare: _addCompare,
        isSelected: _selected,
      ),
    )));
  }

  Widget _account() => SingleChildScrollView(
    padding: const EdgeInsets.all(16),
    child: widget.controller.signedIn
        ? AccountPage(controller: widget.controller)
        : AccessPage(controller: widget.controller),
  );

  @override
  Widget build(BuildContext context) {
    final isCustomer = widget.controller.isCustomer;
    final token = widget.controller.customerToken;
    final hasAccess = isCustomer && token != null && !widget.controller.offlineMode;
    final accountKey = widget.controller.account?.id ?? 0;

    Widget body;
    switch (_tab) {
      case 0:
      case 1:
        body = StorefrontCatalogPage(
          key: ValueKey('${widget.slug}/catalog/$_tab'),
          tienda: widget.slug, repository: _repository,
          onOpen: _openDetail, onCompare: _addCompare,
          isSelected: _selected, home: _tab == 0,
        );
        break;
      case 2:
        body = hasAccess ? StorefrontWishlistPage(
          key: ValueKey('wishes/${widget.slug}/$accountKey'),
          tienda: widget.slug, api: _api,
          session: widget.controller, onOpen: _openDetail,
        ) : StorefrontMessage(
          message: isCustomer && widget.controller.offlineMode
              ? 'La lista de deseos requiere conexión. No se realizarán cambios sin confirmar.'
              : 'Inicia sesión como Cliente de esta tienda para consultar tus deseos.',
          retry: isCustomer ? null : () => setState(() => _tab = 4),
        );
        break;
      case 3:
        body = StorefrontComparisonPage(
          tienda: widget.slug, api: _api,
          selected: List.unmodifiable(_compare),
          onRemove: _removeCompare, onOpen: _openDetail,
        );
        break;
      default:
        body = _account();
        break;
    }

    return Scaffold(
      appBar: AppBar(
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('VN · VestiNova', style: TextStyle(fontWeight: FontWeight.bold)),
          Text(widget.storeName, style: const TextStyle(fontSize: 12)),
        ]),
        actions: [
          IconButton(tooltip: 'Recomendaciones',
            onPressed: () => _openRecommendations(),
            icon: const Icon(Icons.auto_awesome_outlined)),
          if (!widget.controller.signedIn) IconButton(
            tooltip: 'Cambiar tienda',
            onPressed: widget.controller.leaveStore,
            icon: const Icon(Icons.store_mall_directory_outlined)),
        ],
      ),
      body: SafeArea(child: Column(children: [
        if (widget.controller.busy) const LinearProgressIndicator(),
        if (widget.controller.error != null) Card(color: const Color(0xFFFFE9E3),
          child: Padding(padding: const EdgeInsets.all(10),
            child: Text(widget.controller.error!))),
        if (widget.controller.notice != null) Card(color: const Color(0xFFE0EFE6),
          child: Padding(padding: const EdgeInsets.all(10),
            child: Text(widget.controller.notice!))),
        Expanded(child: body),
      ])),
      bottomNavigationBar: NavigationBar(
        height: 75, selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Inicio'),
          NavigationDestination(icon: Icon(Icons.grid_view_outlined), label: 'Catálogo'),
          NavigationDestination(icon: Icon(Icons.favorite_border), label: 'Deseos'),
          NavigationDestination(icon: Icon(Icons.compare_arrows), label: 'Comparar'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Cuenta'),
        ],
      ),
    );
  }
}
