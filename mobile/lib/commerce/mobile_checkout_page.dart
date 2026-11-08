import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';
import '../storefront/storefront_api.dart';
import '../storefront/storefront_models.dart';
import '../storefront/storefront_widgets.dart';
import 'mobile_commerce_api.dart';
import 'mobile_order_store.dart';

/// CU09: compra inmediata o solicitud offline; ambas se validan en FastAPI.
class MobileCheckoutPage extends StatefulWidget {
  const MobileCheckoutPage({super.key, required this.tienda, required this.product,
    required this.variant, required this.knownStocks, required this.controller});
  final String tienda;
  final StoreProduct product;
  final StoreVariant variant;
  final List<StoreStock> knownStocks;
  final SessionController controller;
  @override
  State<MobileCheckoutPage> createState() => _MobileCheckoutPageState();
}

class _MobileCheckoutPageState extends State<MobileCheckoutPage>
    with WidgetsBindingObserver {
  late final MobileCommerceApi api;
  late final MobileOrderStore store;
  bool busy = false, prepared = false, authorized = false;
  String? message, error, lastPurchaseId, lastCheckoutUrl;
  int? branchId;
  int quantity = 1;
  List<Map<String,dynamic>> branches = [];
  List<MobilePendingOrder> pending = [];

  CustomerAccount? get customer => widget.controller.account is CustomerAccount
      ? widget.controller.account as CustomerAccount : null;
  String? get token => widget.controller.customerToken;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    api = MobileCommerceApi(widget.controller.api.config);
    store = MobileOrderStore();
    _load();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _load();
    }
  }

  Future<void> _load() async {
    final person = customer;
    if (person == null) return;
    final stored = await store.wasPrepared(widget.tienda, person.id);
    final queue = await store.list(widget.tienda, person.id);
    if (!mounted) return;
    setState(() { prepared = stored; pending = queue; });
    try {
      final response = await api.branches(widget.tienda);
      if (mounted) setState(() {
        branches = response;
        if (branchId == null && response.isNotEmpty) {
          branchId = response.first['id'] as int;
        }
      });
    } catch (_) {
      // Se pueden guardar borradores sin conexión usando sucursales conocidas.
      if (branches.isEmpty && widget.knownStocks.isNotEmpty && mounted) {
        final lookup = <int,String>{};
        for (final stock in widget.knownStocks) {
          if (stock.branchId != null) lookup[stock.branchId!] = stock.branch;
        }
        setState(() {
          branches = lookup.entries.map((e) => <String,dynamic>{
            'id': e.key, 'nombre': e.value}).toList();
          if (branchId == null && branches.isNotEmpty) {
            branchId = branches.first['id'] as int;
          }
        });
      }
    }
  }

  Future<void> _run(Future<void> Function() fn) async {
    if (busy) return;
    setState(() { busy = true; error = null; message = null; });
    try {
      await fn();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _openStripe(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null || uri.scheme != 'https' ||
        !(uri.host == 'checkout.stripe.com' || uri.host.endsWith('.stripe.com'))) {
      throw const StorefrontException('Stripe devolvió un enlace no autorizado.');
    }
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      await Clipboard.setData(ClipboardData(text: url));
      throw const StorefrontException(
        'No se abrió Stripe; se copió el enlace para abrirlo en el navegador.');
    }
  }

  Future<void> _prepareCard() async => _run(() async {
    final t = token;
    if (t == null) throw const StorefrontException('Inicia sesión como Cliente.');
    final result = await api.prepareCard(widget.tienda, t);
    await _openStripe(result['checkout_url'] as String);
    if (mounted) setState(() => message =
      'Termina la preparación en Stripe y vuelve para verificar la tarjeta.');
  });

  Future<void> _checkCard() async => _run(() async {
    final t = token;
    final person = customer;
    if (t == null || person == null) throw const StorefrontException('Inicia sesión.');
    final result = await api.cardStatus(widget.tienda, t);
    final ready = result['preparado'] == true;
    await store.setPrepared(widget.tienda, person.id, ready);
    if (mounted) setState(() {
      prepared = ready;
      message = ready ? 'Tarjeta preparada en Stripe TEST (' +
        (result['marca']?.toString() ?? '') + ' ••••' +
        (result['ultimos4']?.toString() ?? '') + ').' :
        'Todavía no hay tarjeta preparada para futuros cobros.';
    });
  });

  int get amountCents {
    final cost = double.tryParse(widget.product.effectivePrice);
    return cost == null ? 0 : (cost * 100).round() * quantity;
  }

  Map<String,dynamic> get order {
    final id = const Uuid().v4();
    return {
      'id': id,
      'sucursal_id': branchId,
      'entrega': 'RETIRO',
      'direccion': '',
      'items': [{'producto_id': widget.product.id,
        'variante_id': widget.variant.id, 'cantidad': quantity}],
      'importe_aceptado_centavos': amountCents,
      'autoriza_cobro_diferido': true,
      'creado_local_en': DateTime.now().toUtc().toIso8601String(),
    };
  }

  void _verifyInput() {
    if (customer == null || token == null) {
      throw const StorefrontException('Debes iniciar sesión como Cliente.');
    }
    if (branchId == null) {
      throw const StorefrontException('Selecciona una sucursal conocida.');
    }
    if (amountCents < 1) {
      throw const StorefrontException('El importe no es válido.');
    }
  }

  Future<void> _online() async => _run(() async {
    _verifyInput();
    final payload = order;
    payload['origen_movil'] = true;
    payload.remove('importe_aceptado_centavos');
    payload.remove('autoriza_cobro_diferido');
    payload.remove('creado_local_en');
    final result = await api.onlineCheckout(widget.tienda, token!, payload);
    if (mounted) setState(() {
      lastPurchaseId = result['id'] as String;
      lastCheckoutUrl = result['checkout_url'] as String?;
      message = 'Pago aún NO confirmado. Termina Checkout y verifica el estado.';
    });
    if (lastCheckoutUrl != null) await _openStripe(lastCheckoutUrl!);
  });

  Future<void> _enqueue() async => _run(() async {
    _verifyInput();
    if (!prepared) throw const StorefrontException(
      'Prepara primero la tarjeta mediante Stripe, mientras tengas Internet.');
    if (!authorized) throw const StorefrontException(
      'Debes autorizar expresamente el cargo diferido.');
    await store.enqueue(widget.tienda, customer!.id, order);
    await _load();
    if (mounted) setState(() => message =
      'Solicitud en SQLite. No hay cobro ni reserva; se revisará al recuperar Internet.');
  });

  Future<void> _sync() async => _run(() async {
    final person = customer;
    final t = token;
    if (person == null || t == null) {
      throw const StorefrontException('Necesitas una sesión de Cliente válida.');
    }
    final queue = await store.list(widget.tienda, person.id);
    for (final item in queue.where((x) =>
        x.state == 'PENDIENTE' || x.state == 'PAGO_PENDIENTE')) {
      try {
        final result = await api.deferredCheckout(widget.tienda, t, item.payload);
        final state = result['estado']?.toString() ?? 'PAGO_PENDIENTE';
        await store.update(item.id, state, result['detalle']?.toString() ??
          'Consulta el estado: no se presume cobro por una respuesta ambigua.');
      } on StorefrontException catch (e) {
        if (e.network || e.status == 503) {
          await store.update(item.id, 'PENDIENTE',
            'Resultado no confirmado. Conservar el UUID y volver a consultar.');
          break;
        }
        await store.update(item.id, e.status == 409 ? 'CONFLICTO' : 'ERROR', e.message);
      }
    }
    await _load();
    if (mounted) setState(() => message =
      'Sincronización revisada. Solo CONFIRMADA acredita la compra.');
  });

  Future<void> _verifyPurchase() async => _run(() async {
    final id = lastPurchaseId;
    final t = token;
    if (id == null || t == null) return;
    final result = await api.checkoutStatus(widget.tienda, t, id, reconcile: true);
    if (mounted) setState(() => message =
      'Compra ' + id.substring(0, 8) + ': ' +
      (result['estado']?.toString() ?? 'SIN VERIFICAR') + '. ' +
      (result['detalle']?.toString() ?? ''));
  });

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    api.close();
    store.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CU09 · Comprar')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text(widget.product.name, style: Theme.of(context).textTheme.titleLarge),
        Text('Variante: ' + widget.variant.label),
        Text('Precio referencial: Bs ' + widget.product.effectivePrice),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: branchId, isExpanded: true,
          decoration: const InputDecoration(labelText: 'Sucursal de retiro'),
          items: branches.map((b) => DropdownMenuItem<int>(
            value: b['id'] as int, child: Text(b['nombre'] as String),
          )).toList(),
          onChanged: (v) => setState(() => branchId = v),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: quantity,
          decoration: const InputDecoration(labelText: 'Cantidad'),
          items: List.generate(5, (i) => DropdownMenuItem(
            value: i + 1, child: Text('' + (i + 1).toString() + ' unidad(es)'),
          )),
          onChanged: (v) => setState(() => quantity = v ?? 1),
        ),
        const SizedBox(height: 12),
        Text('Total de referencia: Bs ' +
          (amountCents / 100).toStringAsFixed(2),
          style: Theme.of(context).textTheme.titleMedium),
        const Text('El servidor revalida el stock y el precio antes de cobrar. '
          'Los pedidos sin conexión NO quedan pagados ni reservados.'),
        if (busy) const LinearProgressIndicator(),
        if (error != null) StorefrontMessage(message: error!),
        if (message != null) Text(message!,
          style: const TextStyle(color: Colors.teal)),
        const SizedBox(height: 18),
        FilledButton.icon(
          onPressed: busy ? null : _online,
          icon: const Icon(Icons.payment),
          label: const Text('Pagar online con Stripe TEST'),
        ),
        if (lastPurchaseId != null) OutlinedButton(
          onPressed: busy ? null : _verifyPurchase,
          child: const Text('Verificar pago y comprobante'),
        ),
        const Divider(height: 36),
        Text('Compra diferida sin Internet',
          style: Theme.of(context).textTheme.titleLarge),
        const Text('Primero guarda una tarjeta con autorización para futuros '
          'cobros en Stripe (requiere conexión). Después podrás guardar '
          'solicitudes en SQLite, sin guardar números de tarjeta.'),
        const SizedBox(height: 10),
        OutlinedButton(
          onPressed: busy ? null : _prepareCard,
          child: const Text('Preparar tarjeta con Stripe TEST'),
        ),
        OutlinedButton(
          onPressed: busy ? null : _checkCard,
          child: const Text('Verificar tarjeta autorizada'),
        ),
        Text(prepared ? 'Tarjeta previamente verificada para este cliente.' :
          'No hay una tarjeta verificada en este dispositivo.'),
        CheckboxListTile(
          title: const Text('Autorizo cobrar posteriormente este importe si '
            'el precio y el stock se mantienen.'),
          subtitle: const Text('Puedo revisar cada resultado. '
            'La solicitud local no garantiza la compra.'),
          value: authorized,
          onChanged: (v) => setState(() => authorized = v ?? false),
        ),
        FilledButton.tonal(
          onPressed: busy ? null : _enqueue,
          child: const Text('Guardar solicitud pendiente (SQLite)'),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          icon: const Icon(Icons.sync),
          onPressed: busy ? null : _sync,
          label: const Text('Sincronizar solicitudes pendientes'),
        ),
        for (final item in pending) ListTile(
          title: Text(item.id.substring(0, 8) + ' · ' + item.state),
          subtitle: Text(item.message),
        ),
      ]),
    );
  }
}
