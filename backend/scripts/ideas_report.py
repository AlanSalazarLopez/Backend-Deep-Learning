"""Ideas que rinden por tema (hot y atemporales), desde el CSV. Sin BD y sin cuota.

Uso (desde backend/):
  python -m scripts.ideas_report --csv ..\\export\\videos.csv --niche-ids 1,3,4,5
  python -m scripts.ideas_report --csv ..\\export\\videos.csv --niche-ids 4 --distance 0.8 --examples 3

Un tema es "robusto" solo si supera lo que produce el azar (calibración barajando dentro de cada canal).
Escribe experiments/ideas.json.
"""
import argparse
import json
from pathlib import Path

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows
from ml.ideas import IdeasParams, compute_niche_ideas
from scripts.run_experiments import load_videos


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="../export/videos.csv")
    ap.add_argument("--niche-ids", default=None)
    ap.add_argument("--distance", type=float, default=0.92, help="más bajo = temas más estrictos (más chicos)")
    ap.add_argument("--min-channels", type=int, default=3)
    ap.add_argument("--examples", type=int, default=2, help="videos de ejemplo a mostrar por tema")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--out-dir", default="experiments")
    args = ap.parse_args()

    ids = [int(x) for x in args.niche_ids.split(",")] if args.niche_ids else None
    cfg = merge_cfg({"data": {"niche_ids": ids}} if ids else None)
    ds, _ = select_training_rows(build_dataset(load_videos(args.csv), cfg), cfg)
    p = IdeasParams(distance=args.distance, min_channels=args.min_channels, n_examples=max(1, args.examples))
    todo = {}
    for nid, g in ds.groupby("niche_id"):
        r = compute_niche_ideas(g, p)
        todo[int(nid)] = r
        print(f"\n=== nicho {nid}: {r['videos']} videos, {r['canales']} canales -> {r['estado']}")
        if r["estado"] != "ok":
            print(f"  {r['motivo']}")
            continue
        c = r["calibracion"]
        print(f"  temas evaluados: {c['temas_evaluados']}")
        for clase in ("hot", "evergreen"):
            cc = c[clase]
            print(f"  {clase.upper():<9} reales {cc['reales']} | azar {cc['azar_media']} (p95 {cc['azar_p95']:.0f}) | "
                  f"robustos {cc['robustos']} -> señal {cc['senal']}")
            for t in r[clase][: args.top]:
                marca = "*" if t["robusto"] else " "
                ant = "-" if t["lift_antiguo"] is None else f"{t['lift_antiguo']:.2f}"
                print(f"   {marca} {t['tema']:<42} lift {ant} -> {t['lift_reciente']:.2f} (mín {t['lift_minimo']:.2f}) "
                      f"| {t['videos']} videos, {t['canales']} canales, máx {t['max_share_un_canal']:.0%} de un canal")
                for e in t["ejemplos"][: args.examples]:
                    print(f"        x{e['ratio']:<5} {e['titulo'][:80]}")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ideas.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\nArchivo: {out / 'ideas.json'}   (* = tema robusto frente al azar)")


if __name__ == "__main__":
    main()