/// Sesión devuelta por POST /auth/login. El rol lo decide el servidor: la app solo lo lee.
class AuthSession {
  const AuthSession({
    required this.token,
    required this.id,
    required this.username,
    required this.role,
  });

  final String token;
  final int id;
  final String username;
  final String role; // 'client' | 'admin'

  /// Solo sirve para elegir qué pantallas mostrar. El control real está en el backend.
  bool get isAdmin => role == 'admin';

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
        token: json['token'] as String,
        id: json['id'] as int,
        username: json['username'] as String,
        role: json['role'] as String,
      );
}