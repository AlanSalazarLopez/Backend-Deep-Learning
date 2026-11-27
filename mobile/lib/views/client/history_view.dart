import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/format.dart';
import 'package:yt_trends_app/models/prediction.dart';
import 'package:yt_trends_app/viewmodels/predict_viewmodel.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class HistoryView extends StatelessWidget {
  const HistoryView({super.key});

  String _when(Prediction p) {
    final d = p.publishWeekday;
    final day = (d != null && d >= 0 && d < 7) ? '${weekdayNames[d]} ' : '';
    return '$day${p.publishHour}:00';
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<PredictViewModel>();
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.init);
    }
    return RefreshIndicator(
      onRefresh: vm.refreshHistory,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (vm.error != null) ...[
            MessageBanner(vm.error!),
            const SizedBox(height: 12),
          ],
          if (vm.history.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 48),
              child: Text(
                'Aún no has probado ninguna idea.\nVe a la pestaña "Probar idea".',
                textAlign: TextAlign.center,
              ),
            ),
          for (final p in vm.history)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ExpansionTile(
                leading: CircleAvatar(child: Text(p.score.round().toString())),
                title: Text(p.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                subtitle: Text(
                  '${vm.nicheName(p.nicheId) ?? 'Nicho ${p.nicheId}'} · ${formatDuration(p.durationS)} · ${_when(p)}\n${formatDateTime(p.createdAt)}',
                ),
                childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                expandedAlignment: Alignment.centerLeft,
                children: [
                  if (p.topTerms.isEmpty)
                    const Text('Sin palabras destacadas.')
                  else
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      children: [for (final t in p.topTerms) Chip(label: Text(t))],
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}