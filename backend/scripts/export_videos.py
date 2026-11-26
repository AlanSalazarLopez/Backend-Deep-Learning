"""Exporta los videos y su canal a un CSV para trabajar con el modelo sin acceso a la BD ni a sus credenciales.

Uso (desde backend/):
  python -m scripts.export_videos                   # escribe ../export/videos.csv (solo canales semilla)
  python -m scripts.export_videos --include-clients # incluye también los canales de clientes
  python -m scripts.export_videos --out otro.csv

Las columnas son las de entrada de ml.dataset.build_dataset (docs/C3_ml.md, sección 1). Para cargarlo:
  pd.read_csv("videos.csv", parse_dates=["published_at", "fetched_at"])
No incluye usuarios, contraseñas ni nada del archivo .env.
"""
import argparse
from pathlib import Path

import pandas as pd

from config import ROOT
from scripts._common import connect

QUERY = """
SELECT v.channel_id, c.niche_id, c.language, v.yt_video_id, v.title, v.published_at, v.duration_s,
       v.views, v.yt_category_id, v.is_short, v.fetched_at
FROM videos v JOIN channels c ON c.id = v.channel_id
WHERE c.niche_id IS NOT NULL {extra}
ORDER BY v.channel_id, v.published_at
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "export" / "videos.csv"))
    ap.add_argument("--include-clients", action="store_true", help="incluye los canales de clientes (por defecto, solo semilla)")
    args = ap.parse_args()
    extra = "" if args.include_clients else "AND c.source = 'seed'"
    with connect() as conn:
        rows = conn.execute(QUERY.format(extra=extra)).fetchall()
    if not rows:
        raise SystemExit("No hay videos para exportar. Corre primero scripts.ingest.")
    df = pd.DataFrame(rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"{len(df)} videos de {df['channel_id'].nunique()} canales -> {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()