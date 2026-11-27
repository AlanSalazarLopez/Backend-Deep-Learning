import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/views/admin/admin_home_view.dart';
import 'package:yt_trends_app/views/client/client_home_view.dart';
import 'package:yt_trends_app/views/login_view.dart';

/// Decide la pantalla raíz según el estado de sesión y el rol que dijo el servidor.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthViewModel>();
    switch (auth.status) {
      case AuthStatus.unknown:
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      case AuthStatus.signedOut:
        return const LoginView();
      case AuthStatus.signedIn:
        return auth.session!.isAdmin
            ? const AdminHomeView()
            : const ClientHomeView();
    }
  }
}