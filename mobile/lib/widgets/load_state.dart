import 'package:flutter/material.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

/// Pantalla de carga inicial (con aviso de arranque en frío) o de error con reintento.
class LoadState extends StatelessWidget {
  const LoadState({
    super.key,
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final bool loading;
  final String? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: loading
            ? const Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text(
                    'Cargando… si el servidor estaba dormido, puede tardar hasta un minuto.',
                    textAlign: TextAlign.center,
                  ),
                ],
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  MessageBanner(error ?? 'No pudimos cargar los datos.'),
                  const SizedBox(height: 12),
                  FilledButton(onPressed: onRetry, child: const Text('Reintentar')),
                ],
              ),
      ),
    );
  }
}