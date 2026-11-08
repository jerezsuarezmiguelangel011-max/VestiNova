import 'package:flutter/material.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';
import 'reservation_mobile_service.dart';
import 'reservation_sqlite.dart';

/// CU10: catálogo conocido y bandeja offline persistente por tienda y cliente.
class CustomerReservationsPage extends StatefulWidget {
  const CustomerReservationsPage({super.key, required this.controller});
  final SessionController controller;

  @override
  State<CustomerReservationsPage> createState() => _CustomerReservationsPageState();
}

class _CustomerReservationsPageState extends State<CustomerReservationsPage>
    with WidgetsBindingObserver {
  late final ReservationSqlite _store;
  late final MobileReservationService _service;
  List<LocalCatalogVariant> _variants = const [];
  List<LocalReservation> _queue = const [];
  List<Map<String,dynamic>> _central = const [];
  String? _centralError;
  String? _selectedVariant;
  int _quantity = 1;
  int? _policyHours;
  bool _busy = false;
  String? _message;
  String? _error;

  CustomerAccount? get _customer {
    final account = widget.controller.account;
    return account is CustomerAccount ? account : null;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _store = ReservationSqlite();
    _service = MobileReservationService(widget.controller.api.config, _store);
    _refresh();
    _loadCentral();
  }

  @override
  void didUpdateWidget(covariant CustomerReservationsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      _refresh();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && widget.controller.customerToken != null) {
      _sync();
    }
  }

  Future<void> _refresh() async {
    final account = _customer;
    if (account == null) return;
    try {
      final store = account.store.slug;
      final variants = await _store.catalog(store);
      final queue = await _store.list(store, account.id);
      final hours = await _store.policy(store);
      if (!mounted || _customer?.id != account.id || _customer?.store.slug != store) return;
      setState(() {
        _variants = variants;
        _queue = queue;
        _policyHours = hours;
        if (_selectedVariant != null && !_variants.any((v) => '${v.branchId}:${v.variantId}' == _selectedVariant)) {
          _selectedVariant = null;
        }
      });
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo consultar SQLite. Las reservas existentes no fueron eliminadas.');
    }
  }

  Future<void> _loadCentral() async {
    final account = _customer;
    final token = widget.controller.customerToken;
    if (account == null || token == null) return;
    try {
      final entries = await _service.listCentral(account.store.slug, token);
      if (mounted && _customer?.id == account.id) {
        setState(() { _central = entries; _centralError = null; });
      }
    } catch (_) {
      if (mounted) setState(() =>
        _centralError = 'Sin conexión: las reservas centrales no están actualizadas.');
    }
  }

  Future<void> _cancelCentral(String id) async {
    final account = _customer;
    final token = widget.controller.customerToken;
    if (_busy || account == null || token == null) return;
    setState(() { _busy = true; _error = null; _message = null; });
    try {
      await _service.cancelCentral(account.store.slug, token, id);
      await _loadCentral();
      if (mounted) setState(() => _message =
        'Cancelación confirmada por el servidor. El compromiso de stock se liberó.');
    } catch (_) {
      if (mounted) setState(() => _error =
        'No se confirmó la cancelación. Verifica el estado central.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _download() async {
    final account = _customer;
    if (_busy || account == null) return;
    setState(() { _busy = true; _error = null; _message = null; });
    try {
      final count = await _service.download(account.store.slug);
      await _refresh();
      if (mounted) setState(() => _message = '$count opción(es) disponibles guardadas en SQLite. Los saldos son referenciales.');
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo descargar la información. Se conserva la copia anterior.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _register() async {
    final account = _customer;
    final selected = _variants.where((v) => '${v.branchId}:${v.variantId}' == _selectedVariant).firstOrNull;
    if (_busy || account == null || selected == null) {
      setState(() => _error = 'Selecciona una prenda descargada.');
      return;
    }
    setState(() { _busy = true; _error = null; _message = null; });
    try {
      final saved = await _store.enqueue(
        store: account.store.slug, customerId: account.id,
        variant: selected, quantity: _quantity,
      );
      await _refresh();
      if (mounted) setState(() => _message = 'Solicitud local ${saved.id} guardada. No compromete inventario hasta la confirmación central.');
    } catch (_) {
      if (mounted) setState(() => _error = 'Error al guardar en SQLite. Verifica el almacenamiento del dispositivo.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sync() async {
    final account = _customer;
    final token = widget.controller.customerToken;
    if (_busy || account == null || token == null) return;
    setState(() { _busy = true; _error = null; _message = null; });
    try {
      await _service.synchronize(account.store.slug, account.id, token);
      await _refresh();
      await _loadCentral();
      if (mounted) setState(() => _message = 'Sincronización revisada. Verifica el estado de cada solicitud.');
    } catch (_) {
      if (mounted) setState(() => _error = 'No se completó la sincronización. Las operaciones siguen en SQLite.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _retry(LocalReservation row) async {
    if (_busy) return;
    try {
      await _store.retry(row);
      await _sync();
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo recuperar el reintento.');
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _service.close();
    _store.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final account = _customer;
    if (account == null) return const SizedBox.shrink();
    final knownAt = _variants.isNotEmpty ? _variants.first.downloadedAt : null;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SizedBox(height: 24),
      Text('Reservas de prendas · CU10', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 10),
      const Text('Las solicitudes registradas sin Internet se guardan en SQLite. '
          'Solo el servidor puede confirmar y comprometer las existencias.'),
      const SizedBox(height: 12),
      if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
      if (_message != null) Text(_message!, style: const TextStyle(color: Color(0xFF12644E))),
      if (_busy) const LinearProgressIndicator(),
      const SizedBox(height: 15),
      OutlinedButton.icon(
        onPressed: _busy ? null : _download,
        icon: const Icon(Icons.download_outlined),
        label: const Text('Descargar catálogo para reservas offline'),
      ),
      if (knownAt != null) Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text('Copia local: $knownAt. Existencias conocidas, no garantizadas.',
          style: Theme.of(context).textTheme.bodySmall),
      ),
      const SizedBox(height: 14),
      DropdownButtonFormField<String>(
        isExpanded: true,
        initialValue: _selectedVariant,
        decoration: const InputDecoration(labelText: 'Prenda, variante y sucursal'),
        items: _variants.map((v) => DropdownMenuItem<String>(
          value: '${v.branchId}:${v.variantId}', child: Text(v.label, overflow: TextOverflow.ellipsis),
        )).toList(growable: false),
        onChanged: _busy ? null : (id) => setState(() => _selectedVariant = id),
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<int>(
        initialValue: 1,
        decoration: const InputDecoration(labelText: 'Cantidad'),
        items: [1, 2, 3, 4, 5].map((qty) =>
          DropdownMenuItem(value: qty, child: Text('$qty unidad(es)'))).toList(),
        onChanged: _busy ? null : (qty) => setState(() => _quantity = qty ?? 1),
      ),
      if (_policyHours != null) Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Text('Vigencia prevista: $_policyHours horas desde la confirmación del servidor. '
            'La política conocida se revalida al sincronizar.'),
      ),
      const SizedBox(height: 14),
      FilledButton.icon(
        onPressed: _busy || _selectedVariant == null ? null : _register,
        icon: const Icon(Icons.bookmark_add_outlined),
        label: const Text('Guardar reserva local pendiente'),
      ),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        onPressed: _busy || widget.controller.customerToken == null ? null : _sync,
        icon: const Icon(Icons.sync),
        label: const Text('Sincronizar con servidor'),
      ),
      const SizedBox(height: 24),
      Text('Reservas confirmadas en el servidor',
        style: Theme.of(context).textTheme.titleLarge),
      OutlinedButton(
        onPressed: _busy ? null : _loadCentral,
        child: const Text('Actualizar reservas centrales'),
      ),
      if (_centralError != null) Text(_centralError!,
        style: const TextStyle(color: Colors.deepOrange)),
      if (_central.isEmpty)
        const Text('No hay reservas centrales verificadas en esta sesión.'),
      for (final row in _central) Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Código: ' + (row['codigo']?.toString() ?? '')),
            Text('Estado: ' + (row['estado']?.toString() ?? 'SIN VERIFICAR')),
            Text('Vence: ' + (row['vence_en']?.toString() ?? '')),
            if (row['estado'] == 'CONFIRMADA')
              TextButton(
                onPressed: _busy ? null : () => _cancelCentral(row['id'] as String),
                child: const Text('Cancelar reserva central'),
              ),
          ]),
        ),
      ),
      const SizedBox(height: 24),
      Text('Reservas guardadas en este dispositivo',
        style: Theme.of(context).textTheme.titleLarge),
      if (_queue.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Text('No tienes reservas locales para esta cuenta.'),
        ),
      ..._queue.map((row) => Card(
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(row.label, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 6),
            Text('Estado: ${row.state} · Cantidad: ${row.quantity}'),
            SelectableText('UUID: ${row.id}', style: Theme.of(context).textTheme.bodySmall),
            if (row.resultCode != null) SelectableText('Código central: ${row.resultCode}'),
            if (row.expiresAt != null) Text('Vence: ${row.expiresAt}'),
            if (row.message != null) Text(row.message!),
            if (row.state == 'ERROR' || row.state == 'REQUIERE_ACCESO')
              TextButton(onPressed: _busy ? null : () => _retry(row),
                child: const Text('Reintentar con el mismo UUID')),
            if (row.state == 'CONFLICTO' || row.state == 'RECHAZADA')
              const Text('No reservada: requiere revisión; el registro se conserva.',
                style: TextStyle(color: Colors.deepOrange)),
          ]),
        ),
      )),
    ]);
  }
}
