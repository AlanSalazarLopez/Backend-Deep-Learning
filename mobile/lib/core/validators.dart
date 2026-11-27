/// Validadores puros (sin estado). Mismas reglas que el backend (Pydantic).
class Validators {
  static final _username = RegExp(r'^[A-Za-z0-9._]{3,30}$');
  static final _handle = RegExp(r'^@?[A-Za-z0-9._-]{3,30}$');
  static final _letter = RegExp(r'[A-Za-z]');
  static final _digit = RegExp(r'\d');
  static final _hashtag = RegExp(r'#\S+');

  static String? required(String? v, String message) =>
      (v == null || v.trim().isEmpty) ? message : null;

  static String? username(String? v) {
    final t = (v ?? '').trim();
    if (!_username.hasMatch(t)) {
      return 'El usuario debe tener entre 3 y 30 caracteres (letras, números, . o _)';
    }
    return null;
  }

  static String? name(String? v) {
    final t = (v ?? '').trim();
    if (t.isEmpty || t.length > 80) {
      return 'Escribe tu nombre (máximo 80 caracteres)';
    }
    return null;
  }

  /// Contraseña NUEVA (registro). En el login solo se exige que no esté vacía.
  static String? newPassword(String? v) {
    final t = v ?? '';
    if (t.length < 8 ||
        t.length > 128 ||
        !_letter.hasMatch(t) ||
        !_digit.hasMatch(t)) {
      return 'Usa de 8 a 128 caracteres, con letras y números';
    }
    return null;
  }

  static String? handle(String? v) {
    final t = (v ?? '').trim();
    if (!_handle.hasMatch(t)) {
      return 'Escribe tu @handle, por ejemplo @micanal';
    }
    return null;
  }

  /// Solo lo simple; la regla completa ("Parte N", etc.) la aplica el backend con un 422.
  static String? title(String? v) {
    final t = (v ?? '').trim();
    if (t.length < 3 || t.length > 100) {
      return 'El título debe tener entre 3 y 100 caracteres';
    }
    if (t.replaceAll(_hashtag, '').trim().isEmpty) {
      return 'Escribe un título con palabras, no solo hashtags';
    }
    return null;
  }

  /// El backend exige 181 a 7200 s; en minutos enteros eso es de 4 a 120.
  static String? durationMinutes(String? v) {
    final n = int.tryParse((v ?? '').trim());
    if (n == null || n < 4 || n > 120) {
      return 'La duración va de 4 a 120 minutos (número entero)';
    }
    return null;
  }

  static String? hour(String? v) {
    final n = int.tryParse((v ?? '').trim());
    if (n == null || n < 0 || n > 23) {
      return 'La hora debe estar entre 0 y 23';
    }
    return null;
  }
}