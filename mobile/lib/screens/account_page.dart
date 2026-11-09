import 'package:flutter/material.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';
import '../reservations/customer_reservations_page.dart';
import '../reports/reports_page.dart';
import '../tryon/catalog_page.dart';
import '../staff/cash_sale_page.dart';
import '../staff/reconciliation_page.dart';

class AccountPage extends StatelessWidget {
  const AccountPage({super.key, required this.controller});
  final SessionController controller;
  @override
  Widget build(BuildContext context) {
    final account = controller.account!;
    final customer = account is CustomerAccount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Tu cuenta', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 20),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  account.name,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                SelectableText(account.email),
                const SizedBox(height: 12),
                Text(
                  customer
                      ? 'Cliente · ${account.store.name}'
                      : 'Personal de VestiNova',
                ),
                if (controller.isSuperadministrator) ...[
                  const SizedBox(height: 12),
                  const Chip(label: Text('Superadministrador SaaS')),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
        if (account is CustomerAccount) ...[
          Text(
            controller.offlineMode
                ? 'Modo offline: esta identidad fue validada anteriormente. '
                    'Las operaciones se guardan localmente, pero no están confirmadas por el servidor.'
                : 'Tu cuenta pertenece a esta tienda y el acceso está verificado.',
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => CatalogPage(
                  store: account.store,
                  config: controller.api.config,
                ),
              ),
            ),
            icon: const Icon(Icons.checkroom),
            label: const Text('Explorar prendas y vestidor'),
          ),
        ] else ...[
          Text(
            'Empresa de trabajo',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          if (controller.companies.isEmpty)
            const Text(
              'No tienes empresas activas autorizadas. Puedes actualizar tus accesos o cerrar sesión.',
            )
          else
            DropdownButtonFormField<int>(
              key: ValueKey(controller.context?.company.id),
              initialValue: controller.context?.company.id,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Empresa autorizada',
              ),
              hint: const Text('Elige una empresa'),
              items: controller.companies
                  .map(
                    (company) => DropdownMenuItem(
                      value: company.id,
                      child: Text(
                        company.name,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(growable: false),
              onChanged: controller.busy || controller.offlineMode
                  ? null
                  : (id) {
                      if (id != null) controller.selectCompany(id);
                    },
            ),
          if (controller.context case final access?) ...[
            if (access.company.canUseAIReports) ...[
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: controller.busy
                    ? null
                    : () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => ReportsPage(controller: controller),
                        ),
                      ),
                icon: const Icon(Icons.auto_awesome),
                label: const Text('Reportes con IA · CU21'),
              ),
            ],
            const SizedBox(height: 16),
            Text(
              access.company.roleLabel,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 24),
            Text(
              'Sucursales autorizadas',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            if (access.branches.isEmpty)
              const Text(
                'No hay sucursales activas autorizadas para tu cuenta.',
              )
            else
              ...access.branches.map(
                (branch) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.storefront_outlined),
                  title: Text(branch.name),
                  subtitle: Text(branch.code),
                ),
              ),
          if (const {'CAJERO', 'ENCARGADO_SUCURSAL'}.contains(access.company.role)) ...[
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => StaffCashSalePage(session: controller, staffContext: access),
                ),
              ),
              icon: const Icon(Icons.point_of_sale),
              label: const Text('CU15 · Registrar ventas en caja'),
            ),
          ],
          if (access.company.role == 'ENCARGADO_SUCURSAL') ...[
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: controller.offlineMode ? null : () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ReconciliationPage(session: controller, staffContext: access),
                ),
              ),
              icon: const Icon(Icons.fact_check_outlined),
              label: const Text('CU13 · Conciliar conflictos offline'),
            ),
          ],
          ],
        ],
        if (customer) CustomerReservationsPage(controller: controller),
        const SizedBox(height: 28),
        OutlinedButton.icon(
          onPressed: controller.busy ? null : controller.refresh,
          icon: const Icon(Icons.refresh),
          label: Text(customer ? 'Comprobar mi acceso' : 'Actualizar accesos'),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.busy ? null : (controller.offlineMode ? controller.logoutLocal : controller.logout),
          icon: const Icon(Icons.logout),
          label: Text(controller.offlineMode ? 'Salir de este dispositivo (sin Internet)' : 'Cerrar sesión'),
        ),
      ],
    );
  }
}
