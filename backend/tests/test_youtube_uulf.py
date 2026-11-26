"""YouTubeClient.recent_videos: playlist de videos largos (UULF), respaldo al normal, paginación y cuota."""
import pytest

from services.youtube_client import (YouTubeClient, YouTubeError, YouTubeQuotaError, long_form_playlist_id)

UPLOADS = "UUabc123"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class FakeSession:
    """playlists: {playlistId: [ids...]} (o un código de error int). Registra cada llamada."""
    def __init__(self, playlists):
        self.playlists, self.calls = playlists, []

    def get(self, url, params=None, timeout=None):
        ep = url.rsplit("/", 1)[1]
        self.calls.append((ep, dict(params)))
        if ep == "playlistItems":
            data = self.playlists.get(params["playlistId"], 404)
            if isinstance(data, int):
                body = {"error": {"errors": [{"reason": "quotaExceeded"}]}} if data == 403 else {}
                return _Resp(data, body)
            start = int(params.get("pageToken", 0))
            n = int(params["maxResults"])
            chunk = data[start:start + n]
            body = {"items": [{"contentDetails": {"videoId": v}} for v in chunk]}
            if start + n < len(data):
                body["nextPageToken"] = str(start + n)
            return _Resp(200, body)
        ids = params["id"].split(",")
        items = [{"id": v, "snippet": {"title": f"t {v}", "publishedAt": "2026-10-01T00:00:00Z", "categoryId": "20"},
                  "contentDetails": {"duration": "PT10M"}, "statistics": {"viewCount": "1000"}} for v in ids]
        return _Resp(200, {"items": items})

    def n(self, ep):
        return sum(1 for e, _ in self.calls if e == ep)


def _client(playlists):
    s = FakeSession(playlists)
    return YouTubeClient(api_key="k", session=s), s


def test_id_del_playlist_de_videos_largos():
    assert long_form_playlist_id("UUabc123") == "UULFabc123"
    assert long_form_playlist_id("UULFabc123") is None
    assert long_form_playlist_id("PLxyz") is None


def test_usa_uulf_y_no_toca_el_playlist_normal():
    yt, s = _client({"UULFabc123": ["a", "b", "c"], UPLOADS: ["x"]})
    vids = yt.recent_videos(UPLOADS)
    assert [v.yt_video_id for v in vids] == ["a", "b", "c"]
    assert all(p["playlistId"] == "UULFabc123" for e, p in s.calls if e == "playlistItems")


def test_respaldo_si_uulf_no_existe():
    yt, s = _client({UPLOADS: ["x", "y"]})                  # UULF responde 404
    assert [v.yt_video_id for v in yt.recent_videos(UPLOADS)] == ["x", "y"]


def test_respaldo_si_uulf_viene_vacio():
    yt, _ = _client({"UULFabc123": [], UPLOADS: ["x"]})
    assert [v.yt_video_id for v in yt.recent_videos(UPLOADS)] == ["x"]


def test_pagina_hasta_max_videos_con_el_costo_esperado():
    yt, s = _client({"UULFabc123": [f"v{i}" for i in range(150)]})
    vids = yt.recent_videos(UPLOADS, max_videos=100)
    assert len(vids) == 100 and vids[0].yt_video_id == "v0"
    assert s.n("playlistItems") == 2 and s.n("videos") == 2   # 2 + 2 unidades


def test_con_menos_videos_que_el_maximo_no_pide_paginas_de_mas():
    yt, s = _client({"UULFabc123": [f"v{i}" for i in range(30)]})
    assert len(yt.recent_videos(UPLOADS, max_videos=100)) == 30
    assert s.n("playlistItems") == 1 and s.n("videos") == 1


def test_long_form_only_false_usa_el_playlist_normal():
    yt, s = _client({"UULFabc123": ["a"], UPLOADS: ["x"]})
    assert [v.yt_video_id for v in yt.recent_videos(UPLOADS, long_form_only=False)] == ["x"]


def test_el_error_de_cuota_no_se_traga_con_el_respaldo():
    yt, _ = _client({"UULFabc123": 403, UPLOADS: ["x"]})
    with pytest.raises(YouTubeQuotaError):
        yt.recent_videos(UPLOADS)


def test_si_fallan_los_dos_playlists_sube_el_error():
    class Boom(FakeSession):
        def get(self, url, params=None, timeout=None):
            return _Resp(500, {})
    yt = YouTubeClient(api_key="k", session=Boom({}))
    with pytest.raises(YouTubeError):
        yt.recent_videos(UPLOADS)