"""Predicciones: esquemas y acceso a datos."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ml.config import merge_cfg
from ml.text import clean_title

_DATA = merge_cfg()["data"]   # límites de duración del modelo (181 a 7200 s)


class PredictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    niche_id: int = Field(ge=1)
    title: str
    duration_s: int = Field(ge=_DATA["min_duration_s"], le=_DATA["max_duration_s"])
    publish_hour: int = Field(ge=0, le=23)
    publish_weekday: int | None = Field(default=None, ge=0, le=6)

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        v = v.strip()
        if not (3 <= len(v) <= 100):
                        raise ValueError("El título debe tener entre 3 y 100 caracteres")
        if not clean_title(v):
            raise ValueError("Escribe un título con palabras, no solo hashtags o 'Parte N'")
        return v


class TermOut(BaseModel):
    term: str
    weight: float


class PredictionOut(BaseModel):
    """También valida lo leído de la BD."""
    prediction_id: int = Field(ge=1)
    niche_id: int = Field(ge=1)
    title: str = Field(min_length=1)
    duration_s: int = Field(ge=1)
    publish_hour: int = Field(ge=0, le=23)
    publish_weekday: int = Field(ge=0, le=6)
    probability: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=100)
    model_run_id: int | None = None
    top_terms: list[TermOut] = []
    created_at: datetime


COLS = ("id AS prediction_id, niche_id, title, duration_s, publish_hour, publish_weekday, probability, score, "
        "model_run_id, top_terms, created_at")
