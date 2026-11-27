import 'package:flutter/foundation.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/core/validators.dart';
import 'package:yt_trends_app/models/niche.dart';
import 'package:yt_trends_app/models/prediction.dart';
import 'package:yt_trends_app/services/channel_service.dart';
import 'package:yt_trends_app/services/prediction_service.dart';

/// "Probar una idea" (experimental) + historial de predicciones.
class PredictViewModel extends ChangeNotifier {
  PredictViewModel(this._predictions, this._channels);

  final PredictionService _predictions;
  final ChannelService _channels;

  List<Niche> niches = [];
  List<Prediction> history = [];
  Prediction? result;
  bool loading = false;
  bool loaded = false;
  bool busy = false;
  String? error;
  Map<String, String> _fieldErrors = {};

  String? nicheName(int id) {
    for (final n in niches) {
      if (n.id == id) return n.name;
    }
    return null;
  }

  /// Aviso honesto sobre el modelo (si el servidor no manda model_info, se asume no fiable).
  String get experimentalNotice {
    final info = result?.modelInfo;
    final auc = info?.auc;
    final aucText = auc != null ? ' (AUC ${auc.toStringAsFixed(2)})' : '';
    if (info != null && info.reliable) {
      return 'Modelo con validación en canales no vistos$aucText.';
    }
    return 'Función experimental: en nuestras pruebas este modelo no supera al azar de forma fiable$aucText. Úsalo como referencia, no como decisión.';
  }

  // ---- Validaciones ----
  String? validateNiche(int? v) => v == null ? 'Elige un nicho' : null;
  String? validateTitle(String? v) =>
      Validators.title(v) ?? _fieldErrors['title'];
  String? validateMinutes(String? v) =>
      Validators.durationMinutes(v) ?? _fieldErrors['duration_s'];
  String? validateHour(String? v) =>
      Validators.hour(v) ?? _fieldErrors['publish_hour'];

  void clearErrors() {
    error = null;
    _fieldErrors = {};
    notifyListeners();
  }

  Future<void> init() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final r =
          await Future.wait<Object>([_channels.niches(), _predictions.mine()]);
      niches = r[0] as List<Niche>;
      history = r[1] as List<Prediction>;
      loaded = true;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos cargar tus datos.';
    }
    loading = false;
    notifyListeners();
  }

  Future<void> refreshHistory() async {
    try {
      history = await _predictions.mine();
      error = null;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos actualizar el historial.';
    }
    notifyListeners();
  }

  Future<bool> predict({
    required int nicheId,
    required String title,
    required int minutes,
    required int hour,
    int? weekday,
  }) async {
    busy = true;
    error = null;
    _fieldErrors = {};
    notifyListeners();
    try {
      final p = await _predictions.predict(
        nicheId: nicheId,
        title: title.trim(),
        durationS: minutes * 60,
        hour: hour,
        weekday: weekday,
      );
      result = p;
      history = [p, ...history];
      busy = false;
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
    busy = false;
    notifyListeners();
    return false;
  }
}