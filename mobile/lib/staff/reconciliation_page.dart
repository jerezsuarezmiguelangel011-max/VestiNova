import 'package:flutter/material.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';
import 'cash_api.dart';

/// CU13: solo el Encargado autorizado documenta decisiones sin tocar inventario.
class ReconciliationPage extends StatefulWidget {
  const ReconciliationPage({super.key, required this.session, required this.staffContext});
  final SessionController session;
  final StaffContext staffContext;

  @override
  State<ReconciliationPage> createState() => _ReconciliationPageState();
}

class _ReconciliationPageState extends State<ReconciliationPage> {
  late final StaffCashApi api;
  final reference = TextEditingController();
  final observation = TextEditingController();
  int? branchId;
  String filter = 'CONFLICTO';
  String decision = 'ACUERDO_DOCUMENTADO';
  bool busy = false;
  String? message, error;
  List<Map<String, dynamic>> incidents = [];
  Map<String, dynamic>? selected;

  int get companyId => widget.staffContext.company.id;
  String? get token => widget.session.staffToken;

  @override
  void initState() {
    super.initState();
    api = StaffCashApi(widget.session.api.config);
    branchId = widget.staffContext.branches.isEmpty ? null : widget.staffContext.branches.first.id;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _load();
    });
  }

  Future<void> _load() async {
    final branch = branchId, key = token;
    if (branch == null || key == null || busy) return;
    setState(() { busy = true; error = null; message = null; });
    try {
      final rows = await api.incidents(key, companyId, branch, filter);
      if (mounted && branch == branchId) setState(() {
        incidents = rows;
        selected = null;
      });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _open(String id) async {
    final key = token;
    if (key == null || busy) return;
    setState(() { busy = true; error = null; message = null; selected = null; });
    try {
      final record = await api.incident(key, companyId, id);
      if (mounted) setState(() {
        selected = record;
        reference.clear();
        observation.clear();
        decision = 'ACUERDO_DOCUMENTADO';
      });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _resolve() async {
    final key = token, incident = selected;
    if (key == null || busy || incident == null || incident['estado'] != 'CONFLICTO') return;
    if (reference.text.trim().length < 4 || reference.text.trim().length > 120 ||
        observation.text.trim().length < 15 || observation.text.trim().length > 350) {
      setState(() => error = 'Indica una constancia (4–120 caracteres) y observación (15–350 caracteres).');
      return;
    }
    setState(() { busy = true; error = null; message = null; });
    try {
      await api.resolve(key, companyId, incident['id'] as String,
        decision: decision,
        reference: reference.text.trim(),
        observation: observation.text.trim());
      if (mounted) setState(() => message = 'Resolución documentada; sin cambios automáticos de stock ni efectivo.');
      final rows = await api.incidents(key, companyId, branchId!, filter);
      if (mounted) setState(() {
        incidents = rows;
        selected = null;
      });
    } on CashApiError catch (e) {
      if (mounted) setState(() => error = e.status == 409
        ? 'El conflicto ya tiene otra resolución; actualiza la bandeja.'
        : e.message);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    reference.dispose();
    observation.dispose();
    api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.staffContext.company.role != 'ENCARGADO_SUCURSAL' ||
        token == null || branchId == null) {
      return Scaffold(appBar: AppBar(title: const Text('CU13 · Conciliación')),
        body: const Center(child: Text('Requiere Encargado de sucursal autorizado.')));
    }
    return Scaffold(
      appBar: AppBar(title: const Text('CU13 · Conciliar conflictos')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Conflictos offline por sucursal. Cada decisión requiere una constancia verificable. No se registran devoluciones ni se modifica el stock automáticamente.'),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: ValueKey(branchId), initialValue: branchId, isExpanded: true,
          decoration: const InputDecoration(labelText: 'Sucursal autorizada'),
          items: widget.staffContext.branches.map((b) => DropdownMenuItem(
            value: b.id, child: Text(b.name, overflow: TextOverflow.ellipsis))).toList(),
          onChanged: busy ? null : (id) {
            if (id == null) return;
            setState(() { branchId = id; selected = null; incidents = []; });
            _load();
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: filter,
          decoration: const InputDecoration(labelText: 'Estado'),
          items: const [
            DropdownMenuItem(value: 'CONFLICTO', child: Text('Pendientes de resolver')),
            DropdownMenuItem(value: 'RESUELTO', child: Text('Resueltos')),
            DropdownMenuItem(value: 'TODOS', child: Text('Todos')),
          ],
          onChanged: busy ? null : (value) {
            if (value == null) return;
            setState(() => filter = value);
            _load();
          },
        ),
        OutlinedButton.icon(onPressed: busy ? null : _load,
          icon: const Icon(Icons.refresh), label: const Text('Actualizar bandeja central')),
        if (busy) const LinearProgressIndicator(),
        if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
        if (message != null) Text(message!, style: const TextStyle(color: Color(0xFF12644E))),
        if (incidents.isEmpty && !busy) const Text('No hay incidencias en esta selección.'),
        for (final item in incidents)
          Card(child: ListTile(
            title: Text('${item['tipo'] ?? 'Operación'} · ${item['estado']}'),
            subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${item['motivo'] ?? ''}'),
              SelectableText('UUID original: ${item['operacion_id'] ?? ''}'),
            ]),
            trailing: const Icon(Icons.chevron_right),
            onTap: busy ? null : () => _open(item['id'] as String),
          )),
        if (selected case final incident?) ...[
          const Divider(height: 30),
          Text('Detalle de incidencia', style: Theme.of(context).textTheme.titleLarge),
          SelectableText('ID: ${incident['id']}'),
          Text('Tipo: ${incident['tipo']} · Estado: ${incident['estado']}'),
          Text('Motivo: ${incident['motivo']}'),
          const SizedBox(height: 8),
          const Text('Captura original (no editable)'),
          SelectableText('${incident['datos_originales']}'),
          if (incident['estado'] == 'CONFLICTO') ...[
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: decision,
              decoration: const InputDecoration(labelText: 'Decisión respaldada'),
              items: const [
                DropdownMenuItem(value: 'ACUERDO_DOCUMENTADO', child: Text('Acuerdo documentado')),
                DropdownMenuItem(value: 'DEVOLUCION_DOCUMENTADA', child: Text('Devolución documentada')),
                DropdownMenuItem(value: 'ENTREGA_ALTERNATIVA_DOCUMENTADA', child: Text('Entrega alternativa documentada')),
              ],
              onChanged: busy ? null : (value) => setState(() => decision = value ?? decision),
            ),
            const SizedBox(height: 8),
            TextField(controller: reference, maxLength: 120,
              decoration: const InputDecoration(labelText: 'Referencia de constancia existente')),
            TextField(controller: observation, maxLength: 350, maxLines: 3,
              decoration: const InputDecoration(labelText: 'Observación de la decisión')),
            const Text('La documentación debe existir realmente. Esta acción no efectúa reembolsos ni entrega mercadería.'),
            FilledButton.icon(
              onPressed: busy ? null : _resolve,
              icon: const Icon(Icons.fact_check),
              label: const Text('Documentar resolución'),
            ),
          ] else const Text('Conflicto ya resuelto; decisión inmutable.'),
        ],
      ]),
    );
  }
}
