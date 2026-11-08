import 'package:flutter/material.dart';
import '../auth/session_controller.dart';
import '../storefront/storefront_models.dart';
import '../storefront/storefront_widgets.dart';
import 'mobile_commerce_api.dart';
import 'native_push_service.dart';

/// CU26: suscripción a una variante agotada en una sucursal concreta.
class MobileAlertsPage extends StatefulWidget {
  const MobileAlertsPage({super.key, required this.tienda,
    required this.session, this.product, this.variant, this.stock = const []});
  final String tienda;
  final SessionController session;
  final StoreProduct? product;
  final StoreVariant? variant;
  final List<StoreStock> stock;
  @override
  State<MobileAlertsPage> createState() => _MobileAlertsPageState();
}

class _MobileAlertsPageState extends State<MobileAlertsPage> {
  late final MobileCommerceApi api;
  List<Map<String,dynamic>> alerts = [];
  Map<String,dynamic> config = {};
  int? selectedBranch;
  bool busy = false;
  String? error, success;

  @override
  void initState() {
    super.initState();
    api = MobileCommerceApi(widget.session.api.config);
    _load();
  }

  Future<void> _load() async {
    final token = widget.session.customerToken;
    if (token == null) return;
    setState(() { busy = true; error = null; });
    try {
      final a = await api.alerts(widget.tienda, token);
      final c = await api.alertsConfig(widget.tienda, token);
      if (mounted) setState(() {
        alerts = a; config = c;
        final outOfStock = widget.stock.where(
          (e) => e.variantId == widget.variant?.id &&
            e.status == 'AGOTADO' && e.branchId != null).toList();
        if (selectedBranch == null && outOfStock.isNotEmpty) {
          selectedBranch = outOfStock.first.branchId;
        }
      });
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    if (busy) return;
    setState(() { busy = true; error = null; success = null; });
    try {
      await action();
      await _load();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _subscribe() async => _run(() async {
    final token = widget.session.customerToken;
    if (token == null || widget.variant == null || selectedBranch == null) {
      throw StateError('Selecciona una variante agotada y una sucursal.');
    }
    if (config['movil_habilitado'] != true) {
      throw StateError('El servidor todavía no tiene credenciales FCM para Android.');
    }
    await NativePushService.register(api: api, tienda: widget.tienda, token: token);
    await api.subscribeAlert(widget.tienda, token, widget.variant!.id, selectedBranch!);
    if (mounted) setState(() =>
      success = 'Alerta registrada: se avisará por FCM tras una reposición central confirmada.');
  });

  Future<void> _cancel(int id) async => _run(() async {
    final token = widget.session.customerToken;
    if (token == null) throw StateError('Inicia sesión.');
    await api.cancelAlert(widget.tienda, token, id);
    if (mounted) setState(() => success = 'Alerta cancelada.');
  });

  @override
  void dispose() {
    api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final token = widget.session.customerToken;
    if (token == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('CU26 · Reposición')),
        body: const Center(child: Text('Inicia sesión como Cliente para gestionar alertas.')),
      );
    }
    final known = widget.stock.where((e) =>
      e.variantId == widget.variant?.id && e.branchId != null &&
      e.status == 'AGOTADO').toList();
    return Scaffold(
      appBar: AppBar(title: const Text('CU26 · Avisos de reposición')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Text('Avísame si vuelve el stock',
            style: Theme.of(context).textTheme.headlineSmall),
          const Text('Avisos informativos: no reservan prendas ni garantizan stock.'),
          if (busy) const LinearProgressIndicator(),
          if (error != null) StorefrontMessage(message: error!, retry: _load),
          if (success != null) Text(success!,
            style: const TextStyle(color: Colors.teal)),
          const SizedBox(height: 12),
          if (!NativePushService.configured)
            const Text('Firebase no está configurado en esta compilación. '
              'Para recibir push Android se requiere preparar FCM.'),
          if (config['movil_habilitado'] != true)
            const Text('El servidor aún no dispone del canal FCM móvil. '
              'No se afirmará que el aviso puede llegar al teléfono.'),
          if (widget.product != null && widget.variant != null) ...[
            Text(widget.product!.name + ' · ' + widget.variant!.label,
              style: Theme.of(context).textTheme.titleMedium),
            if (known.isEmpty)
              const Text('No existe una sucursal con agotamiento verificado '
                'para esta variante. No se puede solicitar un aviso.'),
            if (known.isNotEmpty)
              DropdownButtonFormField<int>(
                initialValue: selectedBranch,
                decoration: const InputDecoration(labelText: 'Sucursal agotada'),
                items: known.map((v) => DropdownMenuItem(
                  value: v.branchId, child: Text(v.branch))).toList(),
                onChanged: (v) => setState(() => selectedBranch = v),
              ),
            const SizedBox(height: 12),
            FilledButton.icon(
              icon: const Icon(Icons.notifications_active_outlined),
              onPressed: busy || selectedBranch == null ||
                !NativePushService.configured ||
                config['movil_habilitado'] != true ? null : _subscribe,
              label: const Text('Avisarme cuando haya stock'),
            ),
          ] else
            const Text('Para crear una alerta, abre una prenda agotada desde el catálogo.'),
          const Divider(height: 38),
          Text('Mis alertas activas', style: Theme.of(context).textTheme.titleMedium),
          if (alerts.isEmpty) const Text('No tienes alertas activas.'),
          for (final alert in alerts)
            ListTile(
              title: Text(alert['producto_nombre']?.toString() ?? 'Prenda'),
              subtitle: Text((alert['talla']?.toString() ?? '') + ' · ' +
                (alert['color']?.toString() ?? '') + ' · ' +
                (alert['sucursal_nombre']?.toString() ?? 'Sucursal')),
              trailing: IconButton(
                tooltip: 'Cancelar aviso', icon: const Icon(Icons.close),
                onPressed: busy ? null : () => _cancel(alert['id'] as int),
              ),
            ),
        ]),
      ),
    );
  }
}
