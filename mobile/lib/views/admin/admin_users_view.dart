import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/models/admin.dart';
import 'package:yt_trends_app/viewmodels/admin_viewmodel.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class AdminUsersView extends StatelessWidget {
  const AdminUsersView({super.key});

  Future<void> _promote(
      BuildContext context, AdminViewModel vm, AdminUser u) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Dar permisos de administrador?'),
        content: Text(
            '${u.name} (@${u.username}) podrá ver el panel de admin. El cambio se guarda de inmediato y se aplica la próxima vez que inicie sesión.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Promover')),
        ],
      ),
    );
    if (confirm != true) return;
    final ok = await vm.promote(u);
    if (ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(
            '${u.username} ahora es admin. Tendrá los permisos al volver a iniciar sesión.'),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AdminViewModel>();
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.load);
    }
    return RefreshIndicator(
      onRefresh: vm.load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (vm.error != null) ...[
            MessageBanner(vm.error!),
            const SizedBox(height: 12),
          ],
          Text('${vm.usersTotal} usuarios',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final u in vm.users)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text(u.name),
                subtitle: Text(
                    '@${u.username}${u.channelHandle != null ? ' · ${u.channelHandle}' : ''}'),
                trailing: u.isAdmin
                    ? const Chip(label: Text('Admin'))
                    : OutlinedButton(
                        onPressed: vm.busy ? null : () => _promote(context, vm, u),
                        child: const Text('Hacer admin'),
                      ),
              ),
            ),
          if (vm.hasMoreUsers)
            Center(
              child: TextButton(
                onPressed: vm.busy ? null : vm.loadMoreUsers,
                child: const Text('Cargar más'),
              ),
            ),
        ],
      ),
    );
  }
}