"""API pública del paquete ML (docs/C3_ml.md, sección 4): train, load_model, predict, topic_ranking."""
import io
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from .config import FEATURE_VERSION, merge_cfg
from .dataset import build_dataset, select_training_rows
from .features import build_pipeline, channel_vocabulary, prepare_X
from .text import clean_title
from .topics import topic_ranking  # noqa: F401  (se reexporta)

MIN_ROWS = 200
MIN_CHANNELS = 10
EVAL_SEEDS = [1, 2, 3, 4, 5]


class NotEnoughData(ValueError):
    """No hay datos suficientes (o con ambas clases) para entrenar o evaluar."""


@dataclass
class TrainResult:
    artifact: bytes
    metrics: dict
    config: dict
    n_videos: int
    n_channels: int


@dataclass
class PredictResult:
    probability: float
    score: float
    top_terms: list = field(default_factory=list)


@dataclass
class LoadedModel:
    pipeline: object
    config: dict
    reference: dict
    reference_all: np.ndarray
    terms: np.ndarray
    sklearn_version: str


# ----------------------------------------------------------------------------- entrenamiento
def _fit(parts, cfg, X, y, w, mask, groups=None):
    Xt, yt = X[mask], y[mask]
    vocab = channel_vocabulary(Xt["text"], groups[mask], cfg) if ("text" in parts and groups is not None) else None
    pipe = build_pipeline(cfg, parts, vocab)
    pipe.fit(Xt, yt, clf__sample_weight=w[mask])
    return pipe


def _p_at_k(y_true, proba, frac=0.10):
    k = max(1, int(np.ceil(frac * len(y_true))))
    top = np.argsort(-proba, kind="stable")[:k]
    return float(np.mean(y_true[top]))


def _within_channel_auc(y, p, g, min_n=8):
    """AUC promedio DENTRO de cada canal de prueba (solo canales con al menos min_n videos y ambas clases).

    Es lo que enfrenta un creador real: elegir entre ideas de SU canal. El AUC global mezcla canales con tasas de
    y=1 muy distintas, y esa diferencia entre canales no tiene nada que ver con el título."""
    out = []
    for ch in np.unique(g):
        idx = g == ch
        yy = y[idx]
        if idx.sum() >= min_n and 0 < yy.sum() < len(yy):
            out.append(roc_auc_score(yy, p[idx]))
    return float(np.mean(out)) if out else np.nan


def _evaluate(ds, X, y, w, mask, groups, cfg):
    rows = {"within": [], "auc": [], "pr": [], "p10": [], "lift": [], "base": [], "text": [], "format": []}
    n_tr = n_te = 0
    for seed in EVAL_SEEDS:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
        tr, te = next(gss.split(X, y, groups))
        ytr = y[tr]
        yte = y[te]
        if len(np.unique(yte)) < 2 or len(np.unique(ytr[mask[tr]])) < 2:
            continue
        sub_mask = np.zeros(len(y), dtype=bool)
        sub_mask[tr] = mask[tr]
        pipe = _fit(("text", "meta"), cfg, X, y, w, sub_mask, groups)
        p = pipe.predict_proba(X.iloc[te])[:, 1]
        rows["auc"].append(roc_auc_score(yte, p))
        rows["within"].append(_within_channel_auc(yte, p, groups[te]))
        rows["pr"].append(average_precision_score(yte, p))
        p10 = _p_at_k(yte, p)
        rows["p10"].append(p10)
        rows["base"].append(float(yte.mean()))
        rows["lift"].append(p10 / yte.mean() if yte.mean() > 0 else np.nan)
        for name, parts in (("text", ("text",)), ("format", ("meta",))):
            try:
                pp = _fit(parts, cfg, X, y, w, sub_mask, groups)
                rows[name].append(roc_auc_score(yte, pp.predict_proba(X.iloc[te])[:, 1]))
            except ValueError:
                pass
        n_tr, n_te = len(np.unique(groups[tr])), len(np.unique(groups[te]))
    if not rows["auc"]:
        raise NotEnoughData("No se pudo evaluar: los canales de prueba no tienen ambas clases.")
    avg = lambda v: float(np.nanmean(v)) if len(v) else None  # noqa: E731
    return {
        "auc_mean": avg(rows["auc"]), "auc_std": float(np.nanstd(rows["auc"])),
        "auc_within_channel": avg(rows["within"]), "auc_within_std": float(np.nanstd(rows["within"])),
        "pr_auc": avg(rows["pr"]), "precision_at_10": avg(rows["p10"]), "lift_at_10": avg(rows["lift"]),
        "base_rate": avg(rows["base"]), "baseline_auc": 0.5,
        "format_only_auc": avg(rows["format"]),
        "ablation": {"text_only": avg(rows["text"]), "format_only": avg(rows["format"]), "both": avg(rows["auc"])},
        "n_train_channels": int(n_tr), "n_test_channels": int(n_te), "seeds": EVAL_SEEDS,
    }


def _temporal_auc(ds, X, y, w, mask, cfg):
    groups = ds["channel_id"].to_numpy()
    old = (ds["age_days"] >= cfg["label"]["age_bins"][2]).to_numpy()
    new = ~old
    if old.sum() < 50 or new.sum() < 50 or len(np.unique(y[new])) < 2 or len(np.unique(y[old & mask])) < 2:
        return None
    sub = old & mask
    pipe = _fit(("text", "meta"), cfg, X, y, w, sub, groups)
    return float(roc_auc_score(y[new], pipe.predict_proba(X[new])[:, 1]))


def _reference(X, y, w, mask, groups, niches, cfg):
    """Probabilidades fuera de muestra (GroupKFold) -> cuantiles por nicho, para calcular percentiles."""
    n_splits = int(min(5, len(np.unique(groups))))
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, groups):
        m = np.zeros(len(y), dtype=bool)
        m[tr] = mask[tr]
        if len(np.unique(y[m])) < 2:
            continue
        pipe = _fit(("text", "meta"), cfg, X, y, w, m, groups)
        oof[te] = pipe.predict_proba(X.iloc[te])[:, 1]
    ok = ~np.isnan(oof)
    grid = np.linspace(0, 1, 201)
    ref = {int(n): np.quantile(oof[ok & (niches == n)], grid) for n in np.unique(niches) if (ok & (niches == n)).sum() >= 20}
    ref_all = np.quantile(oof[ok], grid)
    return ref, ref_all


def _top_terms(pipe, k=20):
    fe = pipe.named_steps["features"]
    terms = fe.named_transformers_["tfidf"].get_feature_names_out()
    coef = pipe.named_steps["clf"].coef_[0][: len(terms)]
    order = np.argsort(coef)
    pos = [[str(terms[i]), round(float(coef[i]), 4)] for i in order[::-1][:k] if coef[i] > 0]
    neg = [[str(terms[i]), round(float(coef[i]), 4)] for i in order[:k] if coef[i] < 0]
    return terms, pos, neg


def train(videos_df: pd.DataFrame, cfg: dict | None = None) -> TrainResult:
    cfg = merge_cfg(cfg)
    ds = build_dataset(videos_df, cfg)
    ds, n_sin_base_canal = select_training_rows(ds, cfg)
    n_channels = int(ds["channel_id"].nunique()) if len(ds) else 0
    if len(ds) < MIN_ROWS or n_channels < MIN_CHANNELS:
        raise NotEnoughData(f"Datos insuficientes: {len(ds)} videos y {n_channels} canales "
                            f"(mínimo {MIN_ROWS} y {MIN_CHANNELS}).")
    if ds["y"].nunique() < 2:
        raise NotEnoughData("Todas las etiquetas son iguales; revisa theta o los datos.")

    X = prepare_X(ds, cfg)
    y = ds["y"].to_numpy()
    w = ds["weight"].to_numpy(dtype=float)
    mask = ds["train_ok"].to_numpy(dtype=bool)
    groups = ds["channel_id"].to_numpy()
    niches = ds["niche_id"].to_numpy()

    metrics = _evaluate(ds, X, y, w, mask, groups, cfg)
    metrics["temporal_auc"] = _temporal_auc(ds, X, y, w, mask, cfg)
    reference, reference_all = _reference(X, y, w, mask, groups, niches, cfg)

    final = _fit(("text", "meta"), cfg, X, y, w, mask, groups)
    terms, pos, neg = _top_terms(final)
    metrics.update({"top_positive_terms": pos, "top_negative_terms": neg,
                    "n_rows": int(len(ds)), "n_positive": int(y.sum()),
                    "n_dropped_no_channel_baseline": n_sin_base_canal})

    buf = io.BytesIO()
    joblib.dump({"pipeline": final, "config": cfg, "feature_version": FEATURE_VERSION,
                 "reference": reference, "reference_all": reference_all,
                 "sklearn_version": sklearn.__version__}, buf)
    return TrainResult(artifact=buf.getvalue(), metrics=metrics, config=cfg,
                       n_videos=int(len(ds)), n_channels=n_channels)


# ----------------------------------------------------------------------------- predicción
def load_model(artifact: bytes) -> LoadedModel:
    obj = joblib.load(io.BytesIO(artifact))  # el artefacto es nuestro (se genera y guarda en nuestra BD)
    if obj.get("sklearn_version") != sklearn.__version__:
        raise RuntimeError(f"El modelo se entrenó con scikit-learn {obj.get('sklearn_version')} "
                           f"y el servidor tiene {sklearn.__version__}. Reentrena el modelo.")
    pipe = obj["pipeline"]
    terms = pipe.named_steps["features"].named_transformers_["tfidf"].get_feature_names_out()
    return LoadedModel(pipeline=pipe, config=obj["config"], reference=obj["reference"],
                       reference_all=obj["reference_all"], terms=terms, sklearn_version=obj["sklearn_version"])


def _percentile(grid: np.ndarray, p: float) -> float:
    return float(np.clip(100.0 * np.searchsorted(grid, p, side="right") / len(grid), 0.0, 100.0))


def predict(model: LoadedModel, *, title: str, duration_s: int, publish_hour: int,
            publish_weekday: int, niche_id: int) -> PredictResult:
    row = pd.DataFrame([{"title": clean_title(title), "duration_s": duration_s,
                         "publish_hour": publish_hour, "publish_weekday": publish_weekday, "niche_id": niche_id}])
    X = prepare_X(row, model.config)
    p = float(model.pipeline.predict_proba(X)[0, 1])
    grid = model.reference.get(int(niche_id), model.reference_all)
    score = _percentile(np.asarray(grid), p)

    fe = model.pipeline.named_steps["features"]
    xt = fe.named_transformers_["tfidf"].transform(X["text"]).toarray()[0]
    coef = model.pipeline.named_steps["clf"].coef_[0][: len(model.terms)]
    contrib = xt * coef
    idx = [i for i in np.argsort(-np.abs(contrib))[:5] if contrib[i] != 0]
    top = [{"term": str(model.terms[i]), "weight": round(float(contrib[i]), 4)} for i in idx]
    return PredictResult(probability=round(p, 4), score=round(score, 1), top_terms=top)