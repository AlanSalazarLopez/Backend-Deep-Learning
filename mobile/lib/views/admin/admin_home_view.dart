import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/services/admin_service.dart';
import 'package:yt_trends_app/viewmodels/admin_viewmodel.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/views/admin/admin_dashboard_view.dart';
import 'package:yt_trends_app/views/admin/admin_model_view.dart';
import 'package:yt_trends_app/views/admin/admin_users_view.dart';

/// Home del admin: Panel, Usuarios y Modelo. El control real de permisos está en el backend.
class AdminHomeView extends StatefulWidget {
  const AdminHomeView({super.key});

  @override
  State<AdminHomeView> createState() => _AdminHomeViewState();
}

class _AdminHomeViewState extends State<AdminHomeView> {
  int _tab = 0;

  static const _titles = ['Panel', 'Usuarios', 'Modelo'];

  @override
  Widget build(BuildContext context) {
    final api = context.read<ApiClient>();
    return ChangeNotifierProvider<AdminViewModel>(
      create: (_) => AdminViewModel(AdminService(api))..load(),
      child: Scaffold(
        appBar: AppBar(
          title: Text('Admin · ${_titles[_tab]}'),
          actions: [
            IconButton(
              tooltip: 'Cerrar sesión',
              icon: const Icon(Icons.logout),
              onPressed: () => context.read<AuthViewModel>().logout(),
            ),
          ],
        ),
        body: IndexedStack(
          index: _tab,
          children: const [
            AdminDashboardView(),
            AdminUsersView(),
            AdminModelView(),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.dashboard_outlined), label: 'Panel'),
            NavigationDestination(
                icon: Icon(Icons.people_outline), label: 'Usuarios'),
            NavigationDestination(
                icon: Icon(Icons.psychology_outlined), label: 'Modelo'),
          ],
        ),
      ),
    );
  }
}