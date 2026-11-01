import 'package:flutter/material.dart';

import '../auth/auth_models.dart';
import '../auth/session_controller.dart';

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
        if (customer)
          const Text(
            'Tu cuenta pertenece a esta tienda. Tu acceso está verificado.',
          )
        else ...[
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
              onChanged: controller.busy
                  ? null
                  : (id) {
                      if (id != null) controller.selectCompany(id);
                    },
            ),
          if (controller.context case final access?) ...[
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
          ],
        ],
        const SizedBox(height: 28),
        OutlinedButton.icon(
          onPressed: controller.busy ? null : controller.refresh,
          icon: const Icon(Icons.refresh),
          label: Text(customer ? 'Comprobar mi acceso' : 'Actualizar accesos'),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.busy ? null : controller.logout,
          icon: const Icon(Icons.logout),
          label: const Text('Cerrar sesión'),
        ),
      ],
    );
  }
}
