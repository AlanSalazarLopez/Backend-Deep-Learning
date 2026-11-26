"""Nichos: esquemas de salida (lista, resumen comparativo y temas)."""
from pydantic import BaseModel, Field


class NicheOut(BaseModel):
    id: int = Field(ge=1)
    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)
    n_videos: int = 0


class NicheRef(BaseModel):
    id: int
    name: str


class OwnStats(BaseModel):
    n_videos: int
    median_views_per_day: float
    pct_outperformers: float


class NicheStats(OwnStats):
    n_channels: int


class TopVideo(BaseModel):
    yt_video_id: str
    title: str
    views: int
    ratio: float


class OverviewOut(BaseModel):
    niche: NicheRef
    window_days: int
    own: OwnStats
    niche_stats: NicheStats
    own_top_videos: list[TopVideo]


class TopicOut(BaseModel):
    term: str
    lift: float
    win_rate: float
    n_videos: int


def get(conn, niche_id: int):
    return conn.execute("SELECT id, slug, name FROM niches WHERE id = %s", (niche_id,)).fetchone()
