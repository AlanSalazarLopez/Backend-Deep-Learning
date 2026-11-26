#!/usr/bin/env python3
"""T1a - Descubre canales semilla con la API de YouTube y genera data/channels_seed.csv.

Cómo busca (modo por defecto, "videos"):
  1. Por cada nicho busca VIDEOS recientes (últimos 45 días) dentro de la categoría de YouTube del nicho
     (Gaming, Música, Educación...), en español, ordenados por vistas y por fecha. Así los canales que salen
     son activos, del nicho correcto y de tamaños variados (search.list, 100 unidades por búsqueda).
  2. Pide los datos de esos canales (channels.list, 1 unidad por cada 50).
  3. Descarta canales sin @handle, con suscriptores ocultos, muy chicos o con pocos videos, de países que no son
     hispanohablantes o cuyos videos encontrados están en otro idioma (e imprime cuántos descartó por cada motivo).
  4. Elige los de cada nicho mezclando tamaños (chicos, medianos y grandes) y escribe un CSV para revisarlo.

El filtro fino (idioma de los títulos, categoría de los videos del canal, mínimo de videos válidos) se hace
después, en la ingesta (docs/C3_ml.md, sección 7).

Uso (desde la raíz del proyecto, con el entorno virtual activo):
  python backend/scripts/discover_channels.py --dry-run
  python backend/scripts/discover_channels.py --niches gaming --queries-per-niche 1   # prueba: 200 unidades
  python backend/scripts/discover_channels.py                                         # completo: ~3,200 unidades

La clave se lee de YOUTUBE_API_KEY (archivo .env de la raíz). El CSV queda en data/channels_seed.csv.
Las búsquedas se guardan en data/.cache_discover/: repetir la misma corrida el mismo día no gasta cuota.
Para filtrar por idioma NO cuesta unidades extra: usa los títulos de los videos que ya devolvió la búsqueda.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:  # carga el .env de la raíz del proyecto (backend/scripts/ -> raíz)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
API = "https://www.googleapis.com/youtube/v3"
SEARCH_COST = 100
CHANNELS_COST = 1

# Palabras de búsqueda por nicho (en español). Edítalas: se usan las primeras N (--queries-per-niche).
NICHE_QUERIES = {
    "gaming": ["gameplay en español", "videojuegos en español", "jugando minecraft en español", "reseña de videojuegos", "juegos retro en español"],
    "musica": ["producción musical en español", "tutorial de guitarra en español", "cover en español", "análisis de canciones", "cómo hacer beats"],
    "educacion": ["clases de matemáticas", "historia explicada en español", "aprende inglés desde cero", "física explicada fácil", "cultura general"],
    "ciencia-tech": ["reseña de tecnología en español", "inteligencia artificial en español", "programación para principiantes", "divulgación científica", "reseña de celulares"],
    "howto-estilo": ["tutorial de manualidades", "tutorial de maquillaje en español", "recetas fáciles", "bricolaje y hogar", "moda y estilo en español"],
    "entretenimiento": ["reacciones en español", "retos y desafíos en español", "reseña de series en español", "podcast en español", "curiosidades en español"],
    "deportes": ["análisis de fútbol en español", "rutina de gimnasio en español", "NBA en español", "entrenamiento en casa", "ciclismo en español"],
    "gente-blogs": ["vlog diario en español", "storytime en español", "vlog de viaje en español", "mi rutina diaria", "vida en México"],
}
# Categoría de YouTube de cada nicho (igual que niches.yt_category_id en docs/C1_esquema_bd.sql).
NICHE_CATEGORY = {
    "gaming": 20, "musica": 10, "educacion": 27, "ciencia-tech": 28,
    "howto-estilo": 26, "entretenimiento": 24, "deportes": 17, "gente-blogs": 22,
}

# Países de habla hispana. Un canal con país declarado fuera de esta lista se descarta (si no declara país, se conserva).
SPANISH_COUNTRIES = "ES,MX,AR,CO,CL,PE,VE,EC,UY,PY,BO,CR,PA,DO,GT,HN,SV,NI,CU,PR,GQ"
DEFAULT_REGIONS = ["MX", "ES", "AR", "CO", "CL"]  # cada búsqueda usa una región distinta, por turnos
PICK_PATTERN = ["small", "mid", "large", "small", "mid"]  # sesgo a chicos y medianos


class QuotaError(Exception):
    pass


class Budget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0

    def spend(self, units):
        if self.used + units > self.limit:
            raise QuotaError(f"Se alcanzó el presupuesto de {self.limit} unidades (usadas: {self.used}).")
        self.used += units


def api_get(endpoint, params, key):
    r = requests.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
    if r.status_code == 403:
        try:
            reason = r.json()["error"]["errors"][0]["reason"]
        except Exception:
            reason = "forbidden"
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise QuotaError(f"YouTube respondió {reason}: se acabó la cuota del día.")
        raise SystemExit(f"YouTube respondió 403 ({reason}). Revisa que la API Key sea válida y que YouTube Data API v3 esté habilitada.")
    if not r.ok:
        raise SystemExit(f"YouTube respondió {r.status_code} en {endpoint}: {r.text[:300]}")
    return r.json()


def search_channels(params, key, budget, cache_dir):
    """Una búsqueda (100 unidades). Devuelve [{channel_id, title}] (título del video o canal encontrado); va a caché."""
    cache_file = cache_dir / (hashlib.md5(("v2" + json.dumps(params, sort_keys=True)).encode()).hexdigest() + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    budget.spend(SEARCH_COST)
    data = api_get("search", {"part": "snippet", "maxResults": 50, **params}, key)
    found = []
    for it in data.get("items", []):
        sn = it.get("snippet") or {}
        cid = sn.get("channelId") or (it.get("id") or {}).get("channelId")
        if cid:
            found.append({"channel_id": cid, "title": sn.get("title", "")})
    cache_file.write_text(json.dumps(found), encoding="utf-8")
    return found


def fetch_channels(ids, key, budget):
    out, drops = {}, Counter()
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        budget.spend(CHANNELS_COST)
        data = api_get("channels", {"part": "snippet,statistics", "id": ",".join(batch), "maxResults": 50}, key)
        items = data.get("items", [])
        drops["la API no devolvió datos del canal"] += len(batch) - len(items)
        for it in items:
            st, sn = it.get("statistics", {}), it.get("snippet", {})
            handle = sn.get("customUrl") or ""
            if st.get("hiddenSubscriberCount"):
                drops["suscriptores ocultos"] += 1
                continue
            if not handle.startswith("@"):
                drops["sin @handle utilizable"] += 1
                continue
            out[it["id"]] = {
                "channel_id": it["id"],
                "handle": handle,
                "title": sn.get("title", ""),
                "description": sn.get("description", ""),
                "country": sn.get("country", ""),
                "subscribers": int(st.get("subscriberCount", 0)),
                "video_count": int(st.get("videoCount", 0)),
            }
    return out, drops


try:
    from langdetect import DetectorFactory, detect_langs
    DetectorFactory.seed = 0
except ImportError:  # opcional (pero recomendado: pip install langdetect)
    detect_langs = None


def other_language(titles):
    """Devuelve el código del idioma (ej. 'en', 'hi') si los títulos claramente NO están en español; si no, None.
    Solo descarta con evidencia clara, para no perder canales en español con anglicismos."""
    text = ". ".join(t for t in titles if t)
    if detect_langs is None or len(text) < 25:
        return None
    try:
        langs = detect_langs(text)
    except Exception:
        return None
    p_es = sum(l.prob for l in langs if l.lang == "es")
    return langs[0].lang if p_es < 0.15 and langs[0].prob >= 0.7 else None


def size_bin(subs):
    if subs < 20_000:
        return "small"
    if subs < 200_000:
        return "mid"
    return "large"


def balanced_pick(cands, n):
    bins = {b: sorted([c for c in cands if c["size_bin"] == b], key=lambda c: (-c["hits"], -c["subscribers"]))
            for b in ("small", "mid", "large")}
    idx = {b: 0 for b in bins}
    picked, progress = [], True
    while len(picked) < n and progress:
        progress = False
        for b in PICK_PATTERN:
            if len(picked) >= n:
                break
            if idx[b] < len(bins[b]):
                picked.append(bins[b][idx[b]])
                idx[b] += 1
                progress = True
    return picked


def build_plan(niches, queries_per_niche, mode, orders, regions, window_days):
    """Lista de búsquedas (parámetros de search.list) con el nicho al que pertenecen."""
    after = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00Z")
    plan, turn = [], 0
    for niche in niches:
        for q in NICHE_QUERIES[niche][:queries_per_niche]:
            for order in (orders if mode == "videos" else [None]):
                region = regions[turn % len(regions)]
                turn += 1
                if mode == "videos":
                    params = {"type": "video", "q": q, "videoCategoryId": str(NICHE_CATEGORY[niche]),
                              "order": order, "publishedAfter": after,
                              "relevanceLanguage": "es", "regionCode": region}
                else:
                    params = {"type": "channel", "q": q, "relevanceLanguage": "es", "regionCode": region}
                plan.append((niche, q, order, region, params))
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["videos", "channels"], default="videos",
                    help="videos: busca videos recientes por categoría (recomendado); channels: busca por nombre de canal")
    ap.add_argument("--queries-per-niche", type=int, default=2)
    ap.add_argument("--orders", default="viewCount,date", help="solo modo videos; cada orden es una búsqueda más")
    ap.add_argument("--window-days", type=int, default=45, help="solo modo videos: antigüedad máxima de los videos")
    ap.add_argument("--per-niche", type=int, default=45, help="candidatos a conservar por nicho (la ingesta descarta los que no sirven)")
    ap.add_argument("--budget", type=int, default=4000, help="tope de unidades de cuota a gastar")
    ap.add_argument("--min-subs", type=int, default=1000)
    ap.add_argument("--min-videos", type=int, default=30)
    ap.add_argument("--regions", default=",".join(DEFAULT_REGIONS))
    ap.add_argument("--niches", default="", help="lista separada por comas; por defecto, todos")
    ap.add_argument("--countries", default=SPANISH_COUNTRIES,
                    help="países permitidos (códigos separados por coma); ANY desactiva este filtro")
    ap.add_argument("--no-lang-filter", action="store_true", help="no descarta canales por el idioma de sus títulos")
    ap.add_argument("--out", default=str(DATA_DIR / "channels_seed.csv"))
    ap.add_argument("--cache-dir", default=str(DATA_DIR / ".cache_discover"))
    ap.add_argument("--dry-run", action="store_true", help="solo muestra cuántas unidades se gastarían")
    args = ap.parse_args()

    niches = [n for n in (args.niches.split(",") if args.niches else NICHE_QUERIES) if n]
    unknown = [n for n in niches if n not in NICHE_QUERIES]
    if unknown:
        sys.exit(f"Nichos desconocidos: {unknown}. Disponibles: {list(NICHE_QUERIES)}")
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    orders = [o.strip() for o in args.orders.split(",") if o.strip()]
    plan = build_plan(niches, args.queries_per_niche, args.mode, orders, regions, args.window_days)
    print(f"Plan: {len(plan)} búsquedas = {len(plan) * SEARCH_COST} unidades (+ ~1 por cada 50 canales). Modo: {args.mode}.")
    if args.dry_run:
        return

    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Falta YOUTUBE_API_KEY: pégala en el archivo .env de la raíz del proyecto.")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    budget = Budget(args.budget)
    hits = defaultdict(lambda: defaultdict(int))  # channel_id -> niche -> veces
    titles = defaultdict(set)                     # channel_id -> títulos encontrados (para detectar el idioma)
    for niche, q, order, region, params in plan:
        try:
            found = search_channels(params, key, budget, cache_dir)
        except QuotaError as e:
            print(f"[aviso] {e} Se continúa con lo recolectado.")
            break
        distinct = {f["channel_id"] for f in found}
        for cid in distinct:
            hits[cid][niche] += 1
        for f in found:
            titles[f["channel_id"]].add(f["title"])
        print(f"  {niche:<16} '{q}' ({order or 'canales'}, {region}): {len(distinct)} canales distintos")

    try:
        details, drops = fetch_channels(list(hits), key, budget)
    except QuotaError as e:
        sys.exit(f"{e} Vuelve a correr el script: las búsquedas ya guardadas no cuestan.")

    allowed = set() if args.countries.strip().upper() == "ANY" else {c.strip().upper() for c in args.countries.split(",") if c.strip()}
    if detect_langs is None and not args.no_lang_filter:
        print("[aviso] langdetect no está instalado: no se filtra por idioma. Corre: pip install langdetect")
    order_of = {n: i for i, n in enumerate(niches)}
    per_niche = defaultdict(list)
    for cid, d in details.items():
        if d["subscribers"] < args.min_subs:
            drops[f"menos de {args.min_subs} suscriptores"] += 1
            continue
        if d["video_count"] < args.min_videos:
            drops[f"menos de {args.min_videos} videos"] += 1
            continue
        if allowed and d["country"] and d["country"] not in allowed:
            drops["país no hispanohablante"] += 1
            continue
        if not args.no_lang_filter:
            lang = other_language(sorted(titles[cid]))
            if lang:
                drops[f"videos en otro idioma ({lang})"] += 1
                continue
        best = max(hits[cid].items(), key=lambda kv: (kv[1], -order_of[kv[0]]))
        d["niche_slug"], d["hits"], d["size_bin"] = best[0], best[1], size_bin(d["subscribers"])
        per_niche[best[0]].append(d)

    print(f"\nCanales únicos que devolvieron las búsquedas: {len(hits)}")
    if drops:
        print("Descartados antes de elegir:")
        for reason, n in drops.most_common():
            print(f"  {n:>4}  {reason}")
    rows = []
    print("\nResumen por nicho (candidatos -> elegidos | chicos/medianos/grandes):")
    for niche in niches:
        picked = balanced_pick(per_niche[niche], args.per_niche)
        rows.extend(picked)
        c = {b: sum(1 for p in picked if p["size_bin"] == b) for b in ("small", "mid", "large")}
        print(f"  {niche:<16} {len(per_niche[niche]):>3} -> {len(picked):>3} | {c['small']}/{c['mid']}/{c['large']}")

    fields = ["handle", "niche_slug", "channel_id", "title", "subscribers", "video_count", "size_bin", "country", "hits"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} canales escritos en {args.out}. Unidades de cuota usadas en esta corrida: {budget.used}.")
    print("Revisa el CSV (borra los que no encajen) antes de correr la ingesta.")


if __name__ == "__main__":
    main()