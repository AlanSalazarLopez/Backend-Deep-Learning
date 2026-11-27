class ModelInfo {
  const ModelInfo({this.auc, required this.reliable});

  final double? auc;
  final bool reliable;

  factory ModelInfo.fromJson(Map<String, dynamic> j) => ModelInfo(
        auc: (j['auc'] as num?)?.toDouble(),
        reliable: (j['reliable'] as bool?) ?? false,
      );
}

class Prediction {
  const Prediction({
    required this.id,
    required this.nicheId,
    required this.title,
    required this.durationS,
    required this.publishHour,
    this.publishWeekday,
    required this.probability,
    required this.score,
    required this.topTerms,
    required this.createdAt,
    this.modelInfo,
  });

  final int id;
  final int nicheId;
  final String title;
  final int durationS;
  final int publishHour;
  final int? publishWeekday; // 0 = lunes
  final double probability;
  final double score; // 0..100, relativa al nicho
  final List<String> topTerms;
  final DateTime createdAt;

  /// Opcional: el contrato real todavía puede no traerlo.
  final ModelInfo? modelInfo;

  factory Prediction.fromJson(Map<String, dynamic> j) {
    final info = j['model_info'];
    return Prediction(
      id: (j['prediction_id'] ?? j['id']) as int,
      nicheId: j['niche_id'] as int,
      title: (j['title'] as String?) ?? '',
      durationS: (j['duration_s'] as num?)?.toInt() ?? 0,
      publishHour: (j['publish_hour'] as num?)?.toInt() ?? 0,
      publishWeekday: (j['publish_weekday'] as num?)?.toInt(),
      probability: (j['probability'] as num?)?.toDouble() ?? 0,
      score: (j['score'] as num?)?.toDouble() ?? 0,
      topTerms: ((j['top_terms'] as List?) ?? [])
          .map((e) => e is Map ? (e['term'] ?? '').toString() : e.toString())
          .where((s) => s.isNotEmpty)
          .toList(),
      createdAt: DateTime.tryParse((j['created_at'] as String?) ?? '') ??
          DateTime.now(),
      modelInfo: info is Map<String, dynamic> ? ModelInfo.fromJson(info) : null,
    );
  }
}