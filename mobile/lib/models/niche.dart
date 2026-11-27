class Niche {
  const Niche({
    required this.id,
    required this.slug,
    required this.name,
    required this.nVideos,
  });

  final int id;
  final String slug;
  final String name;
  final int nVideos;

  factory Niche.fromJson(Map<String, dynamic> j) => Niche(
        id: j['id'] as int,
        slug: (j['slug'] as String?) ?? '',
        name: j['name'] as String,
        nVideos: (j['n_videos'] as num?)?.toInt() ?? 0,
      );
}