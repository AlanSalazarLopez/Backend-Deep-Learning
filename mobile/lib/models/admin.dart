List<T> _mapList<T>(dynamic v, T Function(Map<String, dynamic>) f) =>
    ((v as List?) ?? [])
        .map((e) => f((e as Map).cast<String, dynamic>()))
        .toList();

int _int(Map<String, dynamic> j, String k) => (j[k] as num?)?.toInt() ?? 0;

class AdminTotals {
  const AdminTotals({
    required this.users,
    required this.clients,
    required this.admins,
    required this.channels,
    required this.videos,
    required this.predictions,
    required this.seedChannels,
    required this.seedVideos,
  });

  final int users, clients, admins, channels, videos, predictions;
  final int seedChannels, seedVideos;

  factory AdminTotals.fromJson(Map<String, dynamic> j) => AdminTotals(
        users: _int(j, 'users'),
        clients: _int(j, 'clients'),
        admins: _int(j, 'admins'),
        channels: _int(j, 'channels'),
        videos: _int(j, 'videos'),
        predictions: _int(j, 'predictions'),
        seedChannels: _int(j, 'seed_channels'),
        seedVideos: _int(j, 'seed_videos'),
      );
}

class ClientRow {
  const ClientRow({
    required this.userId,
    required this.username,
    this.channelHandle,
    this.niche,
    required this.nPredictions,
    this.lastActivity,
    required this.nChannels,
  });

  final int userId;
  final String username;
  final String? channelHandle; // puede venir "@a, @b"
  final String? niche;
  final int nPredictions;
  final DateTime? lastActivity;
  final int nChannels;

  factory ClientRow.fromJson(Map<String, dynamic> j) => ClientRow(
        userId: _int(j, 'user_id'),
        username: (j['username'] as String?) ?? '',
        channelHandle: j['channel_handle'] as String?,
        niche: j['niche'] as String?,
        nPredictions: _int(j, 'n_predictions'),
        lastActivity: DateTime.tryParse((j['last_activity'] as String?) ?? ''),
        nChannels: _int(j, 'n_channels'),
      );
}

class NicheStat {
  const NicheStat({
    required this.nicheId,
    required this.name,
    required this.nClients,
    required this.nVideos,
    required this.nPredictions,
  });

  final int nicheId;
  final String name;
  final int nClients, nVideos, nPredictions;

  factory NicheStat.fromJson(Map<String, dynamic> j) => NicheStat(
        nicheId: _int(j, 'niche_id'),
        name: (j['name'] as String?) ?? '',
        nClients: _int(j, 'n_clients'),
        nVideos: _int(j, 'n_videos'),
        nPredictions: _int(j, 'n_predictions'),
      );
}

class DayActivity {
  const DayActivity({required this.date, required this.n});

  final String date; // YYYY-MM-DD
  final int n;

  factory DayActivity.fromJson(Map<String, dynamic> j) => DayActivity(
        date: (j['date'] as String?) ?? '',
        n: _int(j, 'n_predictions'),
      );
}

class AdminStats {
  const AdminStats({
    required this.totals,
    required this.perClient,
    required this.byNiche,
    required this.activityByDay,
  });

  final AdminTotals totals;
  final List<ClientRow> perClient;
  final List<NicheStat> byNiche;
  final List<DayActivity> activityByDay;

  factory AdminStats.fromJson(Map<String, dynamic> j) => AdminStats(
        totals: AdminTotals.fromJson(
            ((j['totals'] as Map?) ?? {}).cast<String, dynamic>()),
        perClient: _mapList(j['per_client'], ClientRow.fromJson),
        byNiche: _mapList(j['by_niche'], NicheStat.fromJson),
        activityByDay: _mapList(j['activity_by_day'], DayActivity.fromJson),
      );
}

class AdminUser {
  const AdminUser({
    required this.id,
    required this.username,
    required this.name,
    required this.role,
    this.channelHandle,
    this.createdAt,
  });

  final int id;
  final String username;
  final String name;
  final String role;
  final String? channelHandle;
  final DateTime? createdAt;

  bool get isAdmin => role == 'admin';

  factory AdminUser.fromJson(Map<String, dynamic> j) => AdminUser(
        id: j['id'] as int,
        username: (j['username'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        role: (j['role'] as String?) ?? 'client',
        channelHandle: j['channel_handle'] as String?,
        createdAt: DateTime.tryParse((j['created_at'] as String?) ?? ''),
      );
}

class UsersPage {
  const UsersPage({required this.items, required this.total});

  final List<AdminUser> items;
  final int total;

  factory UsersPage.fromJson(Map<String, dynamic> j) => UsersPage(
        items: _mapList(j['items'], AdminUser.fromJson),
        total: _int(j, 'total'),
      );
}

class ActiveModel {
  const ActiveModel({
    required this.id,
    this.trainedAt,
    required this.nVideos,
    required this.nChannels,
    required this.metrics,
  });

  final int id;
  final DateTime? trainedAt;
  final int nVideos, nChannels;
  final Map<String, dynamic> metrics;

  factory ActiveModel.fromJson(Map<String, dynamic> j) => ActiveModel(
        id: _int(j, 'id'),
        trainedAt: DateTime.tryParse((j['trained_at'] as String?) ?? ''),
        nVideos: _int(j, 'n_videos'),
        nChannels: _int(j, 'n_channels'),
        metrics: ((j['metrics'] as Map?) ?? {}).cast<String, dynamic>(),
      );
}