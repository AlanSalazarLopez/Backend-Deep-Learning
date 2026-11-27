import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/format.dart';
import 'package:yt_trends_app/viewmodels/admin_viewmodel.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

/// Modelo activo y sus métricas (solo lectura; se entrena con scripts.train_model).
class AdminModelView extends StatelessWidget {
  const AdminModelView({super.key});

  String _n(dynamic v, [int d = 3]) => v is num ? v.toStringAsFixed(d) : '—';

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AdminViewModel>();
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.load);
    }
    final m = vm.model;
    if (m == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'No hay modelo activo.\nEntrénalo con: python -m scripts.train_model',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    final x = m.metrics;
    final auc = x['auc_mean'];
    final std = x['auc_std'];
    final fuentes = (x['fuentes'] is Map)
        ? (x['fuentes'] as Map).cast<String, dynamic>()
        : <String, dynamic>{};
    final rows = <MapEntry<String, String>>[
      MapEntry('Modelo', '#${m.id}'),
      MapEntry('Entrenado',
          m.trainedAt != null ? formatDateTime(m.trainedAt!) : '—'),
      MapEntry('Videos / canales', '${m.nVideos} / ${m.nChannels}'),
      MapEntry('AUC en canales no vistos',
          '${_n(auc)}${std is num ? ' ± ${_n(std)}' : ''}'),
      MapEntry('AUC temporal', _n(x['temporal_auc'])),
      MapEntry('Precisión en el 10 % superior', _n(x['precision_at_10'])),
      MapEntry('Lift en el 10 % superior', _n(x['lift_at_10'], 2)),
      MapEntry('Tasa base', _n(x['base_rate'])),
      if (fuentes.isNotEmpty) ...[
        MapEntry('Canales semilla', '${fuentes['canales_semilla'] ?? '—'}'),
        MapEntry('Canales de clientes', '${fuentes['canales_clientes'] ?? '—'}'),
        MapEntry('Videos semilla', '${fuentes['videos_semilla'] ?? '—'}'),
        MapEntry('Videos de clientes', '${fuentes['videos_clientes'] ?? '—'}'),
      ],
    ];

    return RefreshIndicator(
      onRefresh: vm.load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (auc is num && auc < 0.55) ...[
            const MessageBanner(
              'El AUC no llega al umbral de confiabilidad del plan (0.55). Por eso la app muestra la predicción como función experimental a los clientes.',
              isError: false,
            ),
            const SizedBox(height: 12),
          ],
          Card(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                children: [
                  for (final r in rows)
                    ListTile(
                      dense: true,
                      title: Text(r.key),
                      trailing: Text(r.value,
                          style: Theme.of(context).textTheme.titleSmall),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}