import 'package:flutter/foundation.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/models/admin.dart';
import 'package:yt_trends_app/services/admin_service.dart';

/// Panel de admin: estadísticas, usuarios (promover) y modelo activo.
class AdminViewModel extends ChangeNotifier {
  AdminViewModel(this._service);

  final AdminService _service;

  static const _pageSize = 50;

  AdminStats? stats;
  List<AdminUser> users = [];
  int usersTotal = 0;
  ActiveModel? model;
  bool loading = false;
  bool loaded = false;
  bool busy = false; // promover / cargar más
  String? error;

  bool get hasMoreUsers => users.length < usersTotal;

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final r = await Future.wait<Object?>([
        _service.stats(),
        _service.users(limit: _pageSize),
        _service.activeModel(),
      ]);
      stats = r[0] as AdminStats;
      final page = r[1] as UsersPage;
      users = page.items;
      usersTotal = page.total;
      model = r[2] as ActiveModel?;
      loaded = true;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos cargar el panel.';
    }
    loading = false;
    notifyListeners();
  }

  Future<void> loadMoreUsers() async {
    if (busy || !hasMoreUsers) return;
    busy = true;
    error = null;
    notifyListeners();
    try {
      final page =
          await _service.users(limit: _pageSize, offset: users.length);
      users = [...users, ...page.items];
      usersTotal = page.total;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos cargar más usuarios.';
    }
    busy = false;
    notifyListeners();
  }

  /// El cambio persiste en la BD; el usuario ejerce permisos de admin al volver a iniciar sesión.
  Future<bool> promote(AdminUser u) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      await _service.promote(u.id);
      // Refresca totales y la primera página de usuarios.
      final r = await Future.wait<Object?>([
        _service.stats(),
        _service.users(limit: _pageSize),
      ]);
      stats = r[0] as AdminStats;
      final page = r[1] as UsersPage;
      users = page.items;
      usersTotal = page.total;
      busy = false;
      notifyListeners();
      return true;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos promover al usuario.';
    }
    busy = false;
    notifyListeners();
    return false;
  }
}