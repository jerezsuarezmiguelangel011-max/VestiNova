import 'package:flutter/material.dart';
import 'storefront_models.dart';

const vnInk = Color(0xFF202C27);
const vnGreen = Color(0xFF12644E);
const vnIvory = Color(0xFFF7F4EC);

class ProductPhoto extends StatelessWidget {
  const ProductPhoto(this.url, {super.key, this.height = 112});
  final String? url;
  final double height;
  @override
  Widget build(BuildContext context) {
    final uri = url == null ? null : Uri.tryParse(url!);
    if (uri == null || !['http', 'https'].contains(uri.scheme) || uri.host.isEmpty) {
      return _placeholder();
    }
    return ClipRRect(borderRadius: BorderRadius.circular(12), child: Image.network(
      uri.toString(), height: height, width: height, fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => _placeholder(),
    ));
  }
  Widget _placeholder() => Container(
    height: height, width: height,
    decoration: BoxDecoration(color: const Color(0xFFE2E5DD), borderRadius: BorderRadius.circular(12)),
    child: const Icon(Icons.checkroom_outlined, size: 36, color: vnGreen),
  );
}

class ProductRow extends StatelessWidget {
  const ProductRow({super.key, required this.item, required this.onOpen,
    this.onCompare, this.inComparison = false});
  final StoreProduct item;
  final VoidCallback onOpen;
  final VoidCallback? onCompare;
  final bool inComparison;
  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    clipBehavior: Clip.antiAlias,
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(children: [
        ProductPhoto(item.imageUrl),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(item.name, style: Theme.of(context).textTheme.titleMedium, maxLines: 2),
          if (item.category.isNotEmpty) Text(item.category, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 5),
          Text('Bs ${item.effectivePrice}', style: const TextStyle(fontWeight: FontWeight.bold, color: vnGreen)),
          if (item.salePrice != null) Text('Antes: Bs ${item.price}',
              style: const TextStyle(decoration: TextDecoration.lineThrough, fontSize: 12)),
          if (item.reasons.isNotEmpty) Text(item.reasons.first,
              style: Theme.of(context).textTheme.bodySmall, maxLines: 2),
          Wrap(spacing: 4, children: [
            TextButton(onPressed: onOpen, child: const Text('Ver detalle')),
            if (onCompare != null) TextButton.icon(
              onPressed: onCompare,
              icon: Icon(inComparison ? Icons.check_circle : Icons.compare_arrows, size: 17),
              label: Text(inComparison ? 'Agregada' : 'Comparar'),
            ),
          ]),
        ])),
      ]),
    ),
  );
}

class CacheNotice extends StatelessWidget {
  const CacheNotice({super.key, required this.savedAt, this.partial = false});
  final String? savedAt;
  final bool partial;
  @override
  Widget build(BuildContext context) => Card(
    color: const Color(0xFFFFF1D5),
    child: Padding(padding: const EdgeInsets.all(12), child: Text(
      'Copia sin conexión (${savedAt ?? 'fecha desconocida'}). '
      '${partial ? 'Catálogo posiblemente incompleto. ' : ''}'
      'Los precios y existencias pueden haber cambiado; no son confirmación de stock.',
    )),
  );
}

class StorefrontMessage extends StatelessWidget {
  const StorefrontMessage({super.key, required this.message, this.retry});
  final String message;
  final VoidCallback? retry;
  @override
  Widget build(BuildContext context) => Center(child: Padding(
    padding: const EdgeInsets.all(22),
    child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.info_outline, size: 32),
      const SizedBox(height: 10),
      Text(message, textAlign: TextAlign.center),
      if (retry != null) ...[const SizedBox(height: 12), OutlinedButton(
        onPressed: retry, child: const Text('Volver a intentar'))],
    ]),
  ));
}

void notice(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}
