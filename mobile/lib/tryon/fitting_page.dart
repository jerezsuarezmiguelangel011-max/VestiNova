import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../auth/auth_api.dart';
import 'catalog_api.dart';

class FittingPage extends StatefulWidget {
  const FittingPage({
    super.key,
    required this.api,
    required this.product,
    required this.variants,
    required this.initial,
    this.cameraBuilder,
  });
  final CatalogApi api;
  final Garment product;
  final List<FittingVariant> variants;
  final FittingVariant initial;
  final Widget Function(ValueChanged<int>)? cameraBuilder;
  @override
  State<FittingPage> createState() => _FittingPageState();
}

class _FittingPageState extends State<FittingPage> with WidgetsBindingObserver {
  static const permissionChannel = MethodChannel('vestinova/tryon_permission');
  late FittingVariant selected = widget.initial;
  MethodChannel? camera;
  Uint8List? png;
  bool permitted = false, requesting = false, blocked = false, active = true;
  String state = 'permission';
  String? error;
  String? permissionMessage;
  String? focusMessage;
  bool focusing = false;
  Timer? watchdog;
  int revision = 0;
  bool get android =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  Future<void> request() async {
    if (requesting) return;
    setState(() {
      requesting = true;
      error = null;
    });
    try {
      final result = await permissionChannel.invokeMethod<String>('request');
      if (!mounted) return;
      setState(() {
        permitted = result == 'granted';
        blocked = result == 'blocked';
        state = permitted ? 'loading' : 'permission';
        permissionMessage = permitted
            ? null
            : blocked
            ? 'Activa la cámara desde los ajustes de permisos o vuelve al detalle.'
            : 'El permiso de cámara no fue autorizado. Puedes volver al detalle o intentarlo nuevamente.';
      });
      if (permitted) await choose(selected);
    } on Object {
      if (mounted) {
        setState(
          () => error = 'No se pudo solicitar la cámara. Vuelve a intentar.',
        );
      }
    } finally {
      if (mounted) setState(() => requesting = false);
    }
  }

  Future<void> choose(FittingVariant variant) async {
    watchdog?.cancel();
    final current = ++revision;
    setState(() {
      selected = variant;
      error = null;
      state = 'loading';
      png = null;
      focusMessage = null;
    });
    try {
      await camera?.invokeMethod<void>('pause');
      final image = await widget.api.png(variant);
      if (!mounted || current != revision) return;
      setState(() => png = image);
      if (camera != null && active) await configure();
    } on Object catch (e) {
      if (mounted && current == revision) {
        setState(
          () => error = e is AccessException
              ? e.message
              : 'No se pudo preparar el vestidor.',
        );
      }
    }
  }

  Future<void> configure() async {
    final current = revision;
    final bytes = png;
    if (bytes == null || camera == null || !active || !permitted) return;
    try {
      await camera!.invokeMethod<void>('configure', {
        'png': bytes,
        'anclajes': selected.config['anclajes'],
        for (final key in [
          'factor_ancho',
          'factor_alto',
          'offset_x',
          'offset_y',
        ])
          key: selected.config[key],
      });
      if (mounted && active && current == revision && state == 'loading') {
        watchdog?.cancel();
        watchdog = Timer(const Duration(seconds: 20), () {
          if (mounted && active && current == revision) {
            setState(
              () => error = 'La cámara no entregó imágenes. Comprueba el permiso y vuelve a intentar.',
            );
          }
        });
      }
    } on Object {
      if (mounted && current == revision) {
        setState(
          () => error =
              'No se pudo preparar la cámara o la imagen de esta variante.',
        );
      }
    }
  }

  void created(int id) {
    camera = MethodChannel('vestinova/tryon/$id');
    camera!.setMethodCallHandler((call) async {
      if (!mounted || !active || call.method != 'state') return;
      final value = (call.arguments as Map)['estado'] as String;
      if (value != 'loading') watchdog?.cancel();
      setState(() {
        state = value;
        error = switch (value) {
          'camera_error' => 'No se pudo abrir la cámara. Comprueba que otra aplicación no la esté utilizando.',
          'model_error' =>
            'No se pudo cargar el modelo corporal del dispositivo.',
          'processing_error' => 'No se pudo analizar la imagen de la cámara. Reintenta el vestidor.',
          'permission' =>
            'El permiso de cámara ya no está disponible. Vuelve a autorizarlo.',
          _ => null,
        };
        if (value == 'permission') {
          permitted = false;
          camera?.setMethodCallHandler(null);
          camera = null;
          png = null;
        }
      });
    });
    configure();
  }

  Future<void> focusCamera() async {
    if (camera == null || focusing || !active) return;
    setState(() { focusing = true; focusMessage = null; });
    try {
      final result = await camera!.invokeMethod<String>('focus');
      if (!mounted) return;
      setState(() => focusMessage = switch (result) {
        'focused' => 'Enfoque del centro ajustado.',
        'fixed_focus' => 'Esta cámara no permite ajustar el enfoque. Se ajustó la exposición; prueba otra distancia y buena luz.',
        'not_focused' => 'No se logró enfocar. Busca más luz y evita moverte.',
        _ => 'La cámara no permite ajustar el enfoque ahora. Prueba otra distancia y mejor iluminación.',
      });
    } on Object {
      if (mounted) setState(() => focusMessage = 'No se pudo ajustar la cámara. Prueba otra distancia y mejor iluminación.');
    } finally {
      if (mounted) setState(() => focusing = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState value) {
    active = value == AppLifecycleState.resumed;
    if (!active) {
      watchdog?.cancel();
      camera?.invokeMethod<void>('pause').catchError((Object _) {});
    } else if (permitted && png != null) {
      configure();
    }
  }

  @override
  void dispose() {
    watchdog?.cancel();
    revision++;
    WidgetsBinding.instance.removeObserver(this);
    camera?.setMethodCallHandler(null);
    camera?.invokeMethod<void>('pause').catchError((Object _) {});
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Vestidor virtual')),
    body: SafeArea(
      child: Column(
        children: [
          Expanded(
            child: ColoredBox(
              color: const Color(0xFF202C27),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (android && permitted)
                    widget.cameraBuilder?.call(created) ??
                        AndroidView(
                          viewType: 'vestinova/tryon',
                          onPlatformViewCreated: created,
                        ),
                  if (!android)
                    const Center(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: Text(
                          'Este primer vestidor está disponible en Android. El soporte de cámara en iOS sigue pendiente.',
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                    )
                  else if (!permitted)
                    Center(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.camera_alt_outlined,
                              color: Colors.white,
                              size: 52,
                            ),
                            const SizedBox(height: 20),
                            const Text(
                              'Mírate con tu próxima prenda',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 23,
                              ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Necesitamos la cámara para detectar tu torso. Las imágenes se procesan en el teléfono; no se guardan ni se envían a Gemini.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.white),
                            ),
                            const SizedBox(height: 20),
                            if (permissionMessage != null)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 16),
                                child: Text(
                                  permissionMessage!,
                                  style: const TextStyle(color: Colors.white),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            FilledButton(
                              onPressed: requesting ? null : request,
                              child: Text(
                                requesting
                                    ? 'Solicitando permiso…'
                                    : 'Permitir cámara',
                              ),
                            ),
                            if (blocked)
                              TextButton(
                                onPressed: () => permissionChannel
                                    .invokeMethod<void>('settings'),
                                child: const Text(
                                  'Abrir ajustes de permisos',
                                  style: TextStyle(color: Colors.white),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  if (permitted && state == 'loading' && error == null)
                    const Center(
                      child: CircularProgressIndicator(color: Colors.white),
                    ),
                  if (error != null)
                    Center(
                      child: Container(
                        color: const Color(0xDD202C27),
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              error!,
                              style: const TextStyle(color: Colors.white),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 20),
                            FilledButton(
                              onPressed: () =>
                                  permitted ? choose(selected) : request(),
                              child: const Text('Reintentar'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  if (permitted && error == null)
                    Positioned(
                      top: 16,
                      left: 16,
                      right: 16,
                      child: Semantics(
                        liveRegion: true,
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xD9202C27),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            state == 'tracking'
                                ? 'Torso y mangas siguiendo tus puntos corporales · Vista 2D'
                                : state == 'uncalibrated'
                                ? 'Imagen sin calibrar: todavía no se adapta a los brazos.'
                                : state == 'loading'
                                ? 'Preparando cámara y prenda…'
                                : state == 'position_arms'
                                ? 'Deja visibles hombros, cintura y brazos completos. Sepáralos un poco del torso; evita cruzarlos o taparlos.'
                                : 'Colócate de frente, con ambos hombros y la cintura visibles. Evita taparte con el teléfono y busca buena luz.',
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                      ),
                    ),
                  if (permitted && error == null && state != 'loading')
                    Positioned(
                      bottom: 12,
                      right: 12,
                      child: FilledButton.icon(
                        onPressed: focusing ? null : focusCamera,
                        icon: const Icon(Icons.center_focus_strong),
                        label: Text(focusing ? 'Ajustando…' : 'Enfocar centro'),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  widget.product.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<int>(
                  initialValue: selected.id,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Talla y color de la prenda',
                  ),
                  items: widget.variants
                      .map(
                        (v) =>
                            DropdownMenuItem(value: v.id, child: Text(v.label)),
                      )
                      .toList(),
                  onChanged: permitted
                      ? (id) => choose(
                          widget.variants.firstWhere((v) => v.id == id),
                        )
                      : null,
                ),
                const SizedBox(height: 8),
                Text(
                  selected.config['demostracion'] == true
                      ? 'Imagen ilustrativa de demostración. No garantiza talla ni ajuste físico.'
                      : 'Vista orientativa. No garantiza talla ni ajuste físico.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (focusMessage != null) ...[
                  const SizedBox(height: 8),
                  Text(focusMessage!, style: Theme.of(context).textTheme.bodySmall),
                ],
              ],
            ),
          ),
        ],
      ),
    ),
  );
}
