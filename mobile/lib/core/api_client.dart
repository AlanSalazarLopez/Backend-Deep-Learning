import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:yt_trends_app/config.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/services/session_service.dart';

/// Único punto que habla HTTP con la API.
/// - Agrega `Authorization: Bearer` si hay sesión (auth: true).
/// - Decodifica UTF-8 con bodyBytes.
/// - Convierte errores en [ApiException] / [NetworkException].
/// - Ante 401 con sesión: borra la sesión y avisa (onSessionExpired).
class ApiClient {
  ApiClient({required this.session, http.Client? client})
      : _http = client ?? http.Client();

  final SessionService session;
  final http.Client _http;

  /// La conecta main.dart con AuthViewModel.handleSessionExpired.
  void Function()? onSessionExpired;

  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      _send('GET', path, query: query);

  Future<dynamic> post(String path, Object body, {bool auth = true}) =>
      _send('POST', path, body: body, auth: auth);

  Future<dynamic> put(String path, Object body) =>
      _send('PUT', path, body: body);

  Future<dynamic> delete(String path) => _send('DELETE', path);

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool auth = true,
  }) async {
    final uri = Uri.parse('$apiBaseUrl$path').replace(queryParameters: query);
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) headers['Content-Type'] = 'application/json';
    if (auth) {
      final token = await session.token();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }

    late http.Response res;
    try {
      final req = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) req.body = jsonEncode(body);
      final streamed = await _http.send(req).timeout(apiTimeout);
      res = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw const NetworkException(
          'El servidor tardó demasiado en responder. Si estaba dormido, intenta de nuevo en unos segundos.');
    } on Exception {
      throw const NetworkException(
          'No pudimos conectar con el servidor. Revisa tu internet.');
    }

    final data = _decode(res);

    // 401 con token = sesión vencida. (En el login, auth=false: es "credenciales incorrectas".)
    if (res.statusCode == 401 && auth) {
      await session.clear();
      onSessionExpired?.call();
      throw const ApiException('Tu sesión expiró. Inicia sesión de nuevo.',
          statusCode: 401);
    }
    if (res.statusCode >= 400) throw _toException(res.statusCode, data);
    return data;
  }

  dynamic _decode(http.Response res) {
    if (res.bodyBytes.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(res.bodyBytes));
    } catch (_) {
      return null; // p. ej. HTML de error de Render mientras despierta
    }
  }

  ApiException _toException(int status, dynamic data) {
    var message = status >= 500
        ? 'El servidor tuvo un problema. Intenta de nuevo en un momento.'
        : 'Error inesperado ($status).';
    final fields = <String, String>{};

    if (data is Map) {
      final detail = data['detail'];
      if (detail is String && detail.isNotEmpty) {
        message = detail;
      } else if (detail is List && detail.isNotEmpty) {
        final parts = detail
            .map((e) => e is Map ? (e['msg'] ?? e['message'] ?? '').toString() : e.toString())
            .where((s) => s.isNotEmpty)
            .toList();
        if (parts.isNotEmpty) message = parts.join('. ');
      }
      final errors = data['errors'];
      if (errors is List) {
        for (final e in errors) {
          if (e is Map && e['field'] != null && e['message'] != null) {
            final field = e['field'].toString().split('.').last;
            fields.putIfAbsent(field, () => e['message'].toString());
          }
        }
      }
    }
    return ApiException(message, statusCode: status, fieldErrors: fields);
  }
}