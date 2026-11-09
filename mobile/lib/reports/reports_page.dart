import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../auth/auth_api.dart';
import '../auth/session_controller.dart';
import 'reports_api.dart';

class ReportsPage extends StatefulWidget {
  const ReportsPage({super.key, required this.controller, this.api});
  final SessionController controller;
  final ReportsApi? api;
  @override
  State<ReportsPage> createState() => _ReportsPageState();
}

class _ReportsPageState extends State<ReportsPage> {
  late final ReportsApi api =
      widget.api ?? ReportsApi(widget.controller.api.config);
  late final int? company = widget.controller.context?.company.id;
  late final String? token = widget.controller.staffAccessToken;
  final prompt = TextEditingController();
  final from = TextEditingController();
  final until = TextEditingController();
  final speech = SpeechToText();
  Map<String, dynamic>? options;
  Map<String, dynamic>? report;
  String? error;
  String? message;
  int? branch;
  int? category;
  int? product;
  bool busy = false;
  bool recording = false;
  int revision = 0;
  bool get sameContext =>
      token != null &&
      company != null &&
      widget.controller.staffAccessToken == token &&
      widget.controller.context?.company.id == company &&
      widget.controller.context?.company.canUseAIReports == true;
  bool current(int captured) => mounted && captured == revision && sameContext;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(contextChanged);
    load();
  }

  void contextChanged() {
    if (!sameContext && mounted) {
      revision++;
      stopVoice();
      setState(() {
        options = null;
        report = null;
        busy = false;
        prompt.clear();
        from.clear();
        until.clear();
        error =
            'La sesión o empresa cambió. Vuelve a tu cuenta para continuar.';
      });
    }
  }

  Future<void> load() async {
    if (!sameContext) {
      error = 'Selecciona una empresa y un acceso autorizado.';
      return;
    }
    final captured = ++revision;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final value = await api.options(token!, company!);
      if (current(captured)) setState(() => options = value);
    } on AccessException catch (failure) {
      if (current(captured)) setState(() => error = failure.message);
    } on Object {
      if (current(captured)) {
        setState(
          () =>
              error = 'No se pudieron cargar los reportes. Inténtalo de nuevo.',
        );
      }
    } finally {
      if (current(captured)) setState(() => busy = false);
    }
  }

  Map<String, dynamic> filters() => {
    if (from.text.trim().isNotEmpty) 'desde': from.text.trim(),
    if (until.text.trim().isNotEmpty) 'hasta': until.text.trim(),
    if (branch != null) 'sucursal_id': branch,
    if (category != null) 'categoria_id': category,
    if (product != null) 'producto_id': product,
  };
  Future<void> generate() async {
    if (busy ||
        !sameContext ||
        options?['profesional_vigente'] != true ||
        options?['ia_configurada'] != true) {
      return;
    }
    if (prompt.text.trim().length < 5 || prompt.text.length > 800) {
      setState(() => error = 'Escribe una consulta de 5 a 800 caracteres.');
      return;
    }
    await stopVoice();
    if (!mounted || !sameContext) return;
    final captured = ++revision;
    setState(() {
      busy = true;
      report = null;
      error = null;
      message = null;
    });
    try {
      final result = await api.generate(
        token!,
        company!,
        prompt.text.trim(),
        filters(),
      );
      if (current(captured)) {
        setState(() {
          report = result['reporte'] as Map<String, dynamic>?;
          message = result['mensaje'] as String?;
        });
      }
    } on AccessException catch (failure) {
      if (current(captured)) setState(() => error = failure.message);
    } on Object {
      if (current(captured)) {
        setState(
          () => error = 'No se pudo generar el reporte. No se muestran resultados incompletos.',
        );
      }
    } finally {
      if (current(captured)) setState(() => busy = false);
    }
  }

  Future<void> dictate() async {
    if (busy || !sameContext) return;
    if (recording) {
      await stopVoice();
      return;
    }
    final captured = revision;
    try {
      final available = await speech.initialize(
        onError: (_) {
          if (current(captured)) {
            setState(() {
              recording = false;
              message =
                  'El dictado no está disponible. Puedes escribir la consulta.';
            });
          }
        },
        onStatus: (status) {
          if (current(captured) &&
              (status == 'done' || status == 'notListening')) {
            setState(() => recording = false);
          }
        },
      );
      if (!current(captured)) return;
      if (!available) {
        setState(
          () => message = 'Permiso de micrófono denegado o dictado no compatible. Usa texto.',
        );
        return;
      }
      setState(() => recording = true);
      final locales = await speech.locales();
      final spanish = locales
          .where((locale) => locale.localeId.toLowerCase().startsWith('es'))
          .toList();
      if (!current(captured)) return;
      await speech.listen(
        listenOptions: SpeechListenOptions(
          localeId: spanish.isEmpty ? null : spanish.first.localeId,
        ),
        onResult: (result) {
          if (current(captured)) {
            setState(() {
              prompt.text = result.recognizedWords.length > 800
                  ? result.recognizedWords.substring(0, 800)
                  : result.recognizedWords;
              message =
                  'Revisa el texto reconocido antes de generar el reporte.';
            });
          }
        },
      );
    } on Object {
      if (current(captured)) {
        setState(() {
          recording = false;
          message =
              'No se pudo usar el micrófono. Puedes escribir la consulta.';
        });
      }
    }
  }

  Future<void> stopVoice() async {
    try {
      await speech.cancel();
    } catch (_) {
      /* El texto sigue disponible. */
    }
    if (mounted) setState(() => recording = false);
  }

  Future<void> export(String format) async {
    final value = report;
    if (value == null || busy || !sameContext) return;
    final captured = revision;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final bytes = await api.export(token!, company!, value, format);
      if (!mounted || !current(captured)) return;
      final type = switch (format) {
        'pdf' => 'application/pdf',
        'xlsx' =>
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        _ => 'text/html',
      };
      final box = context.findRenderObject() as RenderBox?;
      await SharePlus.instance.share(
        ShareParams(
          files: [XFile.fromData(bytes, mimeType: type)],
          fileNameOverrides: ['vestinova-reporte.$format'],
          sharePositionOrigin: box == null
              ? null
              : box.localToGlobal(Offset.zero) & box.size,
        ),
      );
    } on AccessException catch (failure) {
      if (current(captured)) setState(() => error = failure.message);
    } on Object {
      if (current(captured)) {
        setState(
          () => error = 'No se pudo exportar o compartir el archivo. El reporte permanece disponible.',
        );
      }
    } finally {
      if (current(captured)) setState(() => busy = false);
    }
  }

  Widget selector(
    String label,
    String key,
    int? selected,
    ValueChanged<int?> change,
  ) {
    final items = (options?[key] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return DropdownButtonFormField<int>(
      key: ValueKey('$key-$selected'),
      initialValue: selected,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: [
        const DropdownMenuItem<int>(
          value: null,
          child: Text('Todas las autorizadas'),
        ),
        ...items.map(
          (item) => DropdownMenuItem<int>(
            value: item['id'] as int,
            child: Text(
              item['nombre'] as String,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ],
      onChanged: busy ? null : change,
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Reportes con IA')),
    body: SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.controller.context?.company.name ??
                  'Empresa no disponible',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),
            if (busy)
              const LinearProgressIndicator(
                semanticsLabel: 'Consultando reporte',
              ),
            if (error != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  error!,
                  style: const TextStyle(color: Color(0xFF9D2727)),
                ),
              ),
            if (message != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(message!),
              ),
            if (options != null) ...[
              if (options!['profesional_vigente'] != true)
                const Text(
                  'Los reportes con IA requieren plan Profesional vigente.',
                ),
              if (options!['ia_configurada'] != true)
                const Text('El proveedor de IA todavía no está configurado.'),
              const SizedBox(height: 16),
              TextField(
                controller: prompt,
                maxLength: 800,
                minLines: 3,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: '¿Qué necesitas consultar?',
                  helperText: 'La IA interpreta la consulta; el servidor calcula los resultados.',
                ),
              ),
              OutlinedButton.icon(
                onPressed: busy ? null : dictate,
                icon: Icon(recording ? Icons.stop : Icons.mic_none),
                label: Text(
                  recording ? 'Detener dictado' : 'Dictar y revisar texto',
                ),
              ),
              Wrap(
                spacing: 8,
                children:
                    [
                          'Ventas diarias del último mes',
                          'Prendas más vendidas este mes',
                          'Inventario actual por sucursal',
                          'Abastecimiento por proveedor este mes',
                        ]
                        .map(
                          (example) => ActionChip(
                            label: Text(example),
                            onPressed: busy
                                ? null
                                : () {
                                    prompt.text = example;
                                    if (example.startsWith('Inventario')) {
                                      from.clear();
                                      until.clear();
                                    }
                                  },
                          ),
                        )
                        .toList(),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: from,
                keyboardType: TextInputType.datetime,
                decoration: const InputDecoration(
                  labelText: 'Desde (AAAA-MM-DD)',
                  helperText: 'Vacío para inventario actual',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: until,
                keyboardType: TextInputType.datetime,
                decoration: const InputDecoration(
                  labelText: 'Hasta (AAAA-MM-DD)',
                ),
              ),
              const SizedBox(height: 12),
              selector(
                'Sucursal',
                'sucursales',
                branch,
                (value) => setState(() => branch = value),
              ),
              const SizedBox(height: 12),
              selector(
                'Categoría',
                'categorias',
                category,
                (value) => setState(() => category = value),
              ),
              const SizedBox(height: 12),
              selector(
                'Prenda',
                'productos',
                product,
                (value) => setState(() => product = value),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed:
                    busy ||
                        options!['profesional_vigente'] != true ||
                        options!['ia_configurada'] != true ||
                        !sameContext
                    ? null
                    : generate,
                child: const Text('Generar reporte'),
              ),
            ] else if (!busy && sameContext)
              OutlinedButton(
                onPressed: load,
                child: const Text('Cargar opciones'),
              ),
            if (report case final value?) ...[
              const SizedBox(height: 24),
              Text(
                value['titulo'] as String,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              Text(
                'Empresa: ${(value['empresa'] as Map<String, dynamic>)['nombre']}. Registros centrales · BOB.',
              ),
              Text('Filtros: ${value['filtros']}'),
              if (value['sin_datos'] == true)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    'No se encontraron registros. No se inventaron cifras.',
                  ),
                ),
              ...((value['totales'] as Map<String, dynamic>).entries.map(
                (item) => ListTile(
                  title: Text(item.key.replaceAll('_', ' ')),
                  trailing: Text('${item.value}'),
                ),
              )),
              if ((value['filas'] as List<dynamic>).isNotEmpty)
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: (value['columnas'] as List<dynamic>)
                        .map((name) => DataColumn(label: Text('$name')))
                        .toList(),
                    rows: (value['filas'] as List<dynamic>)
                        .map(
                          (row) => DataRow(
                            cells: (value['columnas'] as List<dynamic>)
                                .map((name) => DataCell(Text('${row[name]}')))
                                .toList(),
                          ),
                        )
                        .toList(),
                  ),
                ),
              if (value['truncado'] == true)
                Text(
                  'Se muestran/exportan 200 de ${value['total_filas']} filas. Afina los filtros.',
                ),
              ...((value['notas'] as List<dynamic>).map(
                (note) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text('$note'),
                ),
              )),
              const Text(
                'Al exportar se consultan nuevamente los registros y tus permisos.',
              ),
              Wrap(
                spacing: 8,
                children: ['html', 'pdf', 'xlsx']
                    .map(
                      (format) => OutlinedButton(
                        onPressed: busy ? null : () => export(format),
                        child: Text('Exportar ${format.toUpperCase()}'),
                      ),
                    )
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    ),
  );
  @override
  void dispose() {
    revision++;
    widget.controller.removeListener(contextChanged);
    stopVoice();
    api.dispose();
    prompt.dispose();
    from.dispose();
    until.dispose();
    super.dispose();
  }
}
