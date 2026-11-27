class Channel {
  const Channel({
    required this.id,
    required this.handle,
    this.title,
    this.nicheId,
    this.language,
    this.shareForTraining = true,
    this.suggestedNicheId,
    this.videosLoaded,
  });

  final int id;
  final String handle;
  final String? title;
  final int? nicheId;
  final String? language;
  final bool shareForTraining;

  /// Solo vienen en la respuesta de POST /channels.
  final int? suggestedNicheId;
  final int? videosLoaded;

  bool get isSpanish => language == null || language == 'es';

  factory Channel.fromJson(Map<String, dynamic> j) => Channel(
        id: j['id'] as int,
        handle: (j['handle'] as String?) ?? '',
        title: j['title'] as String?,
        nicheId: (j['niche_id'] as num?)?.toInt(),
        language: j['language'] as String?,
        shareForTraining: (j['share_for_training'] as bool?) ?? true,
        suggestedNicheId: (j['suggested_niche_id'] as num?)?.toInt(),
        videosLoaded: (j['videos_loaded'] as num?)?.toInt(),
      );
}