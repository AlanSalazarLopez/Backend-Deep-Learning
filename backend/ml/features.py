"""Variables del modelo y construcción del Pipeline (docs/C3_ml.md y PLAN_proyecto.md, 2.4)."""
import re

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .text import EMOJI_RE, STOPWORDS, strip_accents

BASE_COLS = ["title", "duration_s", "publish_hour", "publish_weekday"]


def _l1_kwargs() -> dict:
    """L1 puro según la versión de scikit-learn.

    Desde 1.8 el parámetro `penalty` está obsoleto y L1 puro se pide con l1_ratio=1.0. En versiones anteriores
    l1_ratio se IGNORA si penalty es 'l2' (la regresión salía L2 sin avisar), así que ahí hay que pedir penalty='l1'."""
    major, minor = (int(x) for x in sklearn.__version__.split(".")[:2])
    if (major, minor) >= (1, 8):
        return dict(l1_ratio=1.0, solver="saga")
    return dict(penalty="l1", solver="saga")
_TOKEN = re.compile(r"(?u)\b\w\w+\b")


def prepare_X(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Arma el DataFrame de entrada del Pipeline. NUNCA incluye canal, vistas ni la etiqueta."""
    X = df[["title", "duration_s", "publish_hour", "publish_weekday", "niche_id"]].copy()
    X["title"] = X["title"].astype(str)
    text = X["title"]
    if cfg["features"].get("niche_prefix"):
        # Respaldo 3: cada palabra también como "n<nicho>__palabra", para que el significado cambie por nicho.
        def pref(row):
            toks = _TOKEN.findall(strip_accents(row["title"].lower()))
            return row["title"] + " " + " ".join(f"n{int(row['niche_id'])}__{t}" for t in toks)
        text = X.apply(pref, axis=1)
    X["text"] = text
    return X


def meta_frame(df: pd.DataFrame) -> pd.DataFrame:
    t = df["title"].astype(str)
    out = pd.DataFrame(index=df.index)
    out["log_duration"] = np.log1p(df["duration_s"].astype(float))
    out["title_chars"] = t.str.len().astype(float)
    out["title_words"] = t.str.split().str.len().astype(float)
    out["has_number"] = t.str.contains(r"\d", regex=True).astype(float)
    out["has_question"] = t.str.contains(r"[?¿]", regex=True).astype(float)
    out["has_exclaim"] = t.str.contains(r"[!¡]", regex=True).astype(float)
    letters = t.str.count(r"[^\W\d_]").clip(lower=1)
    out["upper_ratio"] = t.str.count(r"[A-ZÁÉÍÓÚÑ]") / letters
    out["has_emoji"] = t.map(lambda s: 1.0 if EMOJI_RE.search(s) else 0.0)
    h = 2 * np.pi * df["publish_hour"].astype(float) / 24.0
    w = 2 * np.pi * df["publish_weekday"].astype(float) / 7.0
    out["hour_sin"], out["hour_cos"] = np.sin(h), np.cos(h)
    out["wd_sin"], out["wd_cos"] = np.sin(w), np.cos(w)
    return out


def channel_vocabulary(texts, groups, cfg: dict) -> list | None:
    """Vocabulario de palabras y bigramas que aparecen en al menos cfg.features.min_channels canales distintos
    (y en min_df videos). Devuelve None si el filtro está apagado (min_channels = None) o si no queda ningún término.
    No usa la etiqueta: solo cuenta en cuántos canales sale cada término. Se calcula SOLO con los videos de
    entrenamiento de cada ajuste, para que los canales de prueba no influyan en el vocabulario."""
    f = cfg["features"]
    k = f.get("min_channels")
    if not k:
        return None
    cv = CountVectorizer(lowercase=True, strip_accents="unicode", stop_words=STOPWORDS,
                         ngram_range=tuple(f["ngram_range"]), binary=True)
    try:
        M = cv.fit_transform(pd.Series(texts).astype(str)).tocsc()
    except ValueError:      # vocabulario vacío
        return None
    codes = pd.factorize(np.asarray(groups))[0]
    G = sparse.csr_matrix((np.ones(len(codes)), (codes, np.arange(len(codes)))), shape=(codes.max() + 1, len(codes)))
    n_channels = np.asarray(((G @ M) > 0).sum(axis=0)).ravel()
    n_videos = np.asarray(M.sum(axis=0)).ravel()
    keep = np.where((n_channels >= k) & (n_videos >= f["min_df"]))[0]
    if len(keep) == 0:
        return None
    if len(keep) > f["max_features"]:
        keep = keep[np.argsort(-n_videos[keep], kind="stable")[: f["max_features"]]]
    return sorted(cv.get_feature_names_out()[keep].tolist())


def build_pipeline(cfg: dict, parts=("text", "meta"), vocabulary: list | None = None) -> Pipeline:
    f = cfg["features"]
    transformers = []
    if "text" in parts:
        vocab_kw = ({"vocabulary": vocabulary} if vocabulary
                    else {"min_df": f["min_df"], "max_features": f["max_features"]})
        transformers.append(("tfidf", TfidfVectorizer(
            lowercase=True, strip_accents="unicode", stop_words=STOPWORDS,
            ngram_range=tuple(f["ngram_range"]), sublinear_tf=True, **vocab_kw), "text"))
        if f.get("char_ngrams"):
            transformers.append(("tfidf_char", TfidfVectorizer(
                analyzer="char_wb", ngram_range=(3, 5), lowercase=True, strip_accents="unicode",
                min_df=f["min_df"], max_features=f["max_features"], sublinear_tf=True), "text"))
    if "meta" in parts:
        transformers.append(("meta", Pipeline([
            ("f", FunctionTransformer(meta_frame, validate=False)),
            ("s", StandardScaler()),
        ]), BASE_COLS))
        transformers.append(("niche", OneHotEncoder(handle_unknown="ignore"), ["niche_id"]))
    m = cfg["model"]
    kwargs = dict(C=m["C"], class_weight=m["class_weight"], max_iter=2000, random_state=cfg["seed"])
    if m.get("penalty") == "l1":
        kwargs.update(_l1_kwargs())   # L1 puro (más interpretable): deja en cero los términos que no aportan
    clf = LogisticRegression(**kwargs)
    return Pipeline([("features", ColumnTransformer(transformers)), ("clf", clf)])