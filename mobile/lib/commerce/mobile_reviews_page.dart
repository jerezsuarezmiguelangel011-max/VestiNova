import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import '../storefront/storefront_widgets.dart';
import 'mobile_commerce_api.dart';

/// CU25: solo permite valorar productos de compras centrales ENTREGADAS.
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

  List<Map<String, dynamic>> get eligible {
    final result = <Map<String, dynamic>>[];
    for (final purchase in purchases) {
      if (purchase['estado'] != 'CONFIRMADA' ||
          purchase['seguimiento_entrega'] != 'ENTREGADA') {
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
            Text(
              'Valorar prendas compradas',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const Text(
              'Solo compras confirmadas y con entrega verificada. '
              'Una opinión por producto y compra.',
            ),
            if (busy) const LinearProgressIndicator(),
            if (error != null) StorefrontMessage(message: error!, retry: _load),
            if (noticeText != null)
              Text(noticeText!, style: const TextStyle(color: Colors.teal)),
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
