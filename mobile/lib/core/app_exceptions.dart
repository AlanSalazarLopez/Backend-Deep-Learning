/// Jerarquía única de errores de la app. `message` siempre es legible para el usuario.
abstract class AppException implements Exception {
  const AppException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Sin internet, timeout o servidor inalcanzable.
class NetworkException extends AppException {
  const NetworkException(super.message);
}

/// El servidor respondió con error (4xx/5xx).
class ApiException extends AppException {
  const ApiException(
    super.message, {
    required this.statusCode,
    this.fieldErrors = const {},
  });

  final int statusCode;

  /// Errores por campo de un 422: {"title": "Debe tener entre 3 y 100 caracteres"}.
  final Map<String, String> fieldErrors;
}