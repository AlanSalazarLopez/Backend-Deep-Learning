"""Corrida semanal: (1) guarda un snapshot de vistas de los videos recientes y (2) recalcula las ideas por nicho.

Uso (desde backend/):
  python -m scripts.ingest --refresh        # ANTES, una vez por semana: trae los videos nuevos de los canales semilla
  python -m scripts.weekly                  # snapshots + ideas
  python -m scripts.weekly --no-snapshots   # solo recalcula ideas (no gasta cuota)
  python -m scripts.weekly --no-ideas       # solo snapshots

Costo de cuota: 1 unidad por cada 50 videos (videos.list). ~5,000 videos recientes = ~100 unidades.
Además de insertar el snapshot, actualiza videos.views y videos.fetched_at con la lectura nueva, para que la edad
(que se mide contra fetched_at) siga siendo coherente con las vistas.
"""
import argparse
from datetime import datetime, timezone

from scripts._common import connect
from services import ideas_service
from services.youtube_client import YouTubeClient, YouTubeError, YouTubeQuotaError


def _views(item: dict) -> int | None:
    try:
        return int((item.get("statistics") or {})["viewCount"])
    except (KeyError, TypeError, ValueError):
        return None


def take_snapshots(conn, yt: YouTubeClient, max_age_days: int) -> tuple[int, int]:
    rows = conn.execute(
        "SELECT id, yt_video_id FROM videos WHERE published_at > now() - make_interval(days => %s) ORDER BY id",
        (max_age_days,)).fetchall()
    taken_at = datetime.now(timezone.utc)
    ok = missing = 0
    try:
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            by_yt = {r["yt_video_id"]: r["id"] for r in batch}
            data = yt._get("videos", {"part": "statistics", "id": ",".join(by_yt)})
            snaps, upds = [], []
            for it in data.get("items", []):
                vid, views = by_yt.get(it.get("id")), _views(it)
                if vid is None or views is None:
                    continue
                snaps.append((vid, taken_at, views))
                upds.append((views, taken_at, vid))
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO video_snapshots (video_id, taken_at, views) VALUES (%s, %s, %s) "
                                "ON CONFLICT DO NOTHING", snaps)
                cur.executemany("UPDATE videos SET views = %s, fetched_at = %s WHERE id = %s", upds)
            conn.commit()
            ok += len(snaps)
            missing += len(batch) - len(snaps)   # borrados, privados o sin vistas públicas
    except YouTubeQuotaError as e:
        conn.commit()
        print(f"{e}. Lo ya guardado se conserva; vuelve a correr mañana.")
    except YouTubeError as e:
        conn.commit()
        print(f"Error de YouTube: {e}. Lo ya guardado se conserva.")
    return ok, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-snapshots", action="store_true")
    ap.add_argument("--no-ideas", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=200, help="solo videos publicados en los últimos N días")
    args = ap.parse_args()
    with connect() as conn:
        if not args.no_snapshots:
            ok, missing = take_snapshots(conn, YouTubeClient(), args.max_age_days)
            print(f"Snapshots: {ok} videos guardados, {missing} sin lectura (borrados o privados).")
        if not args.no_ideas:
            res = ideas_service.compute_and_store(conn)
            if not res:
                print("No hay datos para calcular ideas.")
            for nid, r in sorted(res.items()):
                if r["estado"] != "ok":
                    print(f"  nicho {nid}: {r['estado']} ({r['motivo']})")
                    continue
                c = r["calibracion"]
                print(f"  nicho {nid}: hot {len(r['hot'])} (señal {c['hot']['senal']}, {c['hot']['robustos']} robustos) | "
                      f"atemporales {len(r['evergreen'])} (señal {c['evergreen']['senal']}, "
                      f"{c['evergreen']['robustos']} robustos)")


if __name__ == "__main__":
    main()