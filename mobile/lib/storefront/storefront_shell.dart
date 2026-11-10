import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import '../auth/auth_models.dart';
import '../tryon/catalog_api.dart';
import '../tryon/catalog_page.dart';
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
import '../commerce/mobile_checkout_page.dart';
import '../commerce/mobile_reviews_page.dart';
import '../commerce/mobile_alerts_page.dart';
import '../commerce/mobile_commerce_api.dart';
import '../commerce/mobile_order_store.dart';
import '../commerce/purchase_sync.dart';

/// Pantalla comercial CU08/CU19/CU23/CU24. La sesión, roles y CU10 continúan
/// bajo los controladores y páginas originales de la aplicación.
class StorefrontShell extends StatefulWidget {
  const StorefrontShell({
    super.key,
    required this.controller,
    required this.slug,
    required this.storeName,
  });
  final SessionController controller;
  final String slug;
  final String storeName;
  @override
  State<StorefrontShell> createState() => _StorefrontShellState();
}

class _StorefrontShellState extends State<StorefrontShell>
    with WidgetsBindingObserver {
  late final StorefrontApi _api;
  late final StorefrontCache _cache;
  late final StorefrontRepository _repository;
  final List<StoreProduct> _compare = [];
  int _tab = 0;
  bool _showStaffLogin = false;
  List<StoreBranch> _branches = const [];
  int _selectedBranchId = 0;
  bool _branchesLoading = true;
  bool _branchesError = false;
  StreamSubscription<List<ConnectivityResult>>? _networkSubscription;
  bool _noNetwork = false;

  @override
  void initState() {
    super.initState();
    _api = StorefrontApi(widget.controller.api.config);
    _cache = StorefrontCache();
    _repository = StorefrontRepository(_api, _cache);
    _loadPublicBranches();
    WidgetsBinding.instance.addObserver(this);
    _networkSubscription = Connectivity().onConnectivityChanged.listen((
      results,
    ) {
      final hasNetwork = !results.contains(ConnectivityResult.none);
      if (_noNetwork && hasNetwork) _syncPending();
      _noNetwork = !hasNetwork;
    }, onError: (Object _) {});
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _syncPending();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _syncPending();
  }

  Future<void> _syncPending() async {
    if (!Platform.isAndroid) return;
    final account = widget.controller.account;
    final token = widget.controller.customerToken;
    if (!widget.controller.isCustomer || token == null || account == null) {
      return;
    }
    final store = MobileOrderStore();
    final api = MobileCommerceApi(widget.controller.api.config);
    try {
      await const PurchaseSyncService().synchronize(
        tienda: widget.slug,
        customerId: account.id,
        token: token,
        store: store,
        api: api,
      );
    } catch (_) {
      // Sin Internet se conserva la cola; el trabajador Android reintentará.
    } finally {
      api.close();
      await store.close();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _networkSubscription?.cancel();
    _api.close();
    _cache.close();
    super.dispose();
  }

  Future<void> _loadPublicBranches() async {
    if (mounted)
      setState(() {
        _branchesLoading = true;
        _branchesError = false;
      });
    try {
      final branches = await _api.publicBranches(widget.slug);
      if (!mounted) return;
      setState(() {
        _branches = branches;
        _selectedBranchId = 0;
      });
    } catch (_) {
      if (mounted) setState(() => _branchesError = true);
    } finally {
      if (mounted) setState(() => _branchesLoading = false);
    }
  }

  Widget _branchSelector() => Container(
    margin: const EdgeInsets.only(bottom: 2),
    padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
    decoration: BoxDecoration(
      color: const Color(0xFFF0F4EC),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: const Color(0xFFD0DECE)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Wrap(
          spacing: 8,
          runSpacing: 7,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Icon(
              Icons.location_on_outlined,
              size: 20,
              color: Color(0xFF1B573E),
            ),
            SizedBox(width: 7),
            Text(
              'Consulta por sucursal',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: Color(0xFF1A4533),
              ),
            ),
          ],
        ),
        const SizedBox(height: 5),
        const Text(
          'Puedes explorar todas las prendas sin elegir sucursal.',
          style: TextStyle(fontSize: 11, color: Color(0xFF5A715F)),
        ),
        const SizedBox(height: 10),
        if (_branchesLoading) const LinearProgressIndicator(),
        DropdownButtonFormField<int>(
          key: ValueKey('branch-${widget.slug}-$_selectedBranchId'),
          initialValue: _selectedBranchId,
          isExpanded: true,
          decoration: const InputDecoration(
            labelText: 'Sucursal',
            prefixIcon: Icon(Icons.store_mall_directory_outlined),
          ),
          items: [
            const DropdownMenuItem(
              value: 0,
              child: Text('Todas las sucursales'),
            ),
            ..._branches.map(
              (b) => DropdownMenuItem<int>(
                value: b.id,
                child: Text(b.name, overflow: TextOverflow.ellipsis),
              ),
            ),
          ],
          onChanged: _branchesLoading
              ? null
              : (id) {
                  if (id == null) return;
                  setState(() => _selectedBranchId = id);
                },
        ),
        if (_selectedBranchId != 0) ...[
          const SizedBox(height: 7),
          const Text(
            'La disponibilidad se consultará para esta sucursal. '
            'La compra se valida en el servidor.',
            style: TextStyle(fontSize: 11, color: Color(0xFF527359)),
          ),
        ],
        if (_branchesError) ...[
          const SizedBox(height: 8),
          Row(
            children: [
              const Expanded(
                child: Text(
                  'No se pudieron cargar las sucursales.',
                  style: TextStyle(fontSize: 11),
                ),
              ),
              TextButton(
                onPressed: _loadPublicBranches,
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ],
      ],
    ),
  );

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
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => StorefrontDetailPage(
          key: ValueKey('${widget.slug}/${item.slug}'),
          tienda: widget.slug,
          slug: item.slug,
          repository: _repository,
          api: _api,
          controller: widget.controller,
          selectedBranchId: _selectedBranchId == 0 ? null : _selectedBranchId,
          onCompare: _addCompare,
          onRecommendations: _openRecommendations,
          onPurchase: _openPurchase,
          onTryOn: (variantId) => _openTryOn(item.slug, variantId),
          onAlerts: _openAlert,
          onLoginRequired: () {
            Navigator.of(context).popUntil((route) => route.isFirst);
            if (!widget.controller.signedIn) {
              setState(() => _tab = 4);
              notice(
                context,
                'Inicia sesión como Cliente para guardar deseos.',
              );
            } else {
              notice(
                context,
                'Solo una cuenta de Cliente puede guardar deseos.',
              );
            }
          },
        ),
      ),
    );
  }

  void _openTryOn(String productSlug, int variantId) {
    final catalogApi = CatalogApi(widget.controller.api.config);
    Navigator.of(context)
        .push(
          MaterialPageRoute<void>(
            builder: (_) => GarmentPage(
              store: Store(slug: widget.slug, name: widget.storeName),
              slug: productSlug,
              api: catalogApi,
              initialVariantId: variantId,
            ),
          ),
        )
        .whenComplete(catalogApi.dispose);
  }

  void _openPurchase(
    StoreProduct product,
    StoreVariant variant,
    List<StoreStock> stocks,
  ) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MobileCheckoutPage(
          tienda: widget.slug,
          product: product,
          variant: variant,
          knownStocks: stocks,
          preferredBranchId: _selectedBranchId == 0 ? null : _selectedBranchId,
          controller: widget.controller,
        ),
      ),
    );
  }

  void _openAlert(
    StoreProduct product,
    StoreVariant variant,
    List<StoreStock> stocks,
  ) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MobileAlertsPage(
          tienda: widget.slug,
          session: widget.controller,
          product: product,
          variant: variant,
          stock: stocks,
        ),
      ),
    );
  }

  void _openReviews() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            MobileReviewsPage(tienda: widget.slug, session: widget.controller),
      ),
    );
  }

  void _openAlertsList() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            MobileAlertsPage(tienda: widget.slug, session: widget.controller),
      ),
    );
  }

  void _openRecommendations([String? slug]) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          appBar: AppBar(title: const Text('Prendas para ti')),
          body: StorefrontRecommendationsPage(
            tienda: widget.slug,
            api: _api,
            session: widget.controller,
            reference: slug,
            onOpen: _openDetail,
            onCompare: _addCompare,
            isSelected: _selected,
          ),
        ),
      ),
    );
  }

  void _openStaffLogin() {
    if (widget.controller.busy || widget.controller.signedIn) return;
    setState(() {
      _showStaffLogin = true;
      _tab = 4;
    });
  }

  Widget _account() => SingleChildScrollView(
    padding: const EdgeInsets.all(16),
    child: widget.controller.signedIn
        ? AccountPage(controller: widget.controller)
        : Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!_showStaffLogin) ...[
                OutlinedButton.icon(
                  key: const ValueKey('storefront-administrative-access'),
                  onPressed: widget.controller.busy ? null : _openStaffLogin,
                  icon: const Icon(Icons.admin_panel_settings_outlined),
                  label: const Text('Acceso administrativo'),
                ),
                const SizedBox(height: 12),
              ],
              AccessPage(
                key: ValueKey(
                  'access-${_showStaffLogin ? 'staff' : 'customer'}',
                ),
                controller: widget.controller,
                startWithStaff: _showStaffLogin,
                onLeaveStaff: () => setState(() => _showStaffLogin = false),
              ),
            ],
          ),
  );

  @override
  Widget build(BuildContext context) {
    final isCustomer = widget.controller.isCustomer;
    final token = widget.controller.customerToken;
    final hasAccess =
        isCustomer && token != null && !widget.controller.offlineMode;
    final accountKey = widget.controller.account?.id ?? 0;

    Widget body;
    switch (_tab) {
      case 0:
      case 1:
        body = StorefrontCatalogPage(
          key: ValueKey('${widget.slug}/catalog/$_tab'),
          tienda: widget.slug,
          repository: _repository,
          onOpen: _openDetail,
          onCompare: _addCompare,
          isSelected: _selected,
          home: _tab == 0,
          scrollHeader: _branchSelector(),
        );
        break;
      case 2:
        body = hasAccess
            ? StorefrontWishlistPage(
                key: ValueKey('wishes/${widget.slug}/$accountKey'),
                tienda: widget.slug,
                api: _api,
                session: widget.controller,
                onOpen: _openDetail,
              )
            : StorefrontMessage(
                message: isCustomer && widget.controller.offlineMode
                    ? 'La lista de deseos requiere conexión. No se realizarán cambios sin confirmar.'
                    : 'Inicia sesión como Cliente de esta tienda para consultar tus deseos.',
                retry: isCustomer ? null : () => setState(() => _tab = 4),
              );
        break;
      case 3:
        body = StorefrontComparisonPage(
          tienda: widget.slug,
          api: _api,
          selected: List.unmodifiable(_compare),
          onRemove: _removeCompare,
          onOpen: _openDetail,
        );
        break;
      default:
        body = _account();
        break;
    }

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'VN · VestiNova',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            Text(widget.storeName, style: const TextStyle(fontSize: 12)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Recomendaciones',
            onPressed: () => _openRecommendations(),
            icon: const Icon(Icons.auto_awesome_outlined),
          ),
          PopupMenuButton<String>(
            tooltip: 'Compras, valoraciones y avisos',
            onSelected: (action) {
              if (action == 'reviews') _openReviews();
              if (action == 'alerts') _openAlertsList();
              if (action == 'reservations') setState(() => _tab = 4);
              if (action == 'staff') _openStaffLogin();
            },
            itemBuilder: (_) => [
              const PopupMenuItem(
                value: 'reviews',
                child: Text('Mis compras y valoraciones · CU25'),
              ),
              const PopupMenuItem(
                value: 'alerts',
                child: Text('Mis avisos · CU26'),
              ),
              const PopupMenuItem(
                value: 'reservations',
                child: Text('Reservas offline · CU10'),
              ),
              if (!widget.controller.signedIn)
                const PopupMenuItem(
                  value: 'staff',
                  child: Text('Acceso administrativo'),
                ),
            ],
          ),
          if (!widget.controller.signedIn)
            IconButton(
              tooltip: 'Cambiar tienda',
              onPressed: widget.controller.leaveStore,
              icon: const Icon(Icons.store_mall_directory_outlined),
            ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (widget.controller.busy) const LinearProgressIndicator(),
            if (widget.controller.error != null)
              Card(
                color: const Color(0xFFFFE9E3),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Text(widget.controller.error!),
                ),
              ),
            if (widget.controller.notice != null)
              Card(
                color: const Color(0xFFE0EFE6),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Text(widget.controller.notice!),
                ),
              ),
            Expanded(child: body),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        height: 75,
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Inicio',
          ),
          NavigationDestination(
            icon: Icon(Icons.grid_view_outlined),
            label: 'Catálogo',
          ),
          NavigationDestination(
            icon: Icon(Icons.favorite_border),
            label: 'Deseos',
          ),
          NavigationDestination(
            icon: Icon(Icons.compare_arrows),
            label: 'Comparar',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Cuenta',
          ),
        ],
      ),
    );
  }
}
