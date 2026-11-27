import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/views/register_view.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class LoginView extends StatefulWidget {
  const LoginView({super.key});

  @override
  State<LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends State<LoginView> {
  final _form = GlobalKey<FormState>();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  bool _hide = true;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_form.currentState!.validate()) return;
    // Si sale bien, AuthGate cambia solo a la pantalla según el rol.
    await context.read<AuthViewModel>().login(_user.text, _pass.text);
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AuthViewModel>();
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Icon(Icons.trending_up, size: 64, color: theme.colorScheme.primary),
                    const SizedBox(height: 12),
                    Text('YT Trends',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineMedium),
                    const SizedBox(height: 4),
                    Text('Ideas que rinden para creadores de YouTube',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyMedium),
                    const SizedBox(height: 24),
                    if (vm.notice != null) ...[
                      MessageBanner(vm.notice!, isError: false),
                      const SizedBox(height: 12),
                    ],
                    TextFormField(
                      controller: _user,
                      enabled: !vm.loading,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Usuario',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                      validator: vm.validateLoginUser,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _pass,
                      enabled: !vm.loading,
                      obscureText: _hide,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Contraseña',
                        prefixIcon: const Icon(Icons.lock_outline),
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(_hide ? Icons.visibility : Icons.visibility_off),
                          onPressed: () => setState(() => _hide = !_hide),
                        ),
                      ),
                      validator: vm.validateLoginPassword,
                    ),
                    const SizedBox(height: 16),
                    if (vm.error != null) ...[
                      MessageBanner(vm.error!),
                      const SizedBox(height: 12),
                    ],
                    FilledButton(
                      onPressed: vm.loading ? null : _submit,
                      child: vm.loading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Iniciar sesión'),
                    ),
                    if (vm.loading) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Conectando… si el servidor estaba dormido, la primera vez puede tardar hasta un minuto.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: vm.loading
                          ? null
                          : () {
                              vm.clearErrors();
                              Navigator.of(context).push(MaterialPageRoute(
                                  builder: (_) => const RegisterView()));
                            },
                      child: const Text('Crear cuenta'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}