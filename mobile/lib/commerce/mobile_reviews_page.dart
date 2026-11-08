import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import '../storefront/storefront_widgets.dart';
import 'mobile_commerce_api.dart';

/// CU16/CU25: historial completo y valoraciones limitadas a entregas verificadas.
class MobileReviewsPage extends StatefulWidget {
  const MobileReviewsPage({
    super.key,
    required this.tienda,
    required this.session,
  });
  final String tienda;
  final SessionController session;
  @override
  State<MobileReviewsPage> createState() => _MobileReviewsPageState();
}

class _MobileReviewsPageState extends State<MobileReviewsPage> {
  late final MobileCommerceApi api;
  bool busy = false;
  String? error, noticeText;
  List<Map<String, dynamic>> purchases = [], reviews = [];
  String? selectedPurchase;
  int? selectedProduct, selectedReviewId;
  int rating = 5;
  final comment = TextEditingController();

  @override
  void initState() {
    super.initState();
    api = MobileCommerceApi(widget.session.api.config);
    _load();
  }

  Future<void> _load() async {
    final token = widget.session.customerToken;
    if (token == null) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final history = await api.history(widget.tienda, token);
      final mine = await api.reviews(widget.tienda, token);
      if (mounted) {
        setState(() {
          purchases = history;
          reviews = mine;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  bool _entregada(Map<String, dynamic> compra) =>
      compra['estado'] == 'CONFIRMADA' &&
      compra['seguimiento_entrega'] == 'ENTREGADA';

  String _fecha(dynamic value) {
    final parsed = value is String ? DateTime.tryParse(value) : null;
    if (parsed == null) return 'Fecha no disponible';
    final local = parsed.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(local.day)}/${two(local.month)}/${local.year} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  String _importe(Map<String, dynamic> compra) =>
      'Bs ${compra['importe_total'] ?? '0.00'}';

  List<Map<String, dynamic>> get eligible {
    final result = <Map<String, dynamic>>[];
    for (final purchase in purchases) {
      if (!_entregada(purchase)) {
        continue;
      }
      for (final raw in (purchase['items'] as List? ?? [])) {
        final item = Map<String, dynamic>.from(raw as Map);
        result.add({
          'compra_id': purchase['id'],
          'producto_id': item['producto_id'],
          'nombre': item['nombre'],
        });
      }
    }
    return result;
  }

  void _select(Map<String, dynamic> item) {
    final compraId = item['compra_id'] as String;
    final productId = item['producto_id'] as int;
    Map<String, dynamic>? existing;
    for (final entry in reviews) {
      if (entry['compra_id'] == compraId && entry['producto_id'] == productId) {
        existing = entry;
        break;
      }
    }
    setState(() {
      selectedPurchase = compraId;
      selectedProduct = productId;
      selectedReviewId = existing?['id'] as int?;
      rating = existing?['puntuacion'] as int? ?? 5;
      comment.text = existing?['comentario'] as String? ?? '';
      noticeText = null;
    });
  }

  Future<void> _submit() async {
    final token = widget.session.customerToken;
    if (token == null || selectedPurchase == null || selectedProduct == null) {
      return;
    }
    if (comment.text.length > 1000) {
      setState(() => error = 'El comentario supera 1000 caracteres.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
      noticeText = null;
    });
    try {
      await api.publishReview(
        widget.tienda,
        token,
        purchaseId: selectedPurchase!,
        productId: selectedProduct!,
        rating: rating,
        comment: comment.text,
        reviewId: selectedReviewId,
      );
      if (mounted) {
        setState(() {
          noticeText = 'Valoración verificada guardada en el servidor.';
          selectedProduct = null;
          selectedPurchase = null;
        });
      }
      await _load();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    api.close();
    comment.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.session.customerToken == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('CU25 · Valoraciones')),
        body: const Center(
          child: Text('Inicia sesión como Cliente en Cuenta.'),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('CU25 · Valoraciones')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Mis compras',
              style: Theme.of(context).textTheme.headlineSmall),
            const Text(
              'Historial de compras confirmadas de tu cuenta en esta tienda. '
              'La confirmación del pago no significa que la prenda fue entregada.'),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: busy ? null : _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Actualizar historial'),
            ),
            if (busy) const LinearProgressIndicator(),
            if (error != null) StorefrontMessage(message: error!, retry: _load),
            if (noticeText != null)
              Text(noticeText!, style: const TextStyle(color: Colors.teal)),
            if (!busy && purchases.isEmpty && error == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('Aún no hay compras confirmadas en esta cuenta. '
                  'Si acabas de sincronizar una compra, vuelve y pulsa '
                  'Actualizar historial. Comprueba que sea la misma cuenta y tienda.'),
              ),
            for (final purchase in purchases)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Comprobante de compra',
                        style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 5),
                      SelectableText('N.º ${purchase['id']}',
                        style: Theme.of(context).textTheme.bodySmall),
                      Text('Fecha: ${_fecha(purchase['creado_en'])}'),
                      const SizedBox(height: 6),
                      Text(
                        purchase['estado'] == 'CONFIRMADA'
                            ? 'Pago / compra: CONFIRMADA'
                            : 'Estado: ${purchase['estado'] ?? 'NO VERIFICADO'}',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      Text(_entregada(purchase)
                          ? 'Entrega: ENTREGADA'
                          : 'Entrega o retiro: PENDIENTE de confirmación. '
                            'Consulta con la tienda antes de desplazarte.'),
                      const SizedBox(height: 8),
                      for (final raw in (purchase['items'] as List? ?? []))
                        Builder(builder: (context) {
                          final item = Map<String, dynamic>.from(raw as Map);
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 3),
                            child: Text(
                              '${item['nombre'] ?? 'Prenda'} · '
                              '${item['cantidad'] ?? 0} u. · '
                              'Bs ${item['subtotal'] ?? '0.00'}',
                            ),
                          );
                        }),
                      const SizedBox(height: 5),
                      Text('Total: ${_importe(purchase)}',
                        style: Theme.of(context).textTheme.titleMedium),
                      if (_entregada(purchase))
                        const Padding(
                          padding: EdgeInsets.only(top: 8),
                          child: Text('Compra entregada. Ya puedes valorar '
                            'sus prendas en la sección inferior.',
                            style: TextStyle(color: Colors.teal)),
                        ),
                    ],
                  ),
                ),
              ),
            const Divider(height: 36),
            Text('Valorar prendas entregadas',
              style: Theme.of(context).textTheme.titleLarge),
            const Text('Solo se permite valorar una compra CONFIRMADA y ENTREGADA. '
              'Una valoración por producto y compra.'),
            const SizedBox(height: 16),
            if (eligible.isEmpty)
              const Text(
                'Todavía no hay compras ENTREGADAS para valorar. '
                'El pago por sí solo no acredita la entrega.',
              ),
            for (final item in eligible)
              ListTile(
                title: Text(item['nombre'] as String),
                subtitle: Text(
                  'Compra ${(item['compra_id'] as String).substring(0, 8)}',
                ),
                trailing: const Icon(Icons.rate_review_outlined),
                onTap: busy ? null : () => _select(item),
              ),
            if (selectedProduct != null) ...[
              const Divider(height: 32),
              const Text('Tu valoración (1 a 5 estrellas)'),
              DropdownButtonFormField<int>(
                initialValue: rating,
                key: ValueKey(
                  selectedPurchase.toString() + selectedProduct.toString(),
                ),
                items: List.generate(
                  5,
                  (i) => DropdownMenuItem(
                    value: i + 1,
                    child: Text('${i + 1} estrellas'),
                  ),
                ),
                onChanged: busy ? null : (v) => setState(() => rating = v ?? 5),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: comment,
                maxLength: 1000,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Comentario opcional',
                ),
              ),
              FilledButton(
                onPressed: busy ? null : _submit,
                child: Text(
                  selectedReviewId == null
                      ? 'Publicar valoración'
                      : 'Actualizar mi valoración',
                ),
              ),
            ],
            const Divider(height: 32),
            Text(
              'Mis valoraciones (${reviews.length})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            for (final r in reviews)
              ListTile(
                title: Text('${r['puntuacion'] ?? 0}/5 estrellas'),
                subtitle: Text(r['comentario']?.toString() ?? 'Sin comentario'),
                trailing: const Icon(
                  Icons.verified_outlined,
                  color: Colors.teal,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
