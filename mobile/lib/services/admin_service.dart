import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/models/admin.dart';

class AdminService {
  AdminService(this._api);

  final ApiClient _api;

  Future<AdminStats> stats() async {
    final d = await _api.get('/admin/stats');
    return AdminStats.fromJson(d as Map<String, dynamic>);
  }

  Future<UsersPage> users({int limit = 50, int offset = 0}) async {
    final d = await _api.get('/admin/users',
        query: {'limit': '$limit', 'offset': '$offset'});
    return UsersPage.fromJson(d as Map<String, dynamic>);
  }

  Future<void> promote(int userId) async {
    await _api.post('/admin/users/$userId/promote', <String, dynamic>{});
  }

  /// null si no hay modelo activo.
  Future<ActiveModel?> activeModel() async {
    final d = await _api.get('/admin/model') as Map<String, dynamic>;
    final a = d['active'];
    return a is Map<String, dynamic> ? ActiveModel.fromJson(a) : null;
  }
}