import 'package:flutter/foundation.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/core/validators.dart';
import 'package:yt_trends_app/models/channel.dart';
import 'package:yt_trends_app/models/niche.dart';
import 'package:yt_trends_app/services/channel_service.dart';

/// Canales del cliente (hasta 5): listar, agregar, elegir nicho, consentimiento y borrar.
class ChannelViewModel extends ChangeNotifier {
  ChannelViewModel(this._service);

  final ChannelService _service;

  static const maxChannels = 5;

  List<Channel> channels = [];
  List<Niche> niches = [];
  bool loading = false; // carga de la lista
  bool loaded = false;
  bool busy = false; // acción en curso (agregar, borrar, cambiar...)
  String? error;
  Channel? created; // último canal agregado (para el paso de elegir nicho)
  Map<String, String> _fieldErrors = {};

  bool get canAdd => channels.length < maxChannels;

  String? nicheName(int? id) {
    for (final n in niches) {
      if (n.id == id) return n.name;
    }
    return null;
  }

  String? validateHandle(String? v) =>
      Validators.handle(v) ?? _fieldErrors['handle'];

  void clearErrors() {
    error = null;
    _fieldErrors = {};
    notifyListeners();
  }

  void startAdd() {
    created = null;
    error = null;
    _fieldErrors = {};
    notifyListeners();
  }

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final r = await Future.wait<Object>([_service.mine(), _service.niches()]);
      channels = r[0] as List<Channel>;
      niches = r[1] as List<Niche>;
      loaded = true;
    } on AppException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'No pudimos cargar tus canales.';
    }
    loading = false;
    notifyListeners();
  }

  /// Agrega el canal. Si el usuario NO acepta compartir, se aplica justo después con PUT /training.
  Future<bool> addChannel(String handle, {required bool share}) async {
    Channel? ch;
    final ok = await _guard(() async {
      ch = await _service.add(handle.trim());
    });
    if (!ok || ch == null) return false;
    created = ch;
    if (!share) {
      try {
        await _service.setTraining(ch!.id, false);
      } on AppException {
        error =
            'Canal agregado, pero no pudimos guardar tu preferencia de privacidad. Revisa el interruptor en tu lista de canales.';
      }
    }
    await _reload();
    return true;
  }

  Future<bool> setNiche(int channelId, int nicheId) async {
    final ok = await _guard(() => _service.setNiche(channelId, nicheId));
    if (ok) await _reload();
    return ok;
  }

  Future<bool> setTraining(int channelId, bool share) async {
    final ok = await _guard(() => _service.setTraining(channelId, share));
    if (ok) await _reload();
    return ok;
  }

  Future<bool> delete(int channelId) async {
    final ok = await _guard(() => _service.delete(channelId));
    if (ok) await _reload();
    return ok;
  }

  Future<void> _reload() async {
    try {
      channels = await _service.mine();
    } catch (_) {
      // se queda la lista anterior; el usuario puede jalar para refrescar
    }
    notifyListeners();
  }

  Future<bool> _guard(Future<void> Function() action) async {
    busy = true;
    error = null;
    _fieldErrors = {};
    notifyListeners();
    try {
      await action();
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