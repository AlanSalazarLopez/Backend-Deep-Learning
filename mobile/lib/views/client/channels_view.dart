import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/models/channel.dart';
import 'package:yt_trends_app/viewmodels/channel_viewmodel.dart';
import 'package:yt_trends_app/views/client/add_channel_view.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class ChannelsView extends StatelessWidget {
  const ChannelsView({super.key});

  void _openAdd(BuildContext context, ChannelViewModel vm) {
    vm.startAdd();
    // La ruta nueva vive fuera del árbol del home: se le pasa el mismo ViewModel.
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChangeNotifierProvider.value(
        value: vm,
        child: const AddChannelView(),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<ChannelViewModel>();
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.load);
    }
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: vm.canAdd && !vm.busy ? () => _openAdd(context, vm) : null,
        icon: const Icon(Icons.add),
        label: const Text('Agregar canal'),
      ),
      body: RefreshIndicator(
        onRefresh: vm.load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          children: [
            if (vm.error != null) ...[
              MessageBanner(vm.error!),
              const SizedBox(height: 12),
            ],
            if (vm.channels.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Text(
                  'Aún no tienes canales.\nAgrega tu @handle para empezar.',
                  textAlign: TextAlign.center,
                ),
              ),
            for (final c in vm.channels) _ChannelCard(channel: c, vm: vm),
            if (!vm.canAdd)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Llegaste al máximo de 5 canales.',
                    textAlign: TextAlign.center),
              ),
          ],
        ),
      ),
    );
  }
}

class _ChannelCard extends StatelessWidget {
  const _ChannelCard({required this.channel, required this.vm});

  final Channel channel;
  final ChannelViewModel vm;

  Future<void> _confirmDelete(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Quitar este canal?'),
        content: const Text(
            'Se borrarán el canal y sus videos de nuestra base de datos. No afecta tu canal en YouTube.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Quitar')),
        ],
      ),
    );
    if (ok == true) await vm.delete(channel.id);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final nicheInList = vm.niches.any((n) => n.id == channel.nicheId);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(channel.title ?? channel.handle,
                          style: theme.textTheme.titleMedium),
                      Text(channel.handle, style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Quitar canal',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: vm.busy ? null : () => _confirmDelete(context),
                ),
              ],
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              key: ValueKey('${channel.id}-${channel.nicheId}'),
              initialValue: nicheInList ? channel.nicheId : null,
              decoration: const InputDecoration(
                labelText: 'Nicho',
                border: OutlineInputBorder(),
              ),
              hint: const Text('Elige un nicho'),
              items: [
                for (final n in vm.niches)
                  DropdownMenuItem(value: n.id, child: Text(n.name)),
              ],
              onChanged: vm.busy
                  ? null
                  : (id) {
                      if (id != null && id != channel.nicheId) {
                        vm.setNiche(channel.id, id);
                      }
                    },
            ),
            if (!channel.isSpanish) ...[
              const SizedBox(height: 12),
              MessageBanner(
                'Este canal parece estar en "${channel.language}". El modelo se entrena solo con títulos en español, así que sus videos no se usan para entrenar.',
                isError: false,
              ),
            ],
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Usar mis datos públicos para mejorar los análisis'),
              subtitle: const Text(
                  'Títulos, fechas y vistas públicos de YouTube. Un canal compartido puede aparecer como ejemplo para otros usuarios.'),
              value: channel.shareForTraining,
              onChanged: vm.busy
                  ? null
                  : (v) => vm.setTraining(channel.id, v),
            ),
          ],
        ),
      ),
    );
  }
}