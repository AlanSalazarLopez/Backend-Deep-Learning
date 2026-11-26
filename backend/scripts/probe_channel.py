"""Diagnóstico de canales contra la API de YouTube. NO usa ni escribe en la base de datos.

Uso (desde backend/):
  python -m scripts.probe_channel @azaelrock0 @l0k0hgaming
  python -m scripts.probe_channel @darkplayertv --max-videos 100

Por canal compara el playlist de videos largos (UULF) contra el playlist normal de subidas (UU) y dice cuántos
videos trae cada uno y cuántos son válidos para el modelo (duración y edad de ml/config.py). Así se ve si el
cambio de la ingesta funciona o si el canal simplemente publica poco video largo.
Costo: unas 9 unidades de cuota por canal.
"""
import argparse
from datetime import datetime, timezone

from ml.config import merge_cfg
from services.youtube_client import YouTubeClient, YouTubeError, YouTubeQuotaError, long_form_playlist_id


def resumen(vids, lo, hi, amin, amax, now) -> dict:
    edades = [(now - v.published_at).total_seconds() / 86400 for v in vids]
    en_dur = [lo <= v.duration_s <= hi for v in vids]
    en_edad = [amin <= e <= amax for e in edades]
    return {
        "traidos": len(vids),
        "cortos(<min)": sum(v.duration_s < lo for v in vids),
        "largos(>max)": sum(v.duration_s > hi for v in vids),
        "en_ventana_de_edad": sum(en_edad),
        "validos": sum(a and b for a, b in zip(en_dur, en_edad)),
        "mas_viejo_d": round(max(edades)) if edades else None,
        "mas_nuevo_d": round(min(edades), 1) if edades else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handles", nargs="+")
    ap.add_argument("--max-videos", type=int, default=100)
    args = ap.parse_args()

    cfg = merge_cfg()
    lo, hi = cfg["data"]["min_duration_s"], cfg["data"]["max_duration_s"]
    amin, amax = cfg["label"]["min_age_days"], cfg["label"]["max_age_days"]
    now = datetime.now(timezone.utc)
    yt = YouTubeClient()
    print(f"Válido = duración de {lo} a {hi} s y edad de {amin} a {amax} días. Mínimo para quedarse: 15.\n")
    try:
        for h in args.handles:
            info = yt.resolve_channel(h)
            if info is None:
                print(f"{h}: no existe\n")
                continue
            print(f"{h} ({info.title})")
            lf = long_form_playlist_id(info.uploads_playlist_id)
            try:
                ids = yt._playlist_video_ids(lf, args.max_videos) if lf else []
                nuevo = resumen(yt._video_details(ids), lo, hi, amin, amax, now)
            except YouTubeQuotaError:
                raise
            except YouTubeError as e:
                nuevo = f"el playlist UULF falló: {e}"
            viejo = resumen(yt.recent_videos(info.uploads_playlist_id, args.max_videos, long_form_only=False),
                            lo, hi, amin, amax, now)
            print(f"  UULF (videos largos): {nuevo}")
            print(f"  UU   (todas las subidas): {viejo}\n")
    except YouTubeQuotaError as e:
        print(f"\n{e}. Vuelve a probar mañana.")


if __name__ == "__main__":
    main()