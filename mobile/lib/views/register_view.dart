import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/widgets/message_banner.dart';

class RegisterView extends StatefulWidget {
  const RegisterView({super.key});

  @override
  State<RegisterView> createState() => _RegisterViewState();
}

class _RegisterViewState extends State<RegisterView> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  bool _hide = true;

  @override
  void dispose() {
    _name.dispose();
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final vm = context.read<AuthViewModel>();
    FocusScope.of(context).unfocus();
    vm.clearErrors(); // quita errores viejos del servidor antes de validar
    if (!_form.currentState!.validate()) return;

    final ok = await vm.register(
        username: _user.text, password: _pass.text, name: _name.text);
    if (!mounted) return;
    if (ok) {
      // Ya hay sesión: AuthGate muestra el home; cerramos esta pantalla.
      Navigator.of(context).popUntil((r) => r.isFirst);
    } else {
      // Si el 422 trajo errores por campo, se pintan en cada campo.
      _form.currentState!.validate();
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AuthViewModel>();
    return Scaffold(
      appBar: AppBar(title: const Text('Crear cuenta')),
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
                    TextFormField(
                      controller: _name,
                      enabled: !vm.loading,
                      textInputAction: TextInputAction.next,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Nombre',
                        prefixIcon: Icon(Icons.badge_outlined),
                        border: OutlineInputBorder(),
                      ),
                      validator: vm.validateName,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _user,
                      enabled: !vm.loading,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Usuario',
                        helperText: 'Letras, números, . o _ (3 a 30)',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                      validator: vm.validateUsername,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _pass,
                      enabled: !vm.loading,
                      obscureText: _hide,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Contraseña',
                        helperText: 'Mínimo 8 caracteres, con letras y números',
                        prefixIcon: const Icon(Icons.lock_outline),
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(_hide ? Icons.visibility : Icons.visibility_off),
                          onPressed: () => setState(() => _hide = !_hide),
                        ),
                      ),
                      validator: vm.validatePassword,
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
                          : const Text('Registrarme'),
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