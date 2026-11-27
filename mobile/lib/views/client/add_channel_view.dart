import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/models/channel.dart';
import 'package:yt_trends_app/viewmodels/channel_viewmodel.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

/// Paso 1: @handle + consentimiento. Paso 2 (cuando ya existe `vm.created`): elegir nicho.
class AddChannelView extends StatefulWidget {
  const AddChannelView({super.key});

  @override
  State<AddChannelView> createState() => _AddChannelViewState();
}

class _AddChannelViewState extends State<AddChannelView> {
  final _form = GlobalKey<FormState>();
  final _handle = TextEditingController();
  bool _share = true;

  @override
  void dispose() {
    _handle.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final vm = context.read<ChannelViewModel>();
    FocusScope.of(context).unfocus();
    vm.clearErrors();
    if (!_form.currentState!.validate()) return;
    final ok = await vm.addChannel(_handle.text, share: _share);
    if (!mounted) return;
    if (!ok) _form.currentState!.validate(); // pinta el 422 del servidor, si hubo
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<ChannelViewModel>();
    final theme = Theme.of(context);
    final created = vm.created;

    return Scaffold(
      appBar: AppBar(title: Text(created == null ? 'Agregar canal' : 'Elige tu nicho')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: created != null
              ? _NicheStep(channel: created)
              : Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextFormField(
                        controller: _handle,
                        enabled: !vm.busy,
                        autocorrect: false,
                        onFieldSubmitted: (_) => _submit(),
                        decoration: const InputDecoration(
                          labelText: '@handle de tu canal',
                          hintText: '@micanal',
                          prefixIcon: Icon(Icons.alternate_email),
                          border: OutlineInputBorder(),
                        ),
                        validator: vm.validateHandle,
                      ),
                      const SizedBox(height: 12),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text(
                            'Usar los datos públicos de mi canal para mejorar los análisis'),
                        value: _share,
                        onChanged:
                            vm.busy ? null : (v) => setState(() => _share = v),
                      ),
                      Text(
                        'Solo usamos datos públicos de YouTube (títulos, fechas y vistas) para entrenar el modelo y calcular estadísticas del nicho. Los títulos y el @handle de un canal compartido podrían aparecer como ejemplos para otros usuarios. Puedes cambiarlo cuando quieras desde tu lista de canales.',
                        style: theme.textTheme.bodySmall,
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
                            : const Text('Agregar canal'),
                      ),
                      if (vm.busy) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Leyendo tu canal en YouTube… puede tardar hasta un minuto.',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ],
                  ),
                ),
        ),
      ),
    );
  }
}

class _NicheStep extends StatefulWidget {
  const _NicheStep({required this.channel});

  final Channel channel;

  @override
  State<_NicheStep> createState() => _NicheStepState();
}

class _NicheStepState extends State<_NicheStep> {
  int? _niche;

  @override
  void initState() {
    super.initState();
    final vm = context.read<ChannelViewModel>();
    final s = widget.channel.suggestedNicheId;
    _niche = vm.niches.any((n) => n.id == s) ? s : null;
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<ChannelViewModel>();
    final ch = widget.channel;
    final suggested = _niche != null && _niche == ch.suggestedNicheId;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        MessageBanner(
          'Canal agregado: ${ch.title ?? ch.handle}. Cargamos ${ch.videosLoaded ?? 0} videos.',
          isError: false,
        ),
        const SizedBox(height: 12),
        if (!ch.isSpanish) ...[
          MessageBanner(
            'Este canal parece estar en "${ch.language}". El modelo se entrena solo con títulos en español, así que sus videos no se usarán para entrenar.',
            isError: false,
          ),
          const SizedBox(height: 12),
        ],
        Text(
          suggested
              ? 'Te sugerimos este nicho porque es la categoría más frecuente de tus videos. Puedes cambiarlo.'
              : 'Elige el nicho que mejor describe tu canal.',
        ),
        const SizedBox(height: 12),
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
        ),
        const SizedBox(height: 16),
        if (vm.error != null) ...[
          MessageBanner(vm.error!),
          const SizedBox(height: 12),
        ],
        FilledButton(
          onPressed: (_niche == null || vm.busy)
              ? null
              : () async {
                  final ok = await vm.setNiche(ch.id, _niche!);
                  if (ok && context.mounted) Navigator.of(context).pop();
                },
          child: const Text('Confirmar nicho'),
        ),
        TextButton(
          onPressed: vm.busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Omitir por ahora'),
        ),
      ],
    );
  }
}