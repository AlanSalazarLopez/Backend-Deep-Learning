import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/models/user.dart';
import 'package:yt_trends_app/services/session_service.dart';

class AuthService {
  AuthService(this._api, this._session);

  final ApiClient _api;
  final SessionService _session;

  Future<AuthSession> login(String username, String password) async {
    final data = await _api.post(
      '/auth/login',
      {'username': username, 'password': password},
      auth: false,
    );
    final s = AuthSession.fromJson(data as Map<String, dynamic>);
    await _session.save(s);
    return s;
  }

  /// El cuerpo NO lleva `role` (el backend lo rechazaría con 422).
  Future<void> register({
    required String username,
    required String password,
    required String name,
  }) async {
    await _api.post(
      '/auth/register',
      {'username': username, 'password': password, 'name': name},
      auth: false,
    );
  }

  Future<AuthSession?> restore() => _session.load();

  Future<void> logout() => _session.clear();
}