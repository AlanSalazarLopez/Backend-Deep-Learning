"""Crea las tablas (docs/C1_esquema_bd.sql). Es idempotente.

Uso (desde backend/):
  python -m scripts.init_db
  python -m scripts.init_db --reset      # BORRA las tablas del proyecto y las vuelve a crear
"""
import argparse

from scripts._common import SCHEMA_FILE, connect

TABLES = ["quota_log", "channel_candidates", "niche_ideas", "video_snapshots", "predictions", "model_runs", "videos", "channels", "niches", "users"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        if args.reset:
            if input("Esto BORRA todos los datos del proyecto. Escribe BORRAR para continuar: ") != "BORRAR":
                raise SystemExit("Cancelado.")
            conn.execute("DROP TABLE IF EXISTS " + ", ".join(TABLES) + " CASCADE")
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    print("Tablas listas.")


if __name__ == "__main__":
    main()