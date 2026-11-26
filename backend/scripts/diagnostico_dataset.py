"""Diagnóstico de sesgos del dataset con los datos reales de la BD (no gasta cuota ni escribe nada).

Uso (desde backend/):
  python -m scripts.diagnostico_dataset              # revisión de la etiqueta y de posibles sesgos
  python -m scripts.diagnostico_dataset --shuffle    # además, prueba de fuga con etiquetas barajadas (tarda más)
  python -m scripts.diagnostico_dataset --method bins   # compara con el método anterior (línea base por franjas)
  python -m scripts.diagnostico_dataset --niche-ids 1,3,4   # solo esos nichos (los mismos con los que se entrenará)

Cada sección dice qué conviene mirar. Nada de esto cambia el modelo: solo mide.
"""
import argparse

import numpy as np
import pandas as pd

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows

QUERY = """
SELECT v.channel_id, c.niche_id, c.language, v.yt_video_id, v.title, v.published_at, v.duration_s,
       v.views, v.yt_category_id, v.is_short, v.fetched_at
FROM videos v JOIN channels c ON c.id = v.channel_id
WHERE c.niche_id IS NOT NULL
"""


def _h(texto: str) -> None:
    print(f"\n== {texto}")


def _size_buckets(ds: pd.DataFrame) -> pd.Series:
    """Tamaño relativo del canal DENTRO de su nicho (chico/mediano/grande), por su velocidad mediana."""
    med = ds.groupby(["niche_id", "channel_id"])["velocity"].median().reset_index()
    med["pct"] = med.groupby("niche_id")["velocity"].rank(pct=True)
    med["tamano"] = pd.cut(med["pct"], [0, 1 / 3, 2 / 3, 1.0], labels=["chico", "mediano", "grande"],
                           include_lowest=True)
    return ds["channel_id"].map(med.set_index("channel_id")["tamano"])


def diagnose(ds: pd.DataFrame, cfg: dict) -> None:
    from ml.service import MIN_CHANNELS, MIN_ROWS
    if ds.empty:
        print("El dataset quedó vacío: no hay videos que pasen los filtros.")
        return
    bins = cfg["label"]["age_bins"]
    names = {i: f"{bins[i]:g}-{bins[i + 1] - 1:g} d" for i in range(len(bins) - 1)}
    ds = ds.assign(franja=ds["age_bin"].map(names), tamano=_size_buckets(ds))

    _h("1. Resumen (todos los videos que pasan los filtros de limpieza)")
    print(f"Videos: {len(ds)} | canales: {ds['channel_id'].nunique()} | y=1: {ds['y'].mean():.1%}")

    _h("2. ¿Contra qué se comparó cada video? (lo ideal: contra su propio canal)")
    print((ds["baseline_src"].value_counts(normalize=True) * 100).round(1).astype(str).add(" %").to_string())

    _h("3. Por franja de edad  [mirar: pct_y1 y ratio_mediana parecidos entre franjas. Si pct_y1 baja con la edad pero "
       "ratio_mediana sigue cerca de 1, lo que cambia con la edad es la dispersión (ratio_p75 y p90), no el nivel]")
    tab = ds.groupby("age_bin").agg(
        videos=("y", "size"),
        pct_canal=("baseline_src", lambda s: round(100 * (s == "canal").mean(), 1)),
        pct_y1=("y", lambda s: round(100 * s.mean(), 1)),
        ratio_mediana=("ratio", lambda s: round(s.median(), 2)),
        ratio_p75=("ratio", lambda s: round(s.quantile(0.75), 2)),
        ratio_p90=("ratio", lambda s: round(s.quantile(0.90), 2)))
    tab.index = tab.index.map(names)
    print(tab.to_string())

    _h("4. Tasa de y=1 por tamaño de canal y origen de la línea base  "
       "[mirar: en 'canal' debería ser parecida entre tamaños; si en 'nicho' los grandes salen altos, hay sesgo de tamaño]")
    print(ds.pivot_table(index="tamano", columns="baseline_src", values="y", aggfunc="mean", observed=True).round(3).to_string())

    _h("5. Edad vs ratio DENTRO de cada franja (Spearman, solo línea base de canal)  "
       "[mirar: cerca de 0; negativo fuerte = los videos jóvenes de la franja salen 'mejores' solo por ser jóvenes]")
    base = ds[ds["baseline_src"] == "canal"]
    for b, g in base.groupby("age_bin"):
        if len(g) >= 30:
            print(f"  {names[b]:>10}: {g['age_days'].corr(g['ratio'], method='spearman'):+.2f}  (n={len(g)})")

    train, quitados = select_training_rows(ds, cfg)
    _h("6. Qué entra al entrenamiento")
    print(f"label.require_channel_baseline = {cfg['label'].get('require_channel_baseline', True)}")
    print(f"Videos quitados por no tener línea base de su canal: {quitados} de {len(ds)}")
    print(f"Quedan: {len(train)} videos y {train['channel_id'].nunique() if len(train) else 0} canales "
          f"(mínimo para entrenar: {MIN_ROWS} y {MIN_CHANNELS})")
    if len(train) < MIN_ROWS or (len(train) and train["channel_id"].nunique() < MIN_CHANNELS):
        print("  AVISO: no alcanza para entrenar; hay que ingestar más canales.")
    if train.empty:
        return

    _h("7. Por nicho, en lo que entra al entrenamiento  [regla acordada: menos de 12 canales -> quitar el nicho]")
    por_nicho = train.groupby("niche_id").agg(canales=("channel_id", "nunique"), videos=("y", "size"),
                                              pct_y1=("y", lambda s: round(100 * s.mean(), 1)))
    por_nicho["aviso"] = np.where(por_nicho["canales"] < 12, "<12 canales", "")
    print(por_nicho.to_string())

    _h("8. Concentración  [mirar: que pocos canales no dominen]")
    por_canal = train.groupby("channel_id").size().sort_values(ascending=False)
    print(f"Videos por canal: mín {por_canal.min()}, mediana {por_canal.median():.0f}, máx {por_canal.max()} | "
          f"los 5 canales con más videos aportan {por_canal.head(5).sum() / len(train):.1%}")
    tasa = train.groupby("channel_id")["y"].mean()
    print(f"Canales con y=1 en todos o en ninguno de sus videos: {((tasa == 0) | (tasa == 1)).mean():.1%} (informativo)")

    _h("9. Títulos repetidos en más de un canal (limpios)  [mirar: bajo; si es alto puede haber fuga entre canales]")
    t = train["title"].str.lower().str.strip()
    n_can = train.assign(_t=t).groupby("_t")["channel_id"].nunique()
    rep = n_can[n_can > 1]
    print(f"{len(rep)} títulos distintos, {t.isin(rep.index).mean():.1%} de los videos")

    _h("10. Duración vs y=1  (informativo: ¿la duración aporta señal?)")
    cubo = pd.cut(train["duration_s"], [0, 600, 1200, 3600, 7201], labels=["3-10 min", "10-20 min", "20-60 min", "1-2 h"])
    print(train.groupby(cubo, observed=True)["y"].agg(videos="size", pct_y1=lambda s: round(100 * s.mean(), 1)).to_string())


def shuffle_check(ds: pd.DataFrame, cfg: dict, n_rep: int = 3) -> None:
    """Entrena con etiquetas barajadas: el AUC en canales no vistos debe quedar cerca de 0.50. Si sale alto, hay fuga."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit

    from ml.features import build_pipeline, prepare_X

    X, y = prepare_X(ds, cfg), ds["y"].to_numpy()
    w, g = ds["weight"].to_numpy(dtype=float), ds["channel_id"].to_numpy()
    rng, aucs = np.random.default_rng(0), []
    for i in range(n_rep):
        ys = rng.permutation(y)
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=i).split(X, ys, g))
        if len(set(ys[tr])) < 2 or len(set(ys[te])) < 2:
            continue
        pipe = build_pipeline(cfg)
        pipe.fit(X.iloc[tr], ys[tr], clf__sample_weight=w[tr])
        aucs.append(roc_auc_score(ys[te], pipe.predict_proba(X.iloc[te])[:, 1]))
    _h("11. Prueba de fuga con etiquetas barajadas  [esperado: cerca de 0.50]")
    if aucs:
        print(f"AUC con etiquetas al azar: {np.mean(aucs):.3f} (repeticiones: {', '.join(f'{a:.3f}' for a in aucs)})")
        if np.mean(aucs) > 0.56:
            print("  AVISO: demasiado alto para etiquetas al azar; revisa fuga de información.")
    else:
        print("No se pudo calcular (pocas clases en la muestra de prueba).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shuffle", action="store_true", help="agrega la prueba de fuga con etiquetas barajadas")
    ap.add_argument("--method", choices=["age_adjusted", "bins"], default=None,
                    help="método de línea base (por defecto, el de ml/config.py)")
    ap.add_argument("--niche-ids", default=None, help="ids de nichos separados por coma, por ejemplo 1,3,4 (por defecto, todos)")
    args = ap.parse_args()
    from scripts._common import connect  # import aquí para poder probar diagnose() sin base de datos
    with connect() as conn:
        rows = conn.execute(QUERY).fetchall()
    if not rows:
        raise SystemExit("No hay videos en la BD con canal y nicho. Corre primero scripts.ingest.")
    over: dict = {}
    if args.method:
        over.setdefault("label", {})["method"] = args.method
    if args.niche_ids:
        over.setdefault("data", {})["niche_ids"] = [int(x) for x in args.niche_ids.split(",")]
    cfg = merge_cfg(over or None)
    print(f"Método de línea base: {cfg['label']['method']} | nichos: {cfg['data'].get('niche_ids') or 'todos'}")
    ds = build_dataset(pd.DataFrame(rows), cfg)
    diagnose(ds, cfg)
    if args.shuffle:
        train, _ = select_training_rows(ds, cfg)
        if len(train):
            shuffle_check(train, cfg)


if __name__ == "__main__":
    main()