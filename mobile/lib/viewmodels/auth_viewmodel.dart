import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/core/validators.dart';
import 'package:yt_trends_app/models/user.dart';
import 'package:yt_trends_app/services/auth_service.dart';

enum AuthStatus { unknown, signedOut, signedIn }

/// Estado de sesión + acciones de login/registro + validaciones de entrada.
class AuthViewModel extends ChangeNotifier {
  AuthViewModel(this._service);

  final AuthService _service;

  AuthStatus status = AuthStatus.unknown;
  AuthSession? session;
  bool loading = false;
  String? error; // error general (credenciales, conexión, usuario repetido...)
  String? notice; // aviso informativo (p. ej. sesión expirada)
  Map<String, String> _fieldErrors = {};

  /// La conecta main.dart para cerrar pantallas abiertas al terminar la sesión.
  VoidCallback? onSignedOut;

  // ---- Validaciones (la Form de la vista las llama desde `validator`) ----
  String? validateLoginUser(String? v) =>
      Validators.required(v, 'Escribe tu usuario');
  String? validateLoginPassword(String? v) =>
      (v == null || v.isEmpty) ? 'Escribe tu contraseña' : null;

  // Registro: regla local primero; si pasa, muestra el error de campo del servidor (422).
  String? validateUsername(String? v) =>
      Validators.username(v) ?? _fieldErrors['username'];
  String? validateName(String? v) =>
      Validators.name(v) ?? _fieldErrors['name'];
  String? validatePassword(String? v) =>
      Validators.newPassword(v) ?? _fieldErrors['password'];

  void clearErrors() {
    error = null;
    _fieldErrors = {};
    notifyListeners();
  }

  // ---- Acciones ----
  Future<void> restore() async {
    session = await _service.restore();
    status = session == null ? AuthStatus.signedOut : AuthStatus.signedIn;
    notifyListeners();
  }

  Future<bool> login(String username, String password) => _run(() async {
        session = await _service.login(username.trim(), password);
        status = AuthStatus.signedIn;
      });

  /// Registra y entra directo (la cuenta siempre nace como cliente).
  Future<bool> register({
    required String username,
    required String password,
    required String name,
  }) =>
      _run(() async {
        final u = username.trim();
        await _service.register(username: u, password: password, name: name.trim());
        session = await _service.login(u, password);
        status = AuthStatus.signedIn;
      });

  Future<void> logout() async {
    await _service.logout();
    _signedOut();
  }

  /// La llama ApiClient cuando el servidor responde 401 con una sesión guardada.
  void handleSessionExpired() {
    _signedOut(message: 'Tu sesión expiró. Inicia sesión de nuevo.');
  }

  void _signedOut({String? message}) {
    session = null;
    status = AuthStatus.signedOut;
    error = null;
    notice = message;
    _fieldErrors = {};
    onSignedOut?.call();
    notifyListeners();
  }

  Future<bool> _run(Future<void> Function() action) async {
    loading = true;
    error = null;
    notice = null;
    _fieldErrors = {};
    notifyListeners();
    try {
      if (!await _online()) {
        throw const NetworkException('Sin conexión a internet. Revísala e intenta de nuevo.');
      }
      await action();
      loading = false;
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      _fieldErrors = e.fieldErrors;
      error = e.fieldErrors.isEmpty ? e.message : null;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'Ocurrió un error inesperado. Intenta de nuevo.';
    }
    loading = false;
    notifyListeners();
    return false;
  }

  Future<bool> _online() async {
    try {
      final r = await Connectivity().checkConnectivity();
      return !r.every((e) => e == ConnectivityResult.none);
    } catch (_) {
      return true; // si no se puede comprobar, que decida la petición
    }
  }
}