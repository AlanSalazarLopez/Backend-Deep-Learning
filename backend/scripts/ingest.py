"""Carga canales semilla y sus videos desde la API de YouTube (docs/C3_ml.md, sección 7).

Uso (desde backend/):
  python -m scripts.ingest                       # lee ../data/channels_seed.csv
  python -m scripts.ingest --limit 5             # prueba con 5 canales
  python -m scripts.ingest --refresh             # vuelve a leer las vistas de los canales semilla ya guardados
Costo: unas 5 unidades de cuota por canal (nunca usa search.list): channels.list (1) + 2 páginas de playlistItems
con hasta 100 videos largos (2) + 2 lotes de videos.list (2). Se leen del playlist de videos largos (sin Shorts)
y, si ese no existe para el canal, del playlist normal de subidas (+1).
Un canal se descarta si, dentro de la ventana de edad del modelo (por defecto de 3 a 180 días), tiene menos
de 15 videos válidos con duración dentro del rango del modelo (por defecto de 3 min a 2 h). Ver ml/config.py.
Al terminar escribe data/ingest_report.csv con el resultado de CADA canal (guardado, descartado y por qué):
sirve para revisar qué tipo de canales se están quedando fuera (posible sesgo de selección).
"""
import argparse
import csv
from pathlib import Path

from config import ROOT
from ml.config import merge_cfg
from ml.dataset import DEFAULT_MAX_DURATION_S, DEFAULT_MIN_DURATION_S
from scripts._common import connect
from services import ingest_service
from services.youtube_client import YouTubeClient, YouTubeError, YouTubeQuotaError

MIN_VALID_VIDEOS = 15
MIN_CATEGORY_SHARE = 0.5
SEED_MAX_VIDEOS = 100   # videos recientes (largos) por canal semilla; los clientes siguen usando 50
REPORT_FIELDS = ["handle", "niche_slug", "estado", "motivo", "videos_validos", "idioma"]


def check_channel(conn, channel_id: int, niche_id: int, language: str | None, want_lang: str,
                  min_dur: int, max_dur: int, min_age: float, max_age: float) -> tuple[str | None, int | None]:
    """Devuelve (motivo_de_descarte o None, videos_validos). videos_validos es None si ya falló por idioma."""
    if language != want_lang:
        return f"idioma {language or 'indeterminado'}", None
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM videos WHERE channel_id = %s AND views >= 0 "
        "AND duration_s BETWEEN %s AND %s "
        "AND EXTRACT(EPOCH FROM (fetched_at - published_at)) / 86400 BETWEEN %s AND %s",
        (channel_id, min_dur, max_dur, min_age, max_age)).fetchone()["n"]
    if n < MIN_VALID_VIDEOS:
        return (f"solo {n} videos válidos (de {min_dur // 60} a {max_dur // 60} min) "
                f"en la ventana de {min_age:g} a {max_age:g} días"), n
    share = conn.execute(
        "SELECT AVG((v.yt_category_id = n.yt_category_id)::int)::float AS s FROM videos v, niches n "
        "WHERE v.channel_id = %s AND n.id = %s AND v.duration_s BETWEEN %s AND %s",
        (channel_id, niche_id, min_dur, max_dur)).fetchone()["s"]
    if share is not None and share < MIN_CATEGORY_SHARE:
        return f"solo {share:.0%} de sus videos tienen la categoría del nicho", n
    return None, n


def write_report(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(ROOT / "data" / "channels_seed.csv"))
    ap.add_argument("--report", default=None, help="por defecto, ingest_report.csv junto al CSV de entrada")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--keep-weak", action="store_true", help="no borra los canales semilla que no cumplen los filtros")
    ap.add_argument("--max-videos", type=int, default=SEED_MAX_VIDEOS,
                    help=f"videos recientes por canal (por defecto {SEED_MAX_VIDEOS}; cada 50 cuestan 2 unidades)")
    args = ap.parse_args()
    report_path = Path(args.report) if args.report else Path(args.csv).with_name("ingest_report.csv")

    yt = YouTubeClient()
    cfg = merge_cfg()
    data_cfg, label_cfg = cfg["data"], cfg["label"]
    want_lang = data_cfg["language"]
    min_dur = data_cfg.get("min_duration_s", DEFAULT_MIN_DURATION_S)
    max_dur = data_cfg.get("max_duration_s", DEFAULT_MAX_DURATION_S)
    min_age, max_age = label_cfg["min_age_days"], label_cfg["max_age_days"]
    report: list[dict] = []
    with connect() as conn:
        niches = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM niches").fetchall()}
        slug_of = {v: k for k, v in niches.items()}
        if args.refresh:
            work = [(r["handle"], r["niche_id"]) for r in conn.execute(
                "SELECT handle, niche_id FROM channels WHERE source = 'seed' AND niche_id IS NOT NULL").fetchall()]
        else:
            path = Path(args.csv)
            if not path.exists():
                raise SystemExit(f"No existe {path}. Genera la lista con backend/scripts/discover_channels.py.")
            with open(path, encoding="utf-8") as f:
                work = []
                for r in csv.DictReader(f):
                    if r["niche_slug"] not in niches:
                        print(f"[omitido] {r['handle']}: nicho desconocido '{r['niche_slug']}'")
                        continue
                    work.append((r["handle"], niches[r["niche_slug"]]))
        if args.limit:
            work = work[: args.limit]

        ok = dropped = failed = 0
        try:
            for i, (handle, niche_id) in enumerate(work, 1):
                row = {"handle": handle, "niche_slug": slug_of.get(niche_id, ""), "estado": "", "motivo": "",
                       "videos_validos": "", "idioma": ""}
                try:
                    info, videos = ingest_service.fetch_from_youtube(yt, handle, max_videos=args.max_videos)
                    res = ingest_service.save_channel(conn, info, videos, user_id=None, source="seed", niche_id=niche_id)
                    conn.commit()
                except ingest_service.ChannelNotFound:
                    print(f"[{i}/{len(work)}] {handle}: no existe"); failed += 1
                    report.append({**row, "estado": "error", "motivo": "no existe"}); continue
                except ingest_service.ChannelTaken:
                    conn.rollback(); print(f"[{i}/{len(work)}] {handle}: ya es de un cliente")
                    report.append({**row, "estado": "omitido", "motivo": "ya es de un cliente"}); continue
                except YouTubeQuotaError as e:
                    conn.rollback(); print(f"\n{e}. Vuelve a correr mañana; lo ya guardado se conserva."); break
                except YouTubeError as e:
                    conn.rollback(); print(f"[{i}/{len(work)}] {handle}: {e}"); failed += 1
                    report.append({**row, "estado": "error", "motivo": str(e)[:200]}); continue
                reason, n_valid = (None, None) if args.keep_weak else check_channel(
                    conn, res.channel["id"], niche_id, res.language, want_lang, min_dur, max_dur, min_age, max_age)
                row.update({"videos_validos": "" if n_valid is None else n_valid, "idioma": res.language or ""})
                if reason and res.channel["source"] == "seed":
                    conn.execute("DELETE FROM channels WHERE id = %s", (res.channel["id"],))
                    conn.commit()
                    dropped += 1
                    print(f"[{i}/{len(work)}] {handle}: descartado ({reason})")
                    report.append({**row, "estado": "descartado", "motivo": reason})
                else:
                    ok += 1
                    print(f"[{i}/{len(work)}] {handle}: {len(videos)} videos, idioma {res.language}")
                    report.append({**row, "estado": "guardado"})
        finally:
            write_report(report_path, report)   # también si se corta por cuota o con Ctrl+C
        print(f"\nListo: {ok} canales guardados, {dropped} descartados, {failed} con error.")
        print(f"Reporte por canal: {report_path}")


if __name__ == "__main__":
    main()