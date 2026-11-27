import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/services/channel_service.dart';
import 'package:yt_trends_app/services/prediction_service.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/viewmodels/channel_viewmodel.dart';
import 'package:yt_trends_app/viewmodels/predict_viewmodel.dart';
import 'package:yt_trends_app/views/client/channels_view.dart';
import 'package:yt_trends_app/views/client/history_view.dart';
import 'package:yt_trends_app/views/client/predict_view.dart';

/// Home del cliente: 3 pestañas. Los ViewModels viven solo mientras haya sesión de cliente
/// (al cerrar sesión se destruyen, así no se mezclan datos de dos usuarios).
class ClientHomeView extends StatefulWidget {
  const ClientHomeView({super.key});

  @override
  State<ClientHomeView> createState() => _ClientHomeViewState();
}

class _ClientHomeViewState extends State<ClientHomeView> {
  int _tab = 0;

  static const _titles = ['Mis canales', 'Probar una idea', 'Historial'];

  @override
  Widget build(BuildContext context) {
    final api = context.read<ApiClient>();
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<ChannelViewModel>(
          create: (_) => ChannelViewModel(ChannelService(api))..load(),
        ),
        ChangeNotifierProvider<PredictViewModel>(
          create: (_) => PredictViewModel(
              PredictionService(api), ChannelService(api))
            ..init(),
        ),
      ],
      child: Scaffold(
        appBar: AppBar(
          title: Text(_titles[_tab]),
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
          children: const [ChannelsView(), PredictView(), HistoryView()],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.video_library_outlined), label: 'Canales'),
            NavigationDestination(
                icon: Icon(Icons.lightbulb_outline), label: 'Probar idea'),
            NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          ],
        ),
      ),
    );
  }
}