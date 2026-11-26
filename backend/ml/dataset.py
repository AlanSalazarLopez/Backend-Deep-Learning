"""Limpieza de videos y construcción del dataset con etiqueta (docs/C3_ml.md, secciones 1 y 3)."""
import numpy as np
import pandas as pd

from .config import merge_cfg
from .text import clean_title

# Rango de duración que usa el modelo: de 3 min a 2 h. Debajo de 181 s se consideran Shorts y no se usan;
# 7200 s coincide con el máximo que acepta /predict. Se pueden cambiar en cfg["data"].
DEFAULT_MIN_DURATION_S = 181
DEFAULT_MAX_DURATION_S = 7200

REQUIRED = ["channel_id", "niche_id", "yt_video_id", "title", "published_at", "duration_s", "views", "fetched_at"]
OUT_COLS = ["yt_video_id", "channel_id", "niche_id", "title", "duration_s", "is_short", "publish_hour",
            "publish_weekday", "views", "age_days", "velocity", "baseline", "ratio", "y", "weight", "train_ok",
            "age_bin", "baseline_src"]


def clean_videos(videos_df: pd.DataFrame) -> pd.DataFrame:
    """Excluye filas inválidas (título vacío, vistas negativas, duración <= 0, fechas imposibles)."""
    missing = [c for c in REQUIRED if c not in videos_df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en videos: {missing}")
    df = videos_df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")
    df["views"] = pd.to_numeric(df["views"], errors="coerce")
    df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")
    title_ok = df["title"].notna() & (df["title"].astype(str).str.strip() != "")
    ok = (
        title_ok
        & df["published_at"].notna()
        & df["fetched_at"].notna()
        & (df["views"] >= 0)
        & (df["duration_s"] > 0)
        & (df["published_at"] <= df["fetched_at"])
    )
    return df[ok].reset_index(drop=True)


def _loo_median(values: np.ndarray) -> np.ndarray:
    out = np.empty(len(values))
    for i in range(len(values)):
        out[i] = np.median(np.delete(values, i))
    return out


def _baseline_bins(df: pd.DataFrame, lab: dict):
    """Método "bins": mediana de la velocidad de los OTROS videos del canal en la misma franja de edad.
    Si el canal tiene pocos videos en la franja, respaldo con la mediana del nicho y luego la global."""
    vel = df["velocity"].to_numpy()
    base = np.full(len(df), np.nan)
    src = np.full(len(df), "canal", dtype=object)
    for _, pos in df.groupby(["channel_id", "age_bin"]).indices.items():
        if len(pos) - 1 >= lab["min_videos_in_bin"]:
            base[pos] = _loo_median(vel[pos])
    use_niche = np.isnan(base)
    src[use_niche] = "nicho"
    niche_med = df.groupby(["niche_id", "age_bin"])["velocity"].transform("median").to_numpy()
    base = np.where(use_niche, niche_med, base)
    use_glob = np.isnan(base)
    src[use_glob] = "global"
    glob_med = df.groupby("age_bin")["velocity"].transform("median").to_numpy()
    return np.where(use_glob, glob_med, base), src


def _interp_log_age(age: np.ndarray, centers: np.ndarray, levels: np.ndarray) -> np.ndarray:
    """Interpola la curva en log(edad) (la caída de la velocidad es casi lineal ahí) y, fuera del rango de los
    centros, la prolonga con la pendiente del tramo más cercano en vez de dejarla plana. Sin esto, los videos más
    jóvenes (donde la curva cae más rápido) quedaban corregidos de menos y salían 'mejores' de lo que son."""
    if len(centers) < 2:
        return np.full(len(age), levels[0])
    x, xp = np.log(age), np.log(centers)
    y = np.interp(x, xp, levels)
    left, right = x < xp[0], x > xp[-1]
    if left.any():
        y[left] = levels[0] + (levels[1] - levels[0]) / (xp[1] - xp[0]) * (x[left] - xp[0])
    if right.any():
        y[right] = levels[-1] + (levels[-1] - levels[-2]) / (xp[-1] - xp[-2]) * (x[right] - xp[-1])
    return y


def _age_curve(age: np.ndarray, lv: np.ndarray, ch: np.ndarray, n_bins: int, n_iter: int = 8) -> np.ndarray:
    """Curva esperada de log-velocidad según la edad, estimada con nivel propio por canal (ajuste alternado).

    Un solo paso (restar la mediana del canal y promediar por edad) falla cuando los canales cubren edades
    distintas: los que publican a diario solo tienen videos jóvenes y los que publican poco abarcan todo el
    rango, así que la curva mezcla tipos de canal según la edad y corrige de menos. Aquí se alternan dos pasos:
    (1) nivel del canal = mediana de (log-velocidad - curva) y (2) curva = mediana por tramo de edad de
    (log-velocidad - nivel del canal). Las repeticiones alinean los niveles a través de las edades que los
    canales tienen en común."""
    if len(lv) < 6:
        return np.zeros(len(lv))
    n_bins = int(max(3, min(n_bins, len(lv) // 40)))
    codes = pd.qcut(age, q=n_bins, duplicates="drop", labels=False)
    curve = np.zeros(len(lv))
    for _ in range(n_iter):
        level = pd.Series(lv - curve).groupby(ch).transform("median").to_numpy()
        tmp = pd.DataFrame({"age": age, "d": lv - level, "b": codes})
        centers = tmp.groupby("b")["age"].median().to_numpy()
        levels = tmp.groupby("b")["d"].median().to_numpy()
        curve = _interp_log_age(age, centers, levels)
    return curve


def _baseline_age_adjusted(df: pd.DataFrame, lab: dict):
    """Método "age_adjusted" (por defecto): quita el efecto de la edad en vez de separar por franjas.

    La velocidad (vistas/día) baja con la edad porque las vistas se estancan, y separar por franjas deja esa
    tendencia dentro de cada franja. Este método divide cada velocidad entre lo esperado a su edad (curva medida
    DENTRO de los canales, ver _age_curve) y toma como línea base del canal la mediana de esos valores ajustados
    de TODOS sus otros videos. Así no hace falta que el canal tenga varios videos en la misma franja, y un video
    de 5 días ya no se compara contra uno de 80."""
    age = df["age_days"].to_numpy(dtype=float)
    lv = np.log(np.maximum(df["velocity"].to_numpy(dtype=float), 0.1))
    ch = df["channel_id"].to_numpy()
    expected = _age_curve(age, lv, ch, lab.get("age_curve_bins", 12))
    adj = lv - expected

    base_adj = np.full(len(df), np.nan)
    src = np.full(len(df), "canal", dtype=object)
    for _, pos in df.groupby("channel_id").indices.items():
        if len(pos) - 1 >= lab.get("min_videos_in_channel", 5):
            base_adj[pos] = _loo_median(adj[pos])
    use_niche = np.isnan(base_adj)
    src[use_niche] = "nicho"
    niche_med = pd.Series(adj).groupby(df["niche_id"].to_numpy()).transform("median").to_numpy()
    base_adj = np.where(use_niche, niche_med, base_adj)
    use_glob = np.isnan(base_adj)
    src[use_glob] = "global"
    base_adj = np.where(use_glob, np.median(adj), base_adj)
    return np.exp(expected + base_adj), src


def build_dataset(videos_df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    cfg = merge_cfg(cfg)
    lab, data = cfg["label"], cfg["data"]
    df = clean_videos(videos_df)

    if data.get("language") and "language" in df.columns:
        df = df[df["language"] == data["language"]]

    # Opcional: entrenar solo con algunos nichos (cfg["data"]["niche_ids"], por ejemplo [1, 3, 4]).
    niche_ids = data.get("niche_ids")
    if niche_ids:
        df = df[df["niche_id"].isin(niche_ids)]

    # Solo videos de duración "normal" (sin Shorts ni streams larguísimos). Va ANTES de calcular la línea
    # base, para comparar cada video solo contra videos del mismo tipo.
    lo = data.get("min_duration_s", DEFAULT_MIN_DURATION_S)
    hi = data.get("max_duration_s", DEFAULT_MAX_DURATION_S)
    df = df[(df["duration_s"] >= lo) & (df["duration_s"] <= hi)].copy()

    # Texto del título sin hashtags ni "Parte N". Si se queda vacío, el video se excluye.
    df["title"] = df["title"].astype(str).map(clean_title)
    df = df[df["title"] != ""].copy()

    df["age_days"] = (df["fetched_at"] - df["published_at"]).dt.total_seconds() / 86400.0
    df = df[(df["age_days"] >= lab["min_age_days"]) & (df["age_days"] <= lab["max_age_days"])].copy()
    if df.empty:
        return pd.DataFrame(columns=OUT_COLS)

    df["velocity"] = df["views"] / np.maximum(df["age_days"], 1.0)
    df["age_bin"] = pd.cut(df["age_days"], bins=lab["age_bins"], right=False, labels=False)
    df = df[df["age_bin"].notna()].reset_index(drop=True)
    df["age_bin"] = df["age_bin"].astype(int)

    # Línea base: mediana de la velocidad de los OTROS videos del canal en la misma franja de edad.
    # baseline_src guarda de dónde salió la línea base de cada video: "canal" (lo ideal), "nicho" o "global"
    # (respaldos cuando el canal tiene pocos videos). Sirve para diagnosticar la etiqueta.
    method = lab.get("method", "age_adjusted")
    if method == "bins":
        base, src = _baseline_bins(df, lab)
    elif method == "age_adjusted":
        base, src = _baseline_age_adjusted(df, lab)
    else:
        raise ValueError(f"label.method desconocido: {method!r} (usa 'age_adjusted' o 'bins')")
    df["baseline"] = base
    df["baseline_src"] = src
    df = df[df["baseline"] > 0].reset_index(drop=True)
    df["ratio"] = df["velocity"] / df["baseline"]

    if lab["mode"] == "percentile":
        q = df.groupby(["niche_id", "age_bin"])["ratio"].transform(lambda s: s.quantile(0.75))
        df["y"] = (df["ratio"] >= q).astype(int)
    else:
        df["y"] = (df["ratio"] >= lab["theta"]).astype(int)

    gz = lab.get("gray_zone")
    df["train_ok"] = True if not gz else ((df["ratio"] >= gz["win"]) | (df["ratio"] <= gz["lose"]))

    hl = cfg["weights"].get("half_life_days")
    df["weight"] = 0.5 ** (df["age_days"] / hl) if hl else 1.0

    local = df["published_at"].dt.tz_convert(data["timezone"])
    df["publish_hour"] = local.dt.hour
    df["publish_weekday"] = local.dt.day_of_week
    if "is_short" not in df.columns:
        df["is_short"] = df["duration_s"] <= 60
    df["is_short"] = df["is_short"].astype(bool)
    return df[OUT_COLS].reset_index(drop=True)


def select_training_rows(ds: pd.DataFrame, cfg: dict | None = None) -> tuple[pd.DataFrame, int]:
    """Deja fuera del entrenamiento los videos cuya línea base no salió de su propio canal
    (label.require_channel_baseline, por defecto True). Devuelve (dataset filtrado, cuántos quitó).

    Se aplica en train() y en el diagnóstico, no en build_dataset: topic_ranking sí quiere los videos más
    recientes, que son justo los que más caen al respaldo del nicho."""
    cfg = merge_cfg(cfg)
    if ds.empty or not cfg["label"].get("require_channel_baseline", True):
        return ds, 0
    keep = ds["baseline_src"] == "canal"
    return ds[keep].reset_index(drop=True), int((~keep).sum())