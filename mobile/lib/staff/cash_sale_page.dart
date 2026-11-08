import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';
import 'cash_api.dart';
import 'cash_models.dart';
import 'cash_store.dart';
import 'cash_sync.dart';

/// CU15: venta de caja con catálogo local y comprobante central al sincronizar.
class StaffCashSalePage extends StatefulWidget {
  const StaffCashSalePage({super.key, required this.session, required this.staffContext});
  final SessionController session;
  final StaffContext staffContext;

  @override
  State<StaffCashSalePage> createState() => _StaffCashSalePageState();
}

class _StaffCashSalePageState extends State<StaffCashSalePage> with WidgetsBindingObserver {
  late final StaffCashApi api;
  late final StaffCashStore store;
  late final StaffCashSync sync;
  final received = TextEditingController();
  StreamSubscription<List<ConnectivityResult>>? _connectivity;
  bool _wasOffline = false;
  int? branchId, variantId;
  int quantity = 1;
  bool offline = false, cashCollected = false, delivered = false, busy = false;
  String? message, error;
  List<CashCatalogItem> catalog = [];
  List<CashLocalSale> localSales = [];
  List<Map<String, dynamic>> centralSales = [];
  final Map<int, int> quantities = {};

  int get companyId => widget.staffContext.company.id;
  int get staffId => widget.session.account!.id;
  String? get token => widget.session.staffToken;
  int get total => quantities.entries.fold<int>(0, (sum, e) {
    final found = catalog.where((x) => x.variantId == e.key);
    return found.isEmpty ? sum : sum + found.first.cents * e.value;
  });

  @override
  void initState() {
    super.initState();
    api = StaffCashApi(widget.session.api.config);
    store = StaffCashStore();
    sync = StaffCashSync(store: store, api: api);
    branchId = widget.staffContext.branches.isEmpty
        ? null : widget.staffContext.branches.first.id;
    WidgetsBinding.instance.addObserver(this);
    _connectivity = Connectivity().onConnectivityChanged.listen(
      (events) {
        final offline = events.contains(ConnectivityResult.none);
        if (_wasOffline && !offline && mounted && !busy) {
          unawaited(_synchronize());
        }
        _wasOffline = offline;
      },
      onError: (Object _) {},
    );
    if (branchId != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _loadLocal();
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !busy && branchId != null) {
      unawaited(_synchronize());
    }
  }

  Future<void> _loadLocal() async {
    final branch = branchId;
    if (branch == null) return;
    try {
      final items = await store.catalog(companyId, staffId, branch);
      final rows = await store.list(companyId, staffId, branch);
      if (mounted && branch == branchId) {
        setState(() {
          catalog = items;
          localSales = rows;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = 'Error del almacenamiento local: $e');
    }
  }

  Future<void> _download() async {
    final branch = branchId, access = token;
    if (branch == null || access == null || busy) return;
    setState(() { busy = true; error = null; message = null; });
    try {
      final items = await api.catalog(access, companyId, branch);
      await store.replaceCatalog(companyId, staffId, branch, items);
      quantities.clear();
      variantId = null;
      await _loadLocal();
      if (mounted) setState(() => message = '${items.length} variantes descargadas. Los precios pueden cambiar.');
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void _addLine() {
    final id = variantId;
    if (id == null || catalog.every((x) => x.variantId != id)) return;
    final next = (quantities[id] ?? 0) + quantity;
    if (next > 100 || (quantities.length >= 30 && !quantities.containsKey(id))) {
      setState(() => error = 'Máximo 30 variantes y 100 unidades por variante.');
      return;
    }
    setState(() {
      quantities[id] = next;
      variantId = null;
      quantity = 1;
      error = null;
    });
  }

  Future<void> _register() async {
    final branch = branchId;
    if (branch == null || quantities.isEmpty || busy) return;
    if (widget.session.context?.company.id != companyId || token == null) {
      setState(() => error = 'Vuelve a iniciar sesión y elige la empresa autorizada.');
      return;
    }
    if (offline && !cashCollected) {
      setState(() => error = 'Confirma el efectivo realmente recibido para registrar una venta offline.');
      return;
    }
    int cash;
    try {
      cash = cashCents(received.text);
    } on FormatException catch (e) {
      setState(() => error = e.message);
      return;
    }
    if (cash < total) {
      setState(() => error = 'El efectivo no cubre el total de Bs ${cashMoney(total)}.');
      return;
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final payload = <String, dynamic>{
      'id': const Uuid().v4(),
      'sucursal_id': branch,
      'cliente_id': null,
      'lineas': quantities.entries.map((e) {
        final item = catalog.firstWhere((x) => x.variantId == e.key);
        return {
          'variante_id': e.key,
          'cantidad': e.value,
          'precio_unitario': item.price,
        };
      }).toList(growable: false),
      'efectivo': cashMoney(cash),
      'origen': offline ? 'MOVIL_OFFLINE' : 'EN_LINEA',
      'efectivo_cobrado': offline && cashCollected,
      'entrega_local': offline && delivered,
      'creada_local_en': offline ? now : null,
    };
    setState(() { busy = true; error = null; message = null; });
    try {
      await store.enqueue(companyId, staffId, branch, payload);
      quantities.clear();
      received.clear();
      final savedOffline = offline;
      if (!savedOffline) {
        await sync.synchronize(token: token!, companyId: companyId, staffId: staffId, branchId: branch);
      }
      await _loadLocal();
      if (mounted) {
        setState(() => message = savedOffline
            ? 'Venta local PENDIENTE. Sin comprobante central ni descuento de stock. Efectivo documentado.'
            : 'Operación registrada localmente. Revisa su estado y el comprobante central.');
      }
    } catch (e) {
      if (mounted) setState(() => error = 'No se pudo conservar la venta: $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _synchronize() async {
    final branch = branchId, access = token;
    if (branch == null || access == null || busy || widget.session.context?.company.id != companyId) return;
    setState(() { busy = true; error = null; message = null; });
    try {
      final result = await sync.synchronize(
        token: access, companyId: companyId, staffId: staffId, branchId: branch);
      await _loadLocal();
      if (mounted) setState(() => message =
        'Sincronización: ${result.confirmed} confirmadas, ${result.conflicts} conflictos, ${result.pending} por verificar.');
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _refreshCentral() async {
    final branch = branchId, access = token;
    if (branch == null || access == null || busy) return;
    setState(() { busy = true; error = null; });
    try {
      final sales = await api.sales(access, companyId, branch);
      if (mounted && branch == branchId) setState(() => centralSales = sales);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void _switchBranch(int? id) {
    if (id == null || id == branchId) return;
    setState(() {
      branchId = id;
      catalog = [];
      localSales = [];
      centralSales = [];
      variantId = null;
      quantities.clear();
      message = null;
      error = null;
    });
    _loadLocal();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivity?.cancel();
    received.dispose();
    api.close();
    unawaited(store.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final branch = branchId;
    final allowed = const {'CAJERO', 'ENCARGADO_SUCURSAL'}.contains(widget.staffContext.company.role);
    if (!allowed || branch == null || token == null) {
      return Scaffold(appBar: AppBar(title: const Text('CU15 · Caja')),
        body: const Center(child: Text('Selecciona una sucursal con rol Cajero o Encargado autorizado.')));
    }
    return Scaffold(
      appBar: AppBar(title: const Text('CU15 · Venta en caja')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Ventas en efectivo, sin Stripe. Solo la confirmación del backend crea comprobante y descuenta inventario.'),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: ValueKey(branch),
          initialValue: branch, isExpanded: true,
          decoration: const InputDecoration(labelText: 'Sucursal autorizada'),
          items: widget.staffContext.branches.map((b) =>
            DropdownMenuItem(value: b.id, child: Text(b.name, overflow: TextOverflow.ellipsis))).toList(),
          onChanged: busy ? null : _switchBranch,
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: busy ? null : _download,
          icon: const Icon(Icons.download_outlined),
          label: const Text('Descargar catálogo de caja (para offline)')),
        Text('Catálogo local: ${catalog.length} variantes. Las existencias se verificarán al sincronizar.'),
        if (busy) const LinearProgressIndicator(),
        if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
        if (message != null) Text(message!, style: const TextStyle(color: Color(0xFF12644E))),
        const Divider(height: 28),
        Text('Registrar artículos', style: Theme.of(context).textTheme.titleMedium),
        if (catalog.isEmpty) const Text('Descarga el catálogo con conexión antes de vender offline.'),
        DropdownButtonFormField<int>(
          key: ValueKey('producto:$branch:${catalog.length}'),
          initialValue: variantId, isExpanded: true,
          decoration: const InputDecoration(labelText: 'Variante de prenda'),
          items: catalog.map((v) => DropdownMenuItem(
            value: v.variantId, child: Text(v.label, maxLines: 1, overflow: TextOverflow.ellipsis))).toList(),
          onChanged: busy ? null : (value) => setState(() => variantId = value),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<int>(
          initialValue: quantity,
          decoration: const InputDecoration(labelText: 'Unidades'),
          items: List.generate(10, (i) => DropdownMenuItem(value: i + 1, child: Text('${i + 1}'))),
          onChanged: busy ? null : (v) => setState(() => quantity = v ?? 1),
        ),
        OutlinedButton.icon(onPressed: busy || variantId == null ? null : _addLine,
          icon: const Icon(Icons.add), label: const Text('Añadir a la venta')),
        for (final entry in quantities.entries)
          ListTile(
            dense: true,
            title: Text(catalog.firstWhere((v) => v.variantId == entry.key).name),
            subtitle: Text('${entry.value} u. × Bs ${catalog.firstWhere((v) => v.variantId == entry.key).price}'),
            trailing: IconButton(tooltip: 'Retirar línea', icon: const Icon(Icons.close),
              onPressed: busy ? null : () => setState(() => quantities.remove(entry.key))),
          ),
        Text('Total calculado: Bs ${cashMoney(total)}',
          style: Theme.of(context).textTheme.titleLarge),
        TextField(controller: received,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Efectivo recibido (Bs)', hintText: '100.00')),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: offline,
          onChanged: busy ? null : (v) => setState(() {
            offline = v; if (!v) { cashCollected = false; delivered = false; }
          }),
          title: const Text('Registrar venta sin conexión'),
          subtitle: const Text('Guardar en SQLite, pendiente de validación central.'),
        ),
        if (offline) ...[
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: cashCollected,
            onChanged: busy ? null : (v) => setState(() {
              cashCollected = v ?? false;
              if (!cashCollected) delivered = false;
            }),
            title: const Text('Confirmo que recibí este efectivo realmente'),
          ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: delivered,
            onChanged: busy || !cashCollected ? null : (v) => setState(() => delivered = v ?? false),
            title: const Text('La prenda también fue entregada localmente'),
          ),
          const Text('Aviso: un conflicto posterior requiere conciliación documentada por Encargado; no se modifica el cobro local.'),
        ],
        FilledButton.icon(
          onPressed: busy || quantities.isEmpty || total <= 0 ? null : _register,
          icon: const Icon(Icons.point_of_sale),
          label: Text(offline ? 'Guardar venta local PENDIENTE' : 'Registrar y sincronizar venta'),
        ),
        const Divider(height: 30),
        Text('Solicitudes locales', style: Theme.of(context).textTheme.titleLarge),
        OutlinedButton.icon(onPressed: busy ? null : _synchronize,
          icon: const Icon(Icons.sync), label: const Text('Sincronizar pendientes (mismo UUID)')),
        if (localSales.isEmpty) const Text('No hay ventas registradas localmente en esta cuenta/sucursal.'),
        for (final sale in localSales)
          Card(child: ListTile(
            title: Text('${sale.state} · Bs ${sale.total}'),
            subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SelectableText('UUID: ${sale.id}'),
              Text(sale.message),
              if (sale.code != null) SelectableText('Comprobante: ${sale.code}'),
              if (sale.incidentId != null) SelectableText('Conflicto CU13: ${sale.incidentId}'),
            ]),
          )),
        const Divider(height: 30),
        Text('Ventas confirmadas en el servidor', style: Theme.of(context).textTheme.titleLarge),
        OutlinedButton.icon(onPressed: busy ? null : _refreshCentral,
          icon: const Icon(Icons.refresh), label: const Text('Actualizar comprobantes centrales')),
        for (final item in centralSales)
          Card(child: ListTile(
            title: Text('${item['codigo'] ?? 'Comprobante'} · Bs ${item['total'] ?? ''}'),
            subtitle: SelectableText('Venta ${item['id']} · cambio Bs ${item['cambio'] ?? ''}'),
          )),
      ]),
    );
  }
}
