"""Administración: esquemas de salida del panel y del modelo activo."""
from datetime import datetime

from pydantic import BaseModel


class Totals(BaseModel):
    users: int
    clients: int
    admins: int
    channels: int
    videos: int
    predictions: int
    seed_channels: int = 0   # canales semilla (no son de clientes), aparte para no mezclarlos
    seed_videos: int = 0


class PerClient(BaseModel):
    user_id: int
    username: str
    channel_handle: str | None
    niche: str | None
    n_predictions: int
    last_activity: datetime | None
    n_channels: int = 0


class ByNiche(BaseModel):
    niche_id: int
    name: str
    n_clients: int
    n_videos: int
    n_predictions: int


class DayActivity(BaseModel):
    date: str
    n_predictions: int


class StatsOut(BaseModel):
    totals: Totals
    per_client: list[PerClient]
    by_niche: list[ByNiche]
    activity_by_day: list[DayActivity]


class ModelRunOut(BaseModel):
    id: int
    trained_at: datetime
    n_videos: int
    n_channels: int
    metrics: dict
    config: dict


class ModelOut(BaseModel):
    active: ModelRunOut | None