/// URL base de la API. Por defecto, Render.
/// Para otra URL al compilar: flutter run --dart-define=API_URL=http://10.0.2.2:8000
const String apiBaseUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'https://backend-deep-learning-c4x3.onrender.com',
);

/// 60 s: aguanta el arranque en frío de Render (plan gratis).
const Duration apiTimeout = Duration(seconds: 60);