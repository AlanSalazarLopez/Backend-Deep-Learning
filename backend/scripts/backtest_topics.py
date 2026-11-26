"""¿Los temas que pegaban antes siguen pegando después? Prueba retrospectiva con el CSV (sin BD, sin cuota).

Uso (desde backend/):
  python -m scripts.backtest_topics --csv ..\\export\\videos.csv --niche-ids 1,3,4,5
  python -m scripts.backtest_topics --csv ..\\export\\videos.csv --niche-ids 1,3,4,5 --cutoff-days 45 --k 15

Cómo funciona, por nicho:
  1. Los videos con edad >= cutoff-days son el "pasado" y los más recientes son el "futuro".
  2. Con el pasado se arma un ranking de términos (palabras y bigramas) por lift suavizado, igual que topic_ranking,
     pero exigiendo que el término aparezca en al menos --min-channels canales distintos.
  3. En el futuro se mide qué tan seguido y_ = 1 ocurre en los videos que contienen alguno de los k mejores términos,
     contra la tasa base del nicho en el futuro (lift_futuro).
  4. Control: lo mismo con k términos elegidos al azar entre los elegibles (--draws veces). Si el ranking sirve,
     lift_futuro queda por encima del p95 del azar. También se mide con los k PEORES términos (debería quedar bajo 1).
Es la prueba más honesta de "temas que pegan ahora" con los datos que ya tenemos: no necesita datos nuevos.
Límite: los videos de un mismo canal se parecen entre sí, así que el p-valor es optimista; mira los canales que aportan.
"""
import argparse
import warnings

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows
from ml.text import STOPWORDS
from scripts.run_experiments import load_videos

warnings.filterwarnings("ignore")
PRIOR_VIDEOS = 8     # igual que ml/topics.py: videos "virtuales" con la tasa base del nicho


def _lift_stat(M_new, y_new, g_new, cols):
    """(lift sobre la tasa base, videos con algún término, canales distintos que aportan)."""
    if len(cols) == 0:
        return np.nan, 0, 0
    hit = np.asarray(M_new[:, cols].sum(axis=1)).ravel() > 0
    if hit.sum() == 0 or y_new.mean() == 0:
        return np.nan, int(hit.sum()), 0
    return float(y_new[hit].mean() / y_new.mean()), int(hit.sum()), int(len(set(g_new[hit])))


def backtest_niche(ds_n: pd.DataFrame, cutoff: float, k: int, min_videos: int, min_channels: int, draws: int, seed: int = 0):
    old, new = ds_n[ds_n["age_days"] >= cutoff], ds_n[ds_n["age_days"] < cutoff]
    if len(old) < 200 or len(new) < 100:
        return {"error": f"pocos videos (pasado {len(old)}, futuro {len(new)}; mínimo 200 y 100)"}
    cv = CountVectorizer(lowercase=True, strip_accents="unicode", stop_words=STOPWORDS, ngram_range=(1, 2),
                         min_df=min_videos, binary=True)
    try:
        M_old = cv.fit_transform(old["title"].astype(str)).tocsc()
    except ValueError:
        return {"error": "vocabulario vacío"}
    terms = cv.get_feature_names_out()
    y_old = old["y"].to_numpy(dtype=float)
    g_old = old["channel_id"].to_numpy()
    codes = pd.factorize(g_old)[0]
    from scipy import sparse
    G = sparse.csr_matrix((np.ones(len(codes)), (codes, np.arange(len(codes)))), shape=(codes.max() + 1, len(codes)))
    n_ch = np.asarray(((G @ M_old) > 0).sum(axis=0)).ravel()
    n_vid = np.asarray(M_old.sum(axis=0)).ravel()
    ok = np.where((n_ch >= min_channels) & ~np.array([t.replace(" ", "").isdigit() for t in terms]))[0]
    if len(ok) < 2 * k:
        return {"error": f"pocos términos elegibles ({len(ok)}) con {min_channels}+ canales"}
    base = y_old.mean()
    num = np.asarray(M_old.T @ y_old).ravel()
    win = (num + PRIOR_VIDEOS * base) / (n_vid + PRIOR_VIDEOS)
    order = ok[np.argsort(-win[ok], kind="stable")]
    top, bottom = order[:k], order[::-1][:k]

    M_new = cv.transform(new["title"].astype(str)).tocsc()
    y_new, g_new = new["y"].to_numpy(dtype=float), new["channel_id"].to_numpy()
    lift_top, n_hit, ch_hit = _lift_stat(M_new, y_new, g_new, top)
    lift_bot, _, _ = _lift_stat(M_new, y_new, g_new, bottom)
    rng = np.random.default_rng(seed)
    rand = np.array([_lift_stat(M_new, y_new, g_new, rng.choice(ok, size=k, replace=False))[0] for _ in range(draws)])
    rand = rand[~np.isnan(rand)]
    pval = float((rand >= lift_top).mean()) if len(rand) and not np.isnan(lift_top) else np.nan
    return {"n_old": len(old), "n_new": len(new), "elegibles": len(ok), "base_new": float(y_new.mean()),
            "lift_top": lift_top, "n_hit": n_hit, "canales_hit": ch_hit, "lift_bottom": lift_bot,
            "azar_media": float(rand.mean()) if len(rand) else np.nan,
            "azar_p95": float(np.quantile(rand, 0.95)) if len(rand) else np.nan, "p_valor": pval,
            "top_terms": [(str(terms[i]), int(n_ch[i])) for i in top[:8]]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="../export/videos.csv")
    ap.add_argument("--niche-ids", default=None)
    ap.add_argument("--cutoff-days", type=float, default=60, help="edad que separa pasado (>=) de futuro (<)")
    ap.add_argument("--k", type=int, default=20, help="cuántos términos top se prueban")
    ap.add_argument("--min-videos", type=int, default=5)
    ap.add_argument("--min-channels", type=int, default=3)
    ap.add_argument("--draws", type=int, default=300)
    args = ap.parse_args()

    df = load_videos(args.csv)
    ids = [int(x) for x in args.niche_ids.split(",")] if args.niche_ids else None
    cfg = merge_cfg({"data": {"niche_ids": ids}} if ids else None)
    ds, _ = select_training_rows(build_dataset(df, cfg), cfg)
    print(f"Videos: {len(ds)} | canales: {ds['channel_id'].nunique()} | pasado = edad >= {args.cutoff_days:g} d, futuro = más recientes")
    print(f"Prueba: top-{args.k} términos del pasado (en {args.min_channels}+ canales) vs azar, medido en el futuro\n")
    resultados = []
    for nid, g in ds.groupby("niche_id"):
        r = backtest_niche(g, args.cutoff_days, args.k, args.min_videos, args.min_channels, args.draws)
        if "error" in r:
            print(f"nicho {nid}: omitido ({r['error']})")
            continue
        resultados.append(r)
        veredicto = "SIRVE" if (r["lift_top"] > r["azar_p95"]) else ("dudoso" if r["lift_top"] > r["azar_media"] else "no sirve")
        print(f"nicho {nid}: pasado {r['n_old']}, futuro {r['n_new']} videos, {r['elegibles']} términos elegibles")
        print(f"  lift de los {args.k} mejores términos en el futuro: {r['lift_top']:.2f} "
              f"({r['n_hit']} videos de {r['canales_hit']} canales) | azar: media {r['azar_media']:.2f}, p95 {r['azar_p95']:.2f} "
              f"| p-valor {r['p_valor']:.3f} | los {args.k} peores: {r['lift_bottom']:.2f}  -> {veredicto}")
        print("  mejores del pasado (canales): " + ", ".join(f"{t} ({c})" for t, c in r["top_terms"]))
    if resultados:
        top = np.nanmean([r["lift_top"] for r in resultados])
        azar = np.nanmean([r["azar_media"] for r in resultados])
        bot = np.nanmean([r["lift_bottom"] for r in resultados])
        sirven = sum(r["lift_top"] > r["azar_p95"] for r in resultados)
        print(f"\nResumen: lift promedio mejores {top:.2f} | azar {azar:.2f} | peores {bot:.2f} | "
              f"nichos donde supera el p95 del azar: {sirven} de {len(resultados)}")
        print("Si los mejores quedan arriba del azar y los peores abajo en la mayoría de nichos, los temas sí persisten.")
        print("Si todo queda cerca de 1.0, el ranking de temas del pasado no predice el futuro y no hay que prometerlo.")


if __name__ == "__main__":
    main()