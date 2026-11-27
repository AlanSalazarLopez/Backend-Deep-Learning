import 'package:yt_trends_app/core/api_client.dart';
import 'package:yt_trends_app/core/app_exceptions.dart';
import 'package:yt_trends_app/models/channel.dart';
import 'package:yt_trends_app/models/niche.dart';

class ChannelService {
  ChannelService(this._api);

  final ApiClient _api;

  Future<List<Niche>> niches() async {
    final d = await _api.get('/niches') as List;
    return d.map((e) => Niche.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Channel>> mine() async {
    try {
      final d = await _api.get('/channels/mine') as List;
      return d.map((e) => Channel.fromJson(e as Map<String, dynamic>)).toList();
    } on ApiException catch (e) {
      if (e.statusCode == 404) return [];
      rethrow;
    }
  }

  /// El cuerpo solo lleva {handle} (el backend rechaza campos extra con 422).
  Future<Channel> add(String handle) async {
    final d = await _api.post('/channels', {'handle': handle});
    return Channel.fromJson(d as Map<String, dynamic>);
  }

  Future<void> setNiche(int channelId, int nicheId) async {
    await _api.put('/channels/$channelId/niche', {'niche_id': nicheId});
  }

  Future<void> setTraining(int channelId, bool share) async {
    await _api.put('/channels/$channelId/training', {'share': share});
  }

  Future<void> delete(int channelId) async {
    await _api.delete('/channels/$channelId');
  }
}