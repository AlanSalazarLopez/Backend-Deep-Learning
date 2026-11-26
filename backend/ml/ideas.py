"""Ideas que rinden por encima de lo normal, agrupadas por tema (hot y atemporales).

NO predice el futuro. Describe qué temas están rindiendo más que lo habitual DE SU PROPIO CANAL
(el `ratio` de ml/dataset.py ya descuenta el tamaño del canal y la edad del video).

Cómo funciona, por nicho:
  1. Agrupa los títulos parecidos en temas (TF-IDF + clustering jerárquico). No usa el rendimiento para agrupar.
  2. Para cada tema mide el rendimiento por canal y promedia ENTRE canales (cada canal cuenta una vez),
     así un solo canal no puede inflar un tema.
  3. Calcula un límite inferior conservador (t de Student sobre los canales, 95 % unilateral): el tema solo
     califica si ese límite queda por encima de "lo normal" (lift 1.0).
  4. Clasifica: HOT = rinde bien en la ventana reciente (3-45 d) y más que antes; EVERGREEN = rinde bien en
     las dos ventanas (reciente y 45-180 d).
  5. Calibración: repite todo con el rendimiento barajado dentro de cada canal. Un tema es "robusto" solo si su
     límite inferior supera el p95 del mejor tema que produce el azar. Un nicho sin temas robustos tiene señal "baja".
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from .text import STOPWORDS

RECENT = (3.0, 45.0)
OLD = (45.0, 181.0)
ANY_AGE = (0.0, 1e9)
LOG_1_1 = float(np.log(1.1))


@dataclass
class IdeasParams:
    distance: float = 0.92         # umbral de distancia coseno para unir títulos (más bajo = temas más estrictos)
    min_videos: int = 4            # videos mínimos por tema
    min_channels: int = 3          # canales distintos mínimos por tema
    max_share: float = 0.5         # un solo canal no puede aportar más de esta fracción del tema
    hot_jump: float = 0.2          # cuánto debe subir (en log) el rendimiento reciente frente al anterior
    n_null: int = 50               # repeticiones de la calibración
    min_niche_channels: int = 12   # regla acordada: menos de 12 canales -> nicho sin información suficiente
    min_niche_videos: int = 300
    n_examples: int = 3
    top: int = 15


# ----------------------------------------------------------------------------- agrupación
def cluster_titles(titles: list[str], distance: float):
    """Devuelve (etiquetas, matriz TF-IDF, vectorizador) o (None, None, None) si no hay vocabulario."""
    vec = TfidfVectorizer(lowercase=True, strip_accents="unicode", stop_words=STOPWORDS,
                          ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    try:
        X = vec.fit_transform(titles)
    except ValueError:
        return None, None, None
    if X.shape[0] < 2 or X.shape[1] == 0:
        return None, None, None
    D = np.clip(1.0 - (X @ X.T).toarray(), 0.0, None)   # TF-IDF ya viene normalizado: coseno = producto punto
    np.fill_diagonal(D, 0.0)
    labels = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
                                     distance_threshold=distance).fit_predict(D)
    return labels, X, vec


def _label(X, terms, idx, k: int = 3) -> str:
    w = np.asarray(X[idx].mean(axis=0)).ravel()
    chosen: list[str] = []
    for j in np.argsort(-w)[:8]:
        if w[j] <= 0:
            break
        t = str(terms[j])
        if any(t in c or c in t for c in chosen):
            continue
        chosen.append(t)
        if len(chosen) == k:
            break
    return " · ".join(chosen)


# ----------------------------------------------------------------------------- estadística por tema
def _window(lr, ch, age, lo, hi) -> dict:
    """Rendimiento (log-ratio) medio ENTRE canales dentro de una ventana de edad, con límite inferior."""
    m = (age >= lo) & (age < hi)
    n = int(m.sum())
    if n == 0:
        return {"n": 0, "nc": 0, "m": np.nan, "lb": np.nan}
    _, inv = np.unique(ch[m], return_inverse=True)
    means = np.bincount(inv, weights=lr[m]) / np.bincount(inv)
    nc = len(means)
    mean = float(means.mean())
    lb = np.nan                      # con un solo canal no hay evidencia
    if nc >= 2:
        se = means.std(ddof=1) / np.sqrt(nc)
        lb = float(mean - stats.t.ppf(0.95, nc - 1) * se)
    return {"n": n, "nc": nc, "m": mean, "lb": lb}


def _eligible(members, ch, p: IdeasParams):
    """Temas con tamaño suficiente y sin dominio de un solo canal (no depende del rendimiento)."""
    out = []
    for idx in members:
        n = len(idx)
        if n < p.min_videos:
            continue
        counts = np.bincount(ch[idx])
        counts = counts[counts > 0]
        if len(counts) < p.min_channels or counts.max() / n > p.max_share:
            continue
        out.append((idx, float(counts.max() / n)))
    return out


def _classify(rec, old, allw, p: IdeasParams):
    hot = (rec["n"] >= 3 and rec["nc"] >= 3 and rec["lb"] > 0
           and (old["n"] < 2 or rec["m"] - old["m"] >= p.hot_jump))
    ever = (rec["n"] >= 2 and old["n"] >= 2 and allw["nc"] >= 4 and rec["m"] > LOG_1_1
            and old["m"] > LOG_1_1 and allw["lb"] > 0)
    return "hot" if hot else ("evergreen" if ever else None)


def _evaluate(lr, age, ch, eligible, p: IdeasParams) -> list[dict]:
    out = []
    for idx, share in eligible:
        l, c, a = lr[idx], ch[idx], age[idx]
        rec, old, allw = _window(l, c, a, *RECENT), _window(l, c, a, *OLD), _window(l, c, a, *ANY_AGE)
        clase = _classify(rec, old, allw, p)
        if clase:
            out.append({"idx": idx, "clase": clase, "rec": rec, "old": old, "all": allw, "share": share})
    return out


def _x(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(np.exp(v)), 2)


# ----------------------------------------------------------------------------- API
def compute_niche_ideas(ds_n: pd.DataFrame, params: IdeasParams | None = None, seed: int = 0) -> dict:
    """ds_n: salida de build_dataset (+ select_training_rows) de UN nicho. Devuelve un dict listo para JSON."""
    p = params or IdeasParams()
    ds_n = ds_n.reset_index(drop=True)
    info = {"videos": int(len(ds_n)), "canales": int(ds_n["channel_id"].nunique())}
    vacio = {"hot": [], "evergreen": [], "calibracion": None}
    if info["canales"] < p.min_niche_channels or info["videos"] < p.min_niche_videos:
        return {**info, **vacio, "estado": "insuficiente",
                "motivo": f"{info['canales']} canales y {info['videos']} videos "
                          f"(mínimo {p.min_niche_channels} y {p.min_niche_videos})"}

    titles = ds_n["title"].astype(str).tolist()
    labels, X, vec = cluster_titles(titles, p.distance)
    if labels is None:
        return {**info, **vacio, "estado": "insuficiente", "motivo": "sin vocabulario suficiente"}
    terms = vec.get_feature_names_out()

    ratio = ds_n["ratio"].to_numpy(float)
    lr = np.log(np.clip(ratio, 1e-3, 5.0))   # topa en 5x: un video viral aislado no define un tema
    age = ds_n["age_days"].to_numpy(float)
    ch = pd.factorize(ds_n["channel_id"])[0]
    members = [np.where(labels == k)[0] for k in np.unique(labels)]
    eligible = _eligible(members, ch, p)
    real = _evaluate(lr, age, ch, eligible, p)

    # calibración: mismo análisis con el rendimiento barajado dentro de cada canal
    rng = np.random.default_rng(seed)
    by_ch = [np.where(ch == c)[0] for c in np.unique(ch)]
    nh, ne, mh, me = [], [], [], []   # conteos y mejor límite inferior que produce el azar, por clase
    for _ in range(p.n_null):
        ls = lr.copy()
        for pos in by_ch:
            ls[pos] = rng.permutation(lr[pos])
        res = _evaluate(ls, age, ch, eligible, p)
        nh.append(sum(r["clase"] == "hot" for r in res))
        ne.append(sum(r["clase"] == "evergreen" for r in res))
        mh.append(max([r["rec"]["lb"] for r in res if r["clase"] == "hot"], default=0.0))
        me.append(max([r["all"]["lb"] for r in res if r["clase"] == "evergreen"], default=0.0))
    umbral = {"hot": float(np.quantile(mh, 0.95)), "evergreen": float(np.quantile(me, 0.95))}
    n_hot = sum(r["clase"] == "hot" for r in real)
    n_ever = sum(r["clase"] == "evergreen" for r in real)
    cal = {
        "hot": {"reales": n_hot, "azar_media": round(float(np.mean(nh)), 1), "azar_p95": float(np.quantile(nh, 0.95)),
                },
        "evergreen": {"reales": n_ever, "azar_media": round(float(np.mean(ne)), 1),
                      "azar_p95": float(np.quantile(ne, 0.95))},
        "temas_evaluados": len(eligible),
    }

    cols = ds_n[["yt_video_id", "title", "channel_id"]]
    items = {"hot": [], "evergreen": []}
    for r in real:
        idx = r["idx"]
        pool = idx[age[idx] < RECENT[1]] if r["clase"] == "hot" else idx
        examples, seen = [], set()
        for j in pool[np.argsort(-ratio[pool])]:
            if ch[j] in seen:
                continue
            seen.add(ch[j])
            examples.append({"yt_video_id": str(cols.iloc[j]["yt_video_id"]), "titulo": str(cols.iloc[j]["title"]),
                             "channel_id": int(cols.iloc[j]["channel_id"]), "ratio": round(float(ratio[j]), 2)})
            if len(examples) == p.n_examples:
                break
        key = r["rec"] if r["clase"] == "hot" else r["all"]
        items[r["clase"]].append({
            "robusto": bool(key["lb"] > umbral[r["clase"]]),
            "tema": _label(X, terms, idx), "lift_reciente": _x(r["rec"]["m"]), "lift_antiguo": _x(r["old"]["m"]) if r["old"]["n"] >= 2 else None,
            "lift_minimo": _x(key["lb"]), "videos": int(len(idx)), "videos_recientes": r["rec"]["n"],
            "canales": r["all"]["nc"], "max_share_un_canal": round(r["share"], 2), "ejemplos": examples})
    for k in items:
        items[k].sort(key=lambda d: (-d["robusto"], -(d["lift_minimo"] or 0)))
        cal[k]["robustos"] = int(sum(d["robusto"] for d in items[k]))
        cal[k]["senal"] = "alta" if cal[k]["robustos"] > 0 else "baja"
        items[k] = items[k][: p.top]
    return {**info, "estado": "ok", "calibracion": cal, **items}