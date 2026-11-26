"""Carga un canal y sus videos recientes en la BD (la usan POST /channels y scripts/ingest.py)."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from services.language import channel_language
from services.youtube_client import ChannelInfo, VideoInfo

MIN_VIDEOS_FOR_SUGGESTION = 10
DEFAULT_MAX_VIDEOS = 50


class ChannelNotFound(Exception):
    pass


class ChannelTaken(Exception):
    pass


@dataclass
class IngestResult:
    channel: dict
    videos: list
    language: str | None
    suggested_niche_id: int | None


def fetch_from_youtube(yt, handle: str, max_videos: int = DEFAULT_MAX_VIDEOS) -> tuple[ChannelInfo, list[VideoInfo]]:
    """Llamadas externas primero (sin tocar la BD): si YouTube falla, no queda nada a medias.
    max_videos: cuántos videos recientes (largos) traer; los canales semilla usan más para tener datos de sobra."""
    info = yt.resolve_channel(handle)
    if info is None:
        raise ChannelNotFound(handle)
    return info, yt.recent_videos(info.uploads_playlist_id, max_videos)


def suggest_niche(conn, videos: list[VideoInfo]) -> int | None:
    if len(videos) < MIN_VIDEOS_FOR_SUGGESTION:
        return None
    cats = Counter(v.category_id for v in videos if v.category_id is not None)
    for cat, _ in cats.most_common():
        row = conn.execute("SELECT id FROM niches WHERE yt_category_id = %s", (cat,)).fetchone()
        if row:
            return row["id"]
    return None


def save_channel(conn, info: ChannelInfo, videos: list[VideoInfo], *, user_id: int | None,
                 source: str, niche_id: int | None = None) -> IngestResult:
    """Guarda canal y videos (sin commit: lo hace quien llama)."""
    language = channel_language(videos)
    now = datetime.now(timezone.utc)
    existing = conn.execute("SELECT * FROM channels WHERE yt_channel_id = %s", (info.yt_channel_id,)).fetchone()

    if existing:
        if user_id is not None and existing["user_id"] not in (None, user_id):
            raise ChannelTaken(info.handle)
        if user_id is not None:
            # El cliente reclama el canal (puede venir de la lista semilla): confirma su nicho después.
            row = conn.execute(
                "UPDATE channels SET user_id=%s, source='client', handle=%s, title=%s, language=%s, fetched_at=%s, "
                "niche_id=CASE WHEN user_id IS NULL THEN NULL ELSE niche_id END WHERE id=%s RETURNING *",
                (user_id, info.handle, info.title, language, now, existing["id"])).fetchone()
        else:
            row = conn.execute(
                "UPDATE channels SET handle=%s, title=%s, language=%s, fetched_at=%s, "
                "niche_id=COALESCE(niche_id, %s) WHERE id=%s RETURNING *",
                (info.handle, info.title, language, now, niche_id, existing["id"])).fetchone()
    else:
        row = conn.execute(
            "INSERT INTO channels (user_id, yt_channel_id, handle, title, niche_id, source, language, fetched_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (user_id, info.yt_channel_id, info.handle, info.title, niche_id, source, language, now)).fetchone()

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO videos (channel_id, yt_video_id, title, published_at, duration_s, views, likes, comments, "
            "yt_category_id, is_short, fetched_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (yt_video_id) DO UPDATE SET title=EXCLUDED.title, duration_s=EXCLUDED.duration_s, "
            "views=EXCLUDED.views, likes=EXCLUDED.likes, comments=EXCLUDED.comments, "
            "yt_category_id=EXCLUDED.yt_category_id, is_short=EXCLUDED.is_short, fetched_at=EXCLUDED.fetched_at",
            [(row["id"], v.yt_video_id, v.title, v.published_at, v.duration_s, v.views, v.likes, v.comments,
              v.category_id, v.duration_s <= 60, now) for v in videos])
    return IngestResult(channel=row, videos=videos, language=language, suggested_niche_id=suggest_niche(conn, videos))