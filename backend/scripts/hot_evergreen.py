"""Temas "hot", temas atemporales y patrones de título, con evidencia. Usa el CSV (sin BD, sin cuota).

Uso (desde backend/):
  python -m scripts.hot_evergreen --csv ..\\export\\videos.csv --niche-ids 1,3,4,5

Qué produce (y qué NO promete):
  A) PATRONES de título ("TOP 10", "hice/probé…", "cómo…", "gratis"…). Para cada patrón compara, DENTRO de cada canal,
     los videos con el patrón contra los que no lo tienen (así el tamaño del canal no cuenta). Promedia entre canales,
     da un intervalo de confianza al 99% (bootstrap sobre canales) y revisa que el efecto tenga el mismo signo en tres
     ventanas de edad. "Atemporal" = intervalo por encima de 1 y mismo signo en las ventanas con datos. Es asociación,
     no causalidad.
  B) TEMAS (palabras y bigramas) por nicho, en tres ventanas de edad: reciente (3-45 d), medio (45-90) y antiguo (90-180).
     HOT = rinde muy por encima de lo normal en la ventana reciente, en 3+ canales, y bastante más que antes.
     ATEMPORAL = rinde por encima de lo normal en las tres ventanas.
     Se descartan términos dominados por un solo canal.
  C) CALIBRACIÓN: se repite B con el rendimiento barajado dentro de cada canal. Eso dice cuántos temas "hot" o
     "atemporales" saldrían solo por azar con tus datos. Si el número real no supera claramente al del azar,
     no hay evidencia y la lista es ruido.
Ventanas de unos 45 días porque hay 30 a 60 videos por semana por nicho: por semana, un término típico aparece en 1 o 2.
Escribe experiments/patrones.csv y experiments/temas.csv.
"""
import argparse
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows
from ml.text import EMOJI_RE, STOPWORDS, strip_accents
from scripts.run_experiments import load_videos

warnings.filterwarnings("ignore")

# Se aplican al título limpio, en minúsculas y sin acentos.
PLANTILLAS = {
    "TOP N / N mejores": r"\btops?\s*\d+|\b\d+\s+(mejores|peores|cosas|trucos|formas|maneras|razones|errores|ideas|consejos|juegos|apps|herramientas)\b",
    "hice/probé (experiencia)": r"\b(hice|hicimos|probe|probamos|intente|intentamos|construi|construimos|compre|compramos|gaste|sobrevivi|jugue|jugamos)\b",
    "cómo + verbo": r"\bcomo (hacer|hago|se |puedes|puedo|crear|ganar|aprender|elegir|usar|instalar|conseguir|lograr|ser|tener)",
    "por qué": r"\bpor ?que\b",
    "secreto/nadie/verdad": r"\b(secreto|secretos|nadie|verdad|oculto|oculta|nunca)\b",
    "gratis": r"\bgratis\b|\bsin pagar\b",
    "nuevo/nueva": r"\bnuev[oa]s?\b",
    "mejor(es)": r"\bmejor(es)?\b",
    "vs / contra": r"\bvs\.?\b|\bcontra\b",
    "tutorial/curso/guía": r"\b(tutorial|curso|guia|clase|aprende)\b",
    "reto/desafío": r"\b(reto|desafio|challenge)\b",
    "completo/definitivo": r"\b(completo|completa|completos|definitiva|definitivo)\b",
    "en N minutos/horas/días": r"\ben\s+\d+\s+(minutos|min|horas|dias|segundos)\b",
    "año 2024-2029": r"\b202[4-9]\b",
    "tiene un número": r"\d",
    "pregunta (¿?)": r"[?¿]",
    "exclamación (!¡)": r"[!¡]",
}
PLANTILLAS = {k: re.sub(r"\((?!\?)", "(?:", v) for k, v in PLANTILLAS.items()}   # grupos sin captura
VENTANAS = {"reciente": (3, 45), "medio": (45, 90), "antiguo": (90, 181)}
PRIOR_VIDEOS = 8


# ----------------------------------------------------------------------------- A) patrones
def flags_de_patrones(ds: pd.DataFrame) -> pd.DataFrame:
    low = ds["title"].astype(str).map(lambda s: strip_accents(s.lower()))
    out = pd.DataFrame({n: low.str.contains(rx, regex=True) for n, rx in PLANTILLAS.items()}, index=ds.index)
    out["emoji"] = ds["title"].astype(str).map(lambda s: bool(EMOJI_RE.search(s)))
    out["título largo (>60 car.)"] = ds["title"].astype(str).str.len() > 60
    out["título corto (<30 car.)"] = ds["title"].astype(str).str.len() < 30
    return out


def efecto_pareado(d: pd.DataFrame, flag: str, min_each: int = 3, min_canales: int = 5, n_boot: int = 2000, seed: int = 0):
    """Efecto del patrón dentro de cada canal (log-ratio con patrón menos sin patrón), promediado entre canales."""
    diffs, n_con = [], 0
    for _, g in d.groupby("channel_id"):
        a, b = g[g[flag]], g[~g[flag]]
        if len(a) >= min_each and len(b) >= min_each:
            diffs.append(a["lr"].mean() - b["lr"].mean())
            n_con += len(a)
    if len(diffs) < min_canales:
        return None
    diffs = np.array(diffs)
    boot = np.random.default_rng(seed).choice(diffs, size=(n_boot, len(diffs))).mean(axis=1)
    lo, hi = np.quantile(boot, [0.005, 0.995])
    return {"canales": len(diffs), "videos_con": n_con, "efecto": float(np.exp(diffs.mean())),
            "ic99_bajo": float(np.exp(lo)), "ic99_alto": float(np.exp(hi)), "pct_canales_a_favor": float((diffs > 0).mean())}


def analizar_patrones(ds: pd.DataFrame, grupo: str) -> list[dict]:
    ds = ds.assign(lr=np.log(ds["ratio"].clip(lower=1e-3)))
    fl = flags_de_patrones(ds)
    filas = []
    for nombre in fl.columns:
        d = pd.concat([ds[["channel_id", "lr", "age_days"]], fl[[nombre]].rename(columns={nombre: "flag"})], axis=1)
        tot = efecto_pareado(d, "flag")
        if tot is None:
            continue
        signos = []
        for _, (lo, hi) in VENTANAS.items():
            w = efecto_pareado(d[(d["age_days"] >= lo) & (d["age_days"] < hi)], "flag", min_each=2, min_canales=5)
            if w is not None:
                signos.append(w["efecto"] > 1)
        estable = len(signos) >= 2 and (all(signos) or not any(signos))
        if tot["ic99_bajo"] > 1 and estable and all(signos):
            clase = "ATEMPORAL (favorable)"
        elif tot["ic99_alto"] < 1 and estable and not any(signos):
            clase = "desfavorable"
        else:
            clase = "sin evidencia"
        filas.append({"grupo": grupo, "patron": nombre, "clase": clase, "ventanas_con_datos": len(signos),
                      "mismo_signo_en_ventanas": bool(estable), **tot})
    return filas


# ----------------------------------------------------------------------------- B) temas
def _matrices(ds_n: pd.DataFrame, min_df: int):
    cv = CountVectorizer(lowercase=True, strip_accents="unicode", stop_words=STOPWORDS, ngram_range=(1, 2),
                         min_df=min_df, binary=True)
    M = cv.fit_transform(ds_n["title"].astype(str)).tocsr()
    codes = pd.factorize(ds_n["channel_id"].to_numpy())[0]
    G = sparse.csr_matrix((np.ones(len(codes)), (codes, np.arange(len(codes)))), shape=(codes.max() + 1, len(codes)))
    return cv.get_feature_names_out(), M, G.tocsc(), codes


def _estaticos(M, G):
    C = (G @ M).toarray()                       # canales x términos: videos con el término en cada canal
    tot = C.sum(axis=0)
    return {"ch_total": (C > 0).sum(axis=0), "share": np.where(tot > 0, C.max(axis=0) / np.maximum(tot, 1), 1.0),
            "n_total": tot}


def _stats_ventanas(M, y, age, G, prior=PRIOR_VIDEOS):
    out = {}
    for nombre, (lo, hi) in {**VENTANAS, "antes": (45, 181)}.items():
        m = (age >= lo) & (age < hi)
        idx = np.where(m)[0]
        n = np.asarray(M[idx].sum(axis=0)).ravel()
        base = y[idx].mean() if len(idx) else np.nan
        ny = np.asarray(M[idx].T @ y[idx]).ravel()
        lift = ((ny + prior * base) / (n + prior)) / base if base and base > 0 else np.full(M.shape[1], np.nan)
        ch = np.asarray(((G[:, idx] @ M[idx]) > 0).sum(axis=0)).ravel()
        out[nombre] = (n, lift, ch)
    return out


def _clasificar(st, est, hot_lift, hot_salto, ever_lift, max_share, min_canales):
    nR, lR, cR = st["reciente"]
    lB = st["antes"][1]
    ok = (est["share"] <= max_share) & (est["ch_total"] >= min_canales)
    hot = (nR >= 5) & (cR >= 3) & (lR >= hot_lift) & ((lR - lB) >= hot_salto) & ok
    ever = np.all([(st[w][0] >= 3) & (st[w][1] >= ever_lift) for w in VENTANAS], axis=0) & ok & (est["ch_total"] >= 5) & ~hot
    return hot, ever


def analizar_temas(ds_n: pd.DataFrame, hot_lift=1.4, hot_salto=0.25, ever_lift=1.1, max_share=0.5, min_canales=3,
                   min_df=8, n_null=20, seed=0):
    terms, M, G, codes = _matrices(ds_n, min_df)
    y, age = ds_n["y"].to_numpy(dtype=float), ds_n["age_days"].to_numpy(dtype=float)
    est = _estaticos(M, G)
    st = _stats_ventanas(M, y, age, G)
    hot, ever = _clasificar(st, est, hot_lift, hot_salto, ever_lift, max_share, min_canales)
    filas = []
    for j in np.where(hot | ever)[0]:
        filas.append({"termino": str(terms[j]), "clase": "HOT" if hot[j] else "ATEMPORAL",
                      "lift_reciente": round(float(st["reciente"][1][j]), 2), "lift_medio": round(float(st["medio"][1][j]), 2),
                      "lift_antiguo": round(float(st["antiguo"][1][j]), 2), "videos_recientes": int(st["reciente"][0][j]),
                      "canales_recientes": int(st["reciente"][2][j]), "canales_total": int(est["ch_total"][j]),
                      "videos_total": int(est["n_total"][j]), "max_share_un_canal": round(float(est["share"][j]), 2)})
    # calibración: mismo análisis con el rendimiento barajado dentro de cada canal
    rng = np.random.default_rng(seed)
    by_ch = [np.where(codes == c)[0] for c in np.unique(codes)]
    nh, ne = [], []
    for _ in range(n_null):
        ys = y.copy()
        for pos in by_ch:
            ys[pos] = rng.permutation(y[pos])
        h, e = _clasificar(_stats_ventanas(M, ys, age, G), est, hot_lift, hot_salto, ever_lift, max_share, min_canales)
        nh.append(int(h.sum()))
        ne.append(int(e.sum()))
    resumen = {"terminos_evaluados": len(terms), "hot": int(hot.sum()), "atemporal": int(ever.sum()),
               "hot_por_azar": float(np.mean(nh)), "atemporal_por_azar": float(np.mean(ne)),
               "hot_azar_p95": float(np.quantile(nh, 0.95)), "atemporal_azar_p95": float(np.quantile(ne, 0.95))}
    return pd.DataFrame(filas), resumen


# ----------------------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="../export/videos.csv")
    ap.add_argument("--niche-ids", default=None)
    ap.add_argument("--top", type=int, default=8, help="cuántos temas mostrar por clase y nicho")
    ap.add_argument("--hot-lift", type=float, default=1.4)
    ap.add_argument("--hot-salto", type=float, default=0.25, help="cuánto debe subir el lift reciente frente a lo anterior")
    ap.add_argument("--ever-lift", type=float, default=1.1)
    ap.add_argument("--out-dir", default="experiments")
    args = ap.parse_args()

    df = load_videos(args.csv)
    ids = [int(x) for x in args.niche_ids.split(",")] if args.niche_ids else None
    cfg = merge_cfg({"data": {"niche_ids": ids}} if ids else None)
    ds, _ = select_training_rows(build_dataset(df, cfg), cfg)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Videos: {len(ds)} | canales: {ds['channel_id'].nunique()} | nichos: {sorted(int(x) for x in ds['niche_id'].unique())}")

    print("\n== A) PATRONES DE TÍTULO (efecto dentro del mismo canal, IC al 99%; con ~100 pruebas, 1 o 2 falsos positivos son normales)")
    filas = analizar_patrones(ds, "todos")
    for nid, g in ds.groupby("niche_id"):
        filas += analizar_patrones(g, f"nicho {nid}")
    pat = pd.DataFrame(filas)
    if pat.empty:
        print("No hay canales suficientes para comparar patrones.")
    else:
        pat.round(3).to_csv(out / "patrones.csv", index=False)
        for grupo, g in pat.groupby("grupo", sort=False):
            g = g.sort_values("efecto", ascending=False)
            print(f"\n[{grupo}]  (efecto = veces lo normal de su canal cuando el título tiene el patrón)")
            for _, r in g[g["clase"] != "sin evidencia"].iterrows():
                print(f"  {r['clase']:<22} {r['patron']:<28} x{r['efecto']:.2f}  IC99 [{r['ic99_bajo']:.2f}, {r['ic99_alto']:.2f}]  "
                      f"{r['canales']} canales, {r['pct_canales_a_favor']:.0%} a favor")
            n_sin = int((g["clase"] == "sin evidencia").sum())
            print(f"  ({n_sin} patrones sin evidencia suficiente)")

    print("\n== B) TEMAS por nicho (ventanas: reciente 3-45 d, medio 45-90, antiguo 90-180)")
    todos = []
    for nid, g in ds.groupby("niche_id"):
        tabla, rs = analizar_temas(g, hot_lift=args.hot_lift, hot_salto=args.hot_salto, ever_lift=args.ever_lift)
        print(f"\nnicho {nid}: {rs['terminos_evaluados']} términos evaluados")
        print(f"  CALIBRACIÓN  hot: {rs['hot']} reales vs {rs['hot_por_azar']:.1f} por azar (p95 {rs['hot_azar_p95']:.0f}) | "
              f"atemporales: {rs['atemporal']} reales vs {rs['atemporal_por_azar']:.1f} por azar (p95 {rs['atemporal_azar_p95']:.0f})")
        veredicto = []
        if rs["hot"] <= rs["hot_azar_p95"]:
            veredicto.append("hot: no supera al azar, tratar como ruido")
        if rs["atemporal"] <= rs["atemporal_azar_p95"]:
            veredicto.append("atemporales: no superan al azar, tratar como ruido")
        if veredicto:
            print("  AVISO: " + "; ".join(veredicto))
        if tabla.empty:
            continue
        tabla.insert(0, "nicho", nid)
        todos.append(tabla)
        for clase in ("HOT", "ATEMPORAL"):
            t = tabla[tabla["clase"] == clase].sort_values("lift_reciente", ascending=False).head(args.top)
            for _, r in t.iterrows():
                print(f"  {clase:<9} {r['termino']:<26} lift {r['lift_antiguo']:.2f} -> {r['lift_medio']:.2f} -> {r['lift_reciente']:.2f}  "
                      f"({r['videos_recientes']} videos recientes, {r['canales_total']} canales, máx {r['max_share_un_canal']:.0%} de un canal)")
    if todos:
        pd.concat(todos).to_csv(out / "temas.csv", index=False)
    print(f"\nArchivos en {out}/: patrones.csv" + (", temas.csv" if todos else ""))
    print("Lectura: confía solo donde la CALIBRACIÓN supera al azar. Un lift es 'veces lo normal del canal'; 1.0 = normal.")


if __name__ == "__main__":
    main()