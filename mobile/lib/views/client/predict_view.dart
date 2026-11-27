import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/format.dart';
import 'package:yt_trends_app/models/prediction.dart';
import 'package:yt_trends_app/viewmodels/predict_viewmodel.dart';
import 'package:yt_trends_app/widgets/load_state.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class PredictView extends StatefulWidget {
  const PredictView({super.key});

  @override
  State<PredictView> createState() => _PredictViewState();
}

class _PredictViewState extends State<PredictView> {
  final _form = GlobalKey<FormState>();
  final _resultKey = GlobalKey();
  final _title = TextEditingController();
  final _minutes = TextEditingController();
  final _hour = TextEditingController();
  int? _niche;
  int _weekday = -1; // -1 = hoy (no se manda; el backend usa el día actual)

  @override
  void dispose() {
    _title.dispose();
    _minutes.dispose();
    _hour.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final vm = context.read<PredictViewModel>();
    FocusScope.of(context).unfocus();
    vm.clearErrors();
    if (!_form.currentState!.validate()) return;

    final ok = await vm.predict(
      nicheId: _niche!,
      title: _title.text,
      minutes: int.parse(_minutes.text.trim()),
      hour: int.parse(_hour.text.trim()),
      weekday: _weekday < 0 ? null : _weekday,
    );
    if (!mounted) return;
    if (ok) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final c = _resultKey.currentContext;
        if (c != null) {
          Scrollable.ensureVisible(c, duration: const Duration(milliseconds: 300));
        }
      });
    } else {
      _form.currentState!.validate(); // pinta el 422 del servidor, si hubo
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<PredictViewModel>();
    final theme = Theme.of(context);
    if (!vm.loaded) {
      return LoadState(loading: vm.loading, error: vm.error, onRetry: vm.init);
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            MessageBanner(vm.experimentalNotice, isError: false),
            const SizedBox(height: 4),
            Text(
              'Probamos videos de más de 3 minutos y hasta 2 horas. No evaluamos Shorts.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<int>(
              initialValue: _niche,
              decoration: const InputDecoration(
                  labelText: 'Nicho', border: OutlineInputBorder()),
              hint: const Text('Elige un nicho'),
              items: [
                for (final n in vm.niches)
                  DropdownMenuItem(value: n.id, child: Text(n.name)),
              ],
              onChanged: vm.busy ? null : (v) => setState(() => _niche = v),
              validator: vm.validateNiche,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _title,
              enabled: !vm.busy,
              maxLength: 100,
              decoration: const InputDecoration(
                labelText: 'Título de tu idea',
                border: OutlineInputBorder(),
              ),
              validator: vm.validateTitle,
            ),
            const SizedBox(height: 4),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _minutes,
                    enabled: !vm.busy,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Duración (min)',
                      helperText: '4 a 120',
                      border: OutlineInputBorder(),
                    ),
                    validator: vm.validateMinutes,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _hour,
                    enabled: !vm.busy,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Hora (0-23)',
                      helperText: 'Hora de México',
                      border: OutlineInputBorder(),
                    ),
                    validator: vm.validateHour,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              initialValue: _weekday,
              decoration: const InputDecoration(
                  labelText: 'Día de publicación', border: OutlineInputBorder()),
              items: [
                const DropdownMenuItem(value: -1, child: Text('Hoy (por defecto)')),
                for (var i = 0; i < 7; i++)
                  DropdownMenuItem(value: i, child: Text(weekdayNames[i])),
              ],
              onChanged:
                  vm.busy ? null : (v) => setState(() => _weekday = v ?? -1),
            ),
            const SizedBox(height: 16),
            if (vm.error != null) ...[
              MessageBanner(vm.error!),
              const SizedBox(height: 12),
            ],
            FilledButton(
              onPressed: vm.busy ? null : _submit,
              child: vm.busy
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Calcular puntuación'),
            ),
            if (vm.result != null) ...[
              const SizedBox(height: 24),
              _ResultCard(key: _resultKey, p: vm.result!),
            ],
          ],
        ),
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({super.key, required this.p});

  final Prediction p;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Puntuación', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(p.score.round().toString(),
                    style: theme.textTheme.displayMedium),
                Padding(
                  padding: const EdgeInsets.only(bottom: 8, left: 4),
                  child: Text('/ 100', style: theme.textTheme.titleMedium),
                ),
              ],
            ),
            LinearProgressIndicator(value: (p.score / 100).clamp(0.0, 1.0)),
            const SizedBox(height: 12),
            Text(
              'Es relativa: compara tu título con lo normal de un canal de este nicho. No es una probabilidad ni una promesa de vistas.',
              style: theme.textTheme.bodySmall,
            ),
            if (p.topTerms.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Palabras del título que más pesan',
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [for (final t in p.topTerms) Chip(label: Text(t))],
              ),
            ],
          ],
        ),
      ),
    );
  }
}