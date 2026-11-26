"""Experimentos de ML sobre un CSV (sin base de datos, sin --activate, no toca nada).

Uso (desde backend/, con el entorno activo):
  python -m scripts.export_videos                                   # genera ..\\export\\videos.csv
  python -m scripts.run_experiments --csv ..\\export\\videos.csv --niche-ids 1,3,4 --quick
  python -m scripts.run_experiments --csv ..\\export\\videos.csv --niche-ids 1,3,4 --seeds 10

Qué hace (PLAN_proyecto.md, 2.6, un paso a la vez y fijando lo mejor):
  1. θ (1.3, 2.0) y modo percentile   2. método de línea base (bins)   3. vocabulario por canales (min_channels)
  4. texto (min_df, max_features, caracteres)   5. modelo (C, class_weight, L1)   6. vida media (7, 14, 45, 60, sin peso)
Después compara la configuración de fábrica contra la mejor con semillas NUEVAS (para no premiar el azar de la
selección) y hace la prueba de fuga con etiquetas barajadas dentro de cada canal.

Escribe en experiments/: runs_log.csv (una fila por corrida, se guarda después de cada una), best_config.json
(JSON parcial, listo para train_model --config) y resumen.md.
"""
import argparse
import copy
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ml import service
from ml.config import DEFAULT_CFG, merge_cfg
from ml.service import NotEnoughData, load_model, predict, train

warnings.filterwarnings("ignore")

REQUIRED = ["channel_id", "niche_id", "yt_video_id", "title", "published_at", "duration_s", "views", "fetched_at"]

# (nombre del paso, [(etiqueta de la corrida, override parcial), ...], ¿se elige por AUC?). La opción de fábrica ya es
# la base de cada paso. Los pasos 1 y 2 cambian la ETIQUETA: cada opción plantea una tarea distinta (otra tasa base,
# otros videos), así que su AUC no es comparable y no se usa para elegir. Se corren y se registran para la tabla y la
# defensa; si quieres que también elijan, usa --select-label.
STEPS = [
    ("1 etiqueta: theta y modo", False, [
        ("theta=1.3", {"label": {"theta": 1.3}}),
        ("theta=2.0", {"label": {"theta": 2.0}}),
        ("modo percentile", {"label": {"mode": "percentile"}}),
    ]),
    ("2 etiqueta: linea base", False, [
        ("method=bins", {"label": {"method": "bins"}}),
    ]),
    ("3 vocabulario por canales", True, [
        ("min_channels=3", {"features": {"min_channels": 3}}),
        ("min_channels=5", {"features": {"min_channels": 5}}),
        ("min_channels=8", {"features": {"min_channels": 8}}),
    ]),
    ("4 texto", True, [
        ("min_df=3", {"features": {"min_df": 3}}),
        ("min_df=10", {"features": {"min_df": 10}}),
        ("max_features=5000", {"features": {"max_features": 5000}}),
        ("char_ngrams", {"features": {"char_ngrams": True}}),
    ]),
    ("5 modelo", True, [
        ("C=0.1", {"model": {"C": 0.1}}),
        ("C=0.3", {"model": {"C": 0.3}}),
        ("C=3", {"model": {"C": 3}}),
        ("C=10", {"model": {"C": 10}}),
        ("class_weight=balanced", {"model": {"class_weight": "balanced"}}),
        ("penalty=l1", {"model": {"penalty": "l1"}}),
    ]),
    ("6 recencia", True, [
        ("vida media=7", {"weights": {"half_life_days": 7}}),
        ("vida media=14", {"weights": {"half_life_days": 14}}),
        ("vida media=45", {"weights": {"half_life_days": 45}}),
        ("vida media=60", {"weights": {"half_life_days": 60}}),
        ("sin peso", {"weights": {"half_life_days": None}}),
    ]),
]

EJEMPLOS = ["Probé 5 IAs gratis y esto pasó", "Vlog de mi semana", "El secreto que nadie te cuenta", "Resumen del capítulo"]


# ----------------------------------------------------------------------------- utilidades
def load_videos(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f"Al CSV le faltan columnas: {missing}. Genera el archivo con scripts.export_videos.")
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")
    if "language" not in df.columns:
        print("AVISO: el CSV no trae 'language'; no se filtra por idioma.")
    return df


def deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def cfg_diff(cfg: dict, ref: dict | None = None) -> dict:
    """Solo lo que cambia contra la configuración de fábrica (es el JSON parcial que acepta train_model --config)."""
    ref = DEFAULT_CFG if ref is None else ref
    out = {}
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(ref.get(k), dict):
            d = cfg_diff(v, ref[k])
            if d:
                out[k] = d
        elif ref.get(k) != v:
            out[k] = v
    return out


def shuffle_views_within_channel(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Rompe la relación título -> vistas SIN romper el nivel de cada canal (el nulo correcto para detectar fuga)."""
    rng = np.random.default_rng(seed)
    out = df.reset_index(drop=True).copy()
    col = out.columns.get_loc("views")
    views = out["views"].to_numpy().copy()
    for _, pos in out.groupby("channel_id").indices.items():
        views[pos] = rng.permutation(views[pos])
    out.iloc[:, col] = views
    return out


def semaforo(auc: float | None, lift: float | None) -> str:
    if auc is None:
        return "sin dato"
    if auc >= 0.60 and (lift or 0) >= 1.3:
        return "VERDE: congela la configuración y avanza"
    if auc >= 0.55:
        return "AMARILLO: aplica los respaldos 0 y 1 del plan (más canales, zona gris)"
    return "ROJO: revisa fuga y etiqueta antes de seguir"


class Runner:
    def __init__(self, df: pd.DataFrame, niche_ids, out_dir: Path):
        self.df, self.niche_ids, self.out_dir = df, niche_ids, out_dir
        self.rows: list[dict] = []
        out_dir.mkdir(parents=True, exist_ok=True)

    def cfg_for(self, override: dict) -> dict:
        base = {"data": {"niche_ids": self.niche_ids}} if self.niche_ids else {}
        return merge_cfg(deep_merge(base, override))

    def run(self, step: str, name: str, override: dict, df: pd.DataFrame | None = None, tag: str = "") -> dict:
        cfg = self.cfg_for(override)
        t0 = time.time()
        row = {"paso": step, "corrida": name + tag, "cambios": json.dumps(cfg_diff(cfg, merge_cfg(
            {"data": {"niche_ids": self.niche_ids}} if self.niche_ids else None)), ensure_ascii=False)}
        try:
            res = train(self.df if df is None else df, cfg)
            m = res.metrics
            row.update(status="ok", videos=res.n_videos, canales=res.n_channels, tasa_base=m["base_rate"],
                       auc=m["auc_mean"], auc_std=m["auc_std"], solo_texto=m["ablation"]["text_only"],
                       solo_formato=m["ablation"]["format_only"], pr_auc=m["pr_auc"],
                       auc_within=m["auc_within_channel"], auc_within_std=m["auc_within_std"],
                       p_at_10=m["precision_at_10"], lift_at_10=m["lift_at_10"], auc_temporal=m["temporal_auc"],
                       canales_prueba=m["n_test_channels"])
            row["_metrics"] = m
        except NotEnoughData as e:
            row.update(status=f"sin datos: {e}")
        row["segundos"] = round(time.time() - t0, 1)
        self.rows.append(row)
        pd.DataFrame([{k: v for k, v in r.items() if k != "_metrics"} for r in self.rows]).to_csv(
            self.out_dir / "runs_log.csv", index=False)
        if row["status"] == "ok":
            print(f"  {row['corrida']:<28} AUC {row['auc']:.3f} ± {row['auc_std']:.3f} (dentro de canal {row['auc_within']:.3f}) | texto {row['solo_texto']:.3f} "
                  f"formato {row['solo_formato']:.3f} | lift@10 {row['lift_at_10']:.2f} | base {row['tasa_base']:.2f} "
                  f"| {row['videos']} videos, {row['segundos']}s", flush=True)
        else:
            print(f"  {row['corrida']:<28} {row['status']}", flush=True)
        return row

    def fuga(self, override: dict, step: str, name: str, reps: int = 2) -> float | None:
        aucs = []
        for i in range(reps):
            r = self.run(step, name, override, df=shuffle_views_within_channel(self.df, seed=100 + i), tag=f" (barajado {i + 1})")
            if r["status"] == "ok":
                aucs.append(r["auc"])
        return float(np.mean(aucs)) if aucs else None


# ----------------------------------------------------------------------------- flujo
def channels_per_term(df: pd.DataFrame, cfg: dict, terms: list) -> dict:
    """En cuántos canales distintos aparece cada término (sobre los videos que entran al entrenamiento)."""
    from sklearn.feature_extraction.text import CountVectorizer

    from ml.dataset import build_dataset, select_training_rows
    from ml.text import STOPWORDS
    ds, _ = select_training_rows(build_dataset(df, cfg), cfg)
    if ds.empty or not terms:
        return {}
    cv = CountVectorizer(vocabulary=terms, lowercase=True, strip_accents="unicode", stop_words=STOPWORDS,
                         ngram_range=tuple(cfg["features"]["ngram_range"]), binary=True)
    M = cv.fit_transform(ds["title"].astype(str)).tocsc()
    codes = ds["channel_id"].to_numpy()
    return {t: int(len(set(codes[M[:, j].nonzero()[0]]))) for j, t in enumerate(terms)}


def quick(runner: Runner) -> None:
    print("\n== Corrida rápida con la configuración de fábrica")
    cfg = runner.cfg_for({})
    res = train(runner.df, cfg)
    m = res.metrics
    print(f"Videos usados: {res.n_videos} | canales: {res.n_channels} | y=1: {m['base_rate']:.1%} | "
          f"quitados por no tener línea base de su canal: {m['n_dropped_no_channel_baseline']}")
    print(f"AUC en canales no vistos: {m['auc_mean']:.3f} ± {m['auc_std']:.3f} (canales de prueba por semilla: {m['n_test_channels']})")
    print(f"AUC DENTRO de cada canal (elegir entre ideas del mismo canal): {m['auc_within_channel']:.3f} ± {m['auc_within_std']:.3f}")
    print(f"Ablación: solo texto {m['ablation']['text_only']:.3f} | solo formato {m['ablation']['format_only']:.3f} | ambos {m['ablation']['both']:.3f}")
    print(f"Precisión@10%: {m['precision_at_10']:.3f} | lift@10%: {m['lift_at_10']:.2f} | AUC temporal: {m['temporal_auc']}")
    print(f"Semáforo: {semaforo(m['auc_mean'], m['lift_at_10'])}")
    pos, neg = m["top_positive_terms"][:20], m["top_negative_terms"][:10]
    nch = channels_per_term(runner.df, cfg, [t for t, _ in pos + neg])
    print("Términos que más suben (peso, canales distintos donde aparece):")
    print("  " + ", ".join(f"{t} ({w:+.2f}, {nch.get(t, '?')} can.)" for t, w in pos[:10]))
    print("Términos que más bajan:")
    print("  " + ", ".join(f"{t} ({w:+.2f}, {nch.get(t, '?')} can.)" for t, w in neg))
    pocos = sum(1 for t, _ in pos if nch.get(t, 99) <= 2)
    print(f"De los {len(pos)} términos que más suben, {pocos} aparecen en 1 o 2 canales (no generalizan a canales nuevos).")
    model = load_model(res.artifact)
    nid = (cfg["data"]["niche_ids"] or [int(runner.df["niche_id"].mode()[0])])[0]
    print(f"\nPredicciones de ejemplo (nicho {nid}, 10 min, 6 pm, viernes):")
    for t in EJEMPLOS:
        p = predict(model, title=t, duration_s=600, publish_hour=18, publish_weekday=4, niche_id=nid)
        print(f"  {p.score:5.1f}/100  p={p.probability:.3f}  {t}")
    fuga = runner.fuga({}, "fuga", "fábrica")
    if fuga is not None:
        print(f"\nPrueba de fuga (vistas barajadas dentro de cada canal): AUC {fuga:.3f} "
              f"{'OK, cerca de 0.50' if fuga <= 0.56 else 'AVISO: demasiado alto, revisa fuga'}")


def search(runner: Runner, min_gain: float, seeds_final: int, select_label: bool = False, metric: str = "auc") -> None:
    print("\n== Corrida base (configuración de fábrica)")
    base = runner.run("0 base", "fábrica", {})
    if base["status"] != "ok":
        raise SystemExit("La corrida base no pudo entrenar. Corre primero scripts.diagnostico_dataset (¿alcanzan los videos?).")
    best_override, best = {}, base
    for step, selectable, candidates in STEPS:
        selectable = selectable or select_label
        print(f"\n== Paso {step}  " + (f"(se cambia solo si gana al menos {min_gain:.3f} de AUC)" if selectable else
              "(informativo: la etiqueta cambia, así que el AUC no es comparable y no se elige por él)"))
        winner = None
        for name, over in candidates:
            r = runner.run(step, name, deep_merge(best_override, over))
            if selectable and r["status"] == "ok" and r[metric] >= best[metric] + min_gain and (winner is None or r[metric] > winner[1][metric]):
                winner = (over, r)
        if winner:
            best_override, best = deep_merge(best_override, winner[0]), winner[1]
            print(f"  -> gana {best['corrida']} ({metric} {best[metric]:.3f})")
        elif selectable:
            print(f"  -> se queda como estaba ({metric} {best[metric]:.3f})")

    print(f"\n== Comparación final con semillas nuevas ({seeds_final}), para no premiar el azar de la selección")
    old_seeds = list(service.EVAL_SEEDS)
    service.EVAL_SEEDS = list(range(101, 101 + seeds_final))
    try:
        f0 = runner.run("final", "fábrica", {}, tag=" [semillas nuevas]")
        f1 = runner.run("final", "mejor", best_override, tag=" [semillas nuevas]")
    finally:
        service.EVAL_SEEDS = old_seeds
    use_best = f1["status"] == "ok" and f0["status"] == "ok" and f1[metric] >= f0[metric] + min_gain / 2
    final_override, final = (best_override, f1) if use_best else ({}, f0)
    print("  -> se recomienda la configuración", "elegida" if use_best else "de fábrica (la mejora no se sostuvo con semillas nuevas)")

    ids = runner.niche_ids or sorted(int(x) for x in runner.df["niche_id"].dropna().unique())
    if len(ids) > 1:
        print("\n== Informativo: cada nicho por separado con la configuración recomendada "
              "(pocos canales de prueba por nicho: mucho ruido, no se elige por esto)")
        for nid in ids:
            runner.run("por nicho", f"nicho {nid}", deep_merge(final_override, {"data": {"niche_ids": [nid]}}))

    print("\n== Prueba de fuga (etiquetas barajadas dentro de cada canal; esperado cerca de 0.50)")
    fuga = runner.fuga(final_override, "fuga", "recomendada")
    if fuga is not None and fuga > 0.56:
        print("  AVISO: AUC alto con etiquetas al azar. Hay fuga o muy pocos canales de prueba; no te fíes de los números.")

    cfg_json = cfg_diff(runner.cfg_for(final_override))
    (runner.out_dir / "best_config.json").write_text(json.dumps(cfg_json, indent=2, ensure_ascii=False), encoding="utf-8")
    log = pd.DataFrame([{k: v for k, v in r.items() if k != "_metrics"} for r in runner.rows])
    cols = ["paso", "corrida", "status", "videos", "canales", "tasa_base", "auc", "auc_std", "auc_within", "solo_texto", "solo_formato",
            "lift_at_10", "segundos"]
    tabla = log[[c for c in cols if c in log.columns]].round(3).to_string(index=False)
    lineas = ["# Resumen de experimentos", "", "```", tabla, "```", "",
              f"Configuración recomendada (best_config.json): `{json.dumps(cfg_json, ensure_ascii=False)}`",
              f"AUC con semillas nuevas: {final['auc']:.3f} ± {final['auc_std']:.3f}" if final["status"] == "ok" else "",
              f"AUC con etiquetas barajadas: {fuga:.3f}" if fuga is not None else "",
              f"Semáforo: {semaforo(final.get('auc'), final.get('lift_at_10'))}"]
    (runner.out_dir / "resumen.md").write_text("\n".join(lineas), encoding="utf-8")

    print("\n" + tabla)
    print(f"\nConfiguración recomendada: {json.dumps(cfg_json, ensure_ascii=False)}")
    print(f"Semáforo: {semaforo(final.get('auc'), final.get('lift_at_10'))}")
    print(f"\nArchivos en {runner.out_dir}/: runs_log.csv, best_config.json, resumen.md")
    print("Para entrenar y activar el modelo con esa configuración (desde backend/):")
    print(f"  python -m scripts.train_model --config {runner.out_dir / 'best_config.json'} --activate")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="../export/videos.csv", help="CSV de scripts.export_videos")
    ap.add_argument("--niche-ids", default=None, help="ids de nichos separados por coma, por ejemplo 1,3,4 (por defecto, todos)")
    ap.add_argument("--seeds", type=int, default=5, help="semillas de evaluación por corrida (5 es lo del plan; 10 es más estable)")
    ap.add_argument("--min-gain", type=float, default=0.01, help="mejora mínima de AUC para cambiar un valor (evita premiar el ruido)")
    ap.add_argument("--select-label", action="store_true",
                    help="deja que theta, percentile y bins también se elijan por AUC (no recomendado: no son comparables)")
    ap.add_argument("--metric", choices=["auc", "auc_within"], default="auc",
                    help="métrica con la que se elige: auc (global, canales no vistos) o auc_within (promedio dentro de cada canal)")
    ap.add_argument("--out-dir", default="experiments")
    ap.add_argument("--quick", action="store_true", help="solo una corrida con la configuración de fábrica y la prueba de fuga")
    args = ap.parse_args()

    df = load_videos(args.csv)
    niche_ids = [int(x) for x in args.niche_ids.split(",")] if args.niche_ids else None
    service.EVAL_SEEDS = list(range(1, args.seeds + 1))
    print(f"CSV: {len(df)} filas, {df['channel_id'].nunique()} canales | nichos: {niche_ids or 'todos'} | "
          f"semillas de evaluación: {args.seeds}")
    runner = Runner(df, niche_ids, Path(args.out_dir))
    if args.quick:
        quick(runner)
    else:
        search(runner, args.min_gain, seeds_final=max(args.seeds, 10), select_label=args.select_label, metric=args.metric)


if __name__ == "__main__":
    main()