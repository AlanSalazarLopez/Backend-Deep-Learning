import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:yt_trends_app/models/user.dart';

/// Guarda y borra la sesión en almacenamiento seguro.
class SessionService {
  SessionService([FlutterSecureStorage? storage])
      : _s = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _s;

  static const _kToken = 'session_token';
  static const _kId = 'session_user_id';
  static const _kUser = 'session_username';
  static const _kRole = 'session_role';

  Future<void> save(AuthSession s) async {
    await _s.write(key: _kToken, value: s.token);
    await _s.write(key: _kId, value: s.id.toString());
    await _s.write(key: _kUser, value: s.username);
    await _s.write(key: _kRole, value: s.role);
  }

  Future<String?> token() async {
    try {
      return await _s.read(key: _kToken);
    } catch (_) {
      return null;
    }
  }

  /// Devuelve la sesión guardada o null. Si el almacenamiento está corrupto, la limpia.
  Future<AuthSession?> load() async {
    try {
      final token = await _s.read(key: _kToken);
      final id = int.tryParse(await _s.read(key: _kId) ?? '');
      final username = await _s.read(key: _kUser);
      final role = await _s.read(key: _kRole);
      if (token == null || id == null || username == null || role == null) {
        return null;
      }
      return AuthSession(token: token, id: id, username: username, role: role);
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> clear() async {
    for (final k in [_kToken, _kId, _kUser, _kRole]) {
      try {
        await _s.delete(key: k);
      } catch (_) {}
    }
  }
}