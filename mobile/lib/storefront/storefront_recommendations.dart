import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import 'storefront_api.dart';
import 'storefront_models.dart';
import 'storefront_widgets.dart';

class StorefrontRecommendationsPage extends StatefulWidget {
  const StorefrontRecommendationsPage({
    super.key,
    required this.tienda,
    required this.api,
    required this.session,
    required this.onOpen,
    required this.onCompare,
    required this.isSelected,
    this.reference,
  });
  final String tienda;
  final StorefrontApi api;
  final SessionController session;
  final ValueChanged<StoreProduct> onOpen;
  final ValueChanged<StoreProduct> onCompare;
  final bool Function(int id) isSelected;
  final String? reference;
  @override
  State<StorefrontRecommendationsPage> createState() =>
      _StorefrontRecommendationsPageState();
}

class _StorefrontRecommendationsPageState
    extends State<StorefrontRecommendationsPage> {
  final _size = TextEditingController();
  final _color = TextEditingController();
  List<StoreProduct> _items = [];
  bool _busy = true;
  bool? _consent;
  bool _personal = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
    _loadConsent();
  }

  @override
  void didUpdateWidget(covariant StorefrontRecommendationsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.reference != oldWidget.reference ||
        widget.session.customerToken != oldWidget.session.customerToken) {
      _load();
      _loadConsent();
    }
  }

  @override
  void dispose() {
    _size.dispose();
    _color.dispose();
    super.dispose();
  }

  Future<void> _loadConsent() async {
    final token = widget.session.customerToken;
    if (token == null || widget.session.offlineMode) {
      if (mounted) setState(() => _consent = null);
      return;
    }
    try {
      final enabled = await widget.api.consent(widget.tienda, token);
      if (mounted) setState(() => _consent = enabled);
    } catch (_) {
      if (mounted) setState(() => _consent = null);
    }
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final token = widget.session.customerToken;
      final items = _personal && _consent == true && token != null
          ? await widget.api.personalized(widget.tienda, token)
          : await widget.api.recommendations(
              widget.tienda,
              reference: widget.reference,
              size: _size.text.trim().isEmpty ? null : _size.text.trim(),
              color: _color.text.trim().isEmpty ? null : _color.text.trim(),
            );
      if (mounted) setState(() => _items = items);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setConsent(bool enabled) async {
    final token = widget.session.customerToken;
    if (token == null) return;
    try {
      final result = await widget.api.setConsent(widget.tienda, token, enabled);
      if (!mounted) return;
      setState(() {
        _consent = result;
        if (!result) _personal = false;
      });
      notice(
        context,
        result
            ? 'Personalización activada.'
            : 'Personalización desactivada y visitas anteriores eliminadas.',
      );
      _load();
    } catch (e) {
      if (mounted) notice(context, 'No se pudo cambiar la preferencia: $e');
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      Text('Recomendaciones', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 6),
      Text(
        widget.reference == null
            ? 'Sugerencias de la tienda'
            : 'Prendas parecidas a ${widget.reference}',
      ),
      const SizedBox(height: 14),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _size,
              decoration: const InputDecoration(labelText: 'Talla'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: _color,
              decoration: const InputDecoration(labelText: 'Color'),
            ),
          ),
        ],
      ),
      const SizedBox(height: 10),
      FilledButton(
        onPressed: _busy ? null : _load,
        child: const Text('Actualizar sugerencias'),
      ),
      if (_consent != null) ...[
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Personalización opcional'),
          subtitle: const Text(
            'Permite guardar visitas a prendas. Desactivarla elimina ese historial.',
          ),
          value: _consent!,
          onChanged: _setConsent,
        ),
        if (_consent == true)
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Usar historial consentido'),
            value: _personal,
            onChanged: (value) {
              setState(() => _personal = value);
              _load();
            },
          ),
      ],
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) StorefrontMessage(message: _error!, retry: _load),
      if (!_busy && _error == null && _items.isEmpty)
        const StorefrontMessage(
          message: 'Todavía no hay sugerencias para estos criterios.',
        ),
      if (_error == null)
        ..._items.map(
          (p) => ProductRow(
            item: p,
            onOpen: () => widget.onOpen(p),
            onCompare: () => widget.onCompare(p),
            inComparison: widget.isSelected(p.id),
          ),
        ),
    ],
  );
}
