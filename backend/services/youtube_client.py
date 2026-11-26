"""Cliente mínimo de la API de YouTube Data v3 (solo datos públicos). Cuesta 1 unidad por llamada."""
import re
from dataclasses import dataclass
from datetime import datetime

import requests

from config import settings

API = "https://www.googleapis.com/youtube/v3"
_ISO = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


class YouTubeError(Exception):
    pass


class YouTubeQuotaError(YouTubeError):
    pass


@dataclass
class ChannelInfo:
    yt_channel_id: str
    handle: str
    title: str
    uploads_playlist_id: str


@dataclass
class VideoInfo:
    yt_video_id: str
    title: str
    published_at: datetime
    duration_s: int
    views: int
    likes: int | None
    comments: int | None
    category_id: int | None
    audio_language: str | None = None   # defaultAudioLanguage que declara el creador (puede faltar)
    text_language: str | None = None    # defaultLanguage (idioma del título y la descripción)


def parse_iso_duration(value: str) -> int:
    m = _ISO.match(value or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def long_form_playlist_id(uploads_playlist_id: str) -> str | None:
    """'UU<resto>' (todas las subidas) -> 'UULF<resto>' (solo videos largos, sin Shorts).

    Es un playlist automático que YouTube genera por canal, pero NO está documentado en la API oficial:
    por eso recent_videos tiene respaldo al playlist normal si este falla o viene vacío."""
    if uploads_playlist_id and uploads_playlist_id.startswith("UU") and not uploads_playlist_id.startswith("UULF"):
        return "UULF" + uploads_playlist_id[2:]
    return None


class YouTubeClient:
    def __init__(self, api_key: str | None = None, session=None, timeout: int = 30):
        self.api_key = api_key or settings.require("youtube_api_key")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get(self, endpoint: str, params: dict) -> dict:
        try:
            r = self.session.get(f"{API}/{endpoint}", params={**params, "key": self.api_key}, timeout=self.timeout)
        except requests.RequestException as e:
            raise YouTubeError(f"No se pudo conectar con YouTube: {e}")
        if r.status_code == 403:
            try:
                reason = r.json()["error"]["errors"][0]["reason"]
            except Exception:
                reason = "forbidden"
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                raise YouTubeQuotaError("Se agotó la cuota diaria de la API de YouTube")
            raise YouTubeError(f"YouTube rechazó la petición ({reason})")
        if r.status_code != 200:
            raise YouTubeError(f"YouTube respondió {r.status_code}")
        return r.json()

    def resolve_channel(self, handle: str) -> ChannelInfo | None:
        handle = handle if handle.startswith("@") else "@" + handle
        data = self._get("channels", {"part": "snippet,contentDetails", "forHandle": handle})
        items = data.get("items") or []
        if not items:
            return None
        it = items[0]
        uploads = (it.get("contentDetails", {}).get("relatedPlaylists", {}) or {}).get("uploads")
        if not uploads:
            return None
        custom = it.get("snippet", {}).get("customUrl") or ""
        return ChannelInfo(it["id"], custom if custom.startswith("@") else handle,
                           it.get("snippet", {}).get("title", handle), uploads)

    def _playlist_video_ids(self, playlist_id: str, max_videos: int) -> list[str]:
        """Ids de los videos más recientes del playlist, paginando de 50 en 50 (1 unidad por página)."""
        ids: list[str] = []
        token = None
        while len(ids) < max_videos:
            params = {"part": "contentDetails", "playlistId": playlist_id,
                      "maxResults": min(50, max_videos - len(ids))}
            if token:
                params["pageToken"] = token
            data = self._get("playlistItems", params)
            ids += [it["contentDetails"]["videoId"] for it in data.get("items", []) if it.get("contentDetails")]
            token = data.get("nextPageToken")
            if not token:
                break
        return ids[:max_videos]

    def _video_details(self, ids: list[str]) -> list[VideoInfo]:
        out = []
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            vids = self._get("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(batch),
                                        "maxResults": 50})
            for it in vids.get("items", []):
                sn, st = it.get("snippet", {}), it.get("statistics", {})
                duration = parse_iso_duration(it.get("contentDetails", {}).get("duration", ""))
                views = _int(st.get("viewCount"))
                if views is None or duration <= 0 or sn.get("liveBroadcastContent", "none") != "none":
                    continue  # sin vistas públicas, en vivo o programado
                out.append(VideoInfo(
                    yt_video_id=it["id"], title=sn.get("title", ""),
                    published_at=datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")),
                    duration_s=duration, views=views, likes=_int(st.get("likeCount")),
                    comments=_int(st.get("commentCount")), category_id=_int(sn.get("categoryId")),
                    audio_language=sn.get("defaultAudioLanguage") or None,
                    text_language=sn.get("defaultLanguage") or None))
        return out

    def recent_videos(self, uploads_playlist_id: str, max_videos: int = 50, long_form_only: bool = True) -> list[VideoInfo]:
        """Videos más recientes del canal. Con long_form_only (por defecto) lee primero el playlist de videos largos
        (UULF...), que no trae Shorts: los canales que publican muchos Shorts dejaban 0 a 4 videos útiles de 50.
        Si ese playlist falla o viene vacío, cae al playlist normal de subidas. Costo: 1 unidad por página de 50
        (playlistItems) más 1 por lote de 50 (videos.list)."""
        ids: list[str] = []
        lf = long_form_playlist_id(uploads_playlist_id) if long_form_only else None
        if lf:
            try:
                ids = self._playlist_video_ids(lf, max_videos)
            except YouTubeQuotaError:
                raise
            except YouTubeError:
                ids = []   # playlist no disponible para este canal: respaldo abajo
        if not ids:
            ids = self._playlist_video_ids(uploads_playlist_id, max_videos)
        return self._video_details(ids) if ids else []