import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/format.dart';
import 'package:yt_trends_app/models/admin.dart';
import 'package:yt_trends_app/viewmodels/admin_viewmodel.dart';
import 'package:yt_trends_app/widgets/activity_chart.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class AdminDashboardView extends StatelessWidget {
  const AdminDashboardView({super.key});

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AdminViewModel>();
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.load);
    }
    final s = vm.stats!;
    final t = s.totals;
    final theme = Theme.of(context);

    return RefreshIndicator(
      onRefresh: vm.load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (vm.error != null) ...[
            MessageBanner(vm.error!),
            const SizedBox(height: 12),
          ],
          Text('Resumen', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Stat('Usuarios', t.users),
              _Stat('Clientes', t.clients),
              _Stat('Admins', t.admins),
              _Stat('Canales de clientes', t.channels),
              _Stat('Videos de clientes', t.videos),
              _Stat('Predicciones', t.predictions),
              _Stat('Canales semilla', t.seedChannels),
              _Stat('Videos semilla', t.seedVideos),
            ],
          ),
          const SizedBox(height: 24),
          Text('Predicciones por día (últimos 14 días)',
              style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          ActivityChart(days: s.activityByDay),
          const SizedBox(height: 24),
          Text('Predicciones por nicho', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          _NicheBars(niches: s.byNiche),
          const SizedBox(height: 24),
          Text('Clientes', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          _ClientsTable(rows: s.perClient),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value);

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      width: 150,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('$value', style: theme.textTheme.headlineSmall),
              Text(label, style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

class _NicheBars extends StatelessWidget {
  const _NicheBars({required this.niches});

  final List<NicheStat> niches;

  @override
  Widget build(BuildContext context) {
    if (niches.isEmpty) return const Text('Sin datos por nicho todavía.');
    final theme = Theme.of(context);
    final maxN =
        niches.map((n) => n.nPredictions).fold<int>(1, (a, b) => b > a ? b : a);
    return Column(
      children: [
        for (final n in niches)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(n.name)),
                    Text('${n.nPredictions}', style: theme.textTheme.titleSmall),
                  ],
                ),
                const SizedBox(height: 4),
                LinearProgressIndicator(
                  value: n.nPredictions / maxN,
                  minHeight: 10,
                  borderRadius: BorderRadius.circular(5),
                ),
                const SizedBox(height: 2),
                Text('${n.nClients} clientes · ${n.nVideos} videos',
                    style: theme.textTheme.bodySmall),
              ],
            ),
          ),
      ],
    );
  }
}

class _ClientsTable extends StatelessWidget {
  const _ClientsTable({required this.rows});

  final List<ClientRow> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const Text('Aún no hay clientes.');
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Usuario')),
          DataColumn(label: Text('Canal(es)')),
          DataColumn(label: Text('Nicho')),
          DataColumn(label: Text('Pred.'), numeric: true),
          DataColumn(label: Text('Última actividad')),
        ],
        rows: [
          for (final c in rows)
            DataRow(cells: [
              DataCell(Text(c.username)),
              DataCell(Text(c.channelHandle ?? '—')),
              DataCell(Text(c.niche ?? '—')),
              DataCell(Text('${c.nPredictions}')),
              DataCell(Text(c.lastActivity != null
                  ? formatDateTime(c.lastActivity!)
                  : '—')),
            ]),
        ],
      ),
    );
  }
}