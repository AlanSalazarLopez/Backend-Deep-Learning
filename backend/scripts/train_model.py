"""Entrena el modelo con los videos de la BD (canales semilla y de clientes) y lo guarda en model_runs.

Uso (desde backend/):
  python -m scripts.train_model                   # entrena con la configuración por defecto y lo activa
  python -m scripts.train_model --config cfg.json # configuración parcial en JSON (se mezcla con la de por defecto)
  python -m scripts.train_model --no-activate     # guarda el modelo sin activarlo
"""
import argparse
import json

from ml.service import NotEnoughData
from scripts._common import connect
from services.training import train_from_db


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--no-activate", action="store_true")
    args = ap.parse_args()
    cfg = json.load(open(args.config, encoding="utf-8")) if args.config else None
    with connect() as conn:
        try:
            run_id, res = train_from_db(conn, cfg, activate=not args.no_activate)
        except NotEnoughData as e:
            raise SystemExit(f"No se pudo entrenar: {e}")
        row = conn.execute("SELECT metrics->'fuentes' AS f FROM model_runs WHERE id = %s", (run_id,)).fetchone()
        fuentes = row["f"] if row else None
    m = res.metrics
    print(f"Modelo #{run_id} {'(guardado, no activo)' if args.no_activate else 'activo'}: "
          f"{res.n_videos} videos, {res.n_channels} canales")
    if fuentes:
        print(f"  Datos cargados: {fuentes['canales_semilla']} canales semilla ({fuentes['videos_semilla']} videos) + "
              f"{fuentes['canales_clientes']} canales de clientes ({fuentes['videos_clientes']} videos)")
    print(f"  AUC en canales no vistos: {m['auc_mean']:.3f} ± {m['auc_std']:.3f}  (azar = 0.50)")
    print(f"  Precisión en el 10 % superior: {m['precision_at_10']:.3f}  |  lift: {m['lift_at_10']:.2f}  |  tasa base: {m['base_rate']:.3f}")
    print(f"  Ablación (AUC): {json.dumps({k: round(v, 3) if v else v for k, v in m['ablation'].items()})}")
    if m.get("temporal_auc") is not None:
        print(f"  AUC temporal (entrena con videos viejos, prueba con recientes): {m['temporal_auc']:.3f}")
    print("  Términos que más suben:", ", ".join(t for t, _ in m["top_positive_terms"][:8]))
    print("  Términos que más bajan:", ", ".join(t for t, _ in m["top_negative_terms"][:8]))


if __name__ == "__main__":
    main()