"""Ranking de temas que pegan ahora: lift ponderado por recencia (docs/C3_ml.md, sección 4)."""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

from .config import merge_cfg
from .dataset import build_dataset
from .text import STOPWORDS

MIN_VIDEOS_PER_TERM = 5
PRIOR_VIDEOS = 8  # videos "virtuales" con la tasa base del nicho


def topic_ranking(videos_df: pd.DataFrame, niche_id: int, cfg: dict | None = None, limit: int = 10) -> list[dict]:
    cfg = merge_cfg(cfg)
    ds = build_dataset(videos_df[videos_df["niche_id"] == niche_id], cfg)
    if len(ds) < MIN_VIDEOS_PER_TERM:
        return []
    cv = CountVectorizer(lowercase=True, strip_accents="unicode", stop_words=STOPWORDS,
                         ngram_range=(1, 2), min_df=MIN_VIDEOS_PER_TERM, binary=True)
    try:
        X = cv.fit_transform(ds["title"].astype(str))
    except ValueError:  # vocabulario vacío
        return []
    w = ds["weight"].to_numpy(dtype=float)
    y = ds["y"].to_numpy(dtype=float)
    base = (w * y).sum() / w.sum()
    if base <= 0:
        return []
    num = np.asarray(X.T @ (w * y)).ravel()
    den = np.asarray(X.T @ w).ravel()
    n_videos = np.asarray(X.sum(axis=0)).ravel()
    terms = cv.get_feature_names_out()
    # Suavizado: evita que un término con 5 videos "ganadores" encabece el ranking por azar.
    prior = PRIOR_VIDEOS * float(w.mean())
    rows = []
    for t, nu, de, nv in zip(terms, num, den, n_videos):
        if de <= 0 or t.replace(" ", "").isdigit():
            continue
        win = (nu + prior * base) / (de + prior)
        rows.append({"term": str(t), "lift": round(float(win / base), 3), "win_rate": round(float(win), 3),
                     "n_videos": int(nv)})
    rows.sort(key=lambda r: (-r["lift"], -r["n_videos"]))
    return rows[:limit]
