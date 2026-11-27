import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/services/auth_service.dart';
import 'package:yt_trends_app/services/session_service.dart';
import 'package:yt_trends_app/viewmodels/auth_viewmodel.dart';
import 'package:yt_trends_app/views/auth_gate.dart';

final navigatorKey = GlobalKey<NavigatorState>();

void main() => runApp(const YtTrendsApp());

class YtTrendsApp extends StatefulWidget {
  const YtTrendsApp({super.key});

  @override
  State<YtTrendsApp> createState() => _YtTrendsAppState();
}

class _YtTrendsAppState extends State<YtTrendsApp> {
  late final SessionService _session = SessionService();
  late final ApiClient _api = ApiClient(session: _session);
  late final AuthViewModel _auth = AuthViewModel(AuthService(_api, _session));

  @override
  void initState() {
    super.initState();
    // 401 en cualquier llamada -> AuthViewModel cierra la sesión.
    _api.onSessionExpired = _auth.handleSessionExpired;
    // Al cerrar sesión, se cierran las pantallas abiertas encima del home.
    _auth.onSignedOut =
        () => navigatorKey.currentState?.popUntil((r) => r.isFirst);
    _auth.restore();
  }

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: _api),
        ChangeNotifierProvider<AuthViewModel>.value(value: _auth),
      ],
      child: MaterialApp(
        title: 'YT Trends',
        navigatorKey: navigatorKey,
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        home: const AuthGate(),
      ),
    );
  }
}