import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/models/prediction.dart';

class PredictionService {
  PredictionService(this._api);

  final ApiClient _api;

  Future<Prediction> predict({
    required int nicheId,
    required String title,
    required int durationS,
    required int hour,
    int? weekday,
  }) async {
    final d = await _api.post('/predict', {
      'niche_id': nicheId,
      'title': title,
      'duration_s': durationS,
      'publish_hour': hour,
      if (weekday != null) 'publish_weekday': weekday,
    });
    return Prediction.fromJson(d as Map<String, dynamic>);
  }

  Future<List<Prediction>> mine({int limit = 50}) async {
    final d = await _api.get('/predictions/mine', query: {'limit': '$limit'})
        as List;
    return d
        .map((e) => Prediction.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}