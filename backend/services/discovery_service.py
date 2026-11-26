"""Descubrimiento semanal de canales (bloque 1 del plan nuevo).

Flujo (lo orquesta scripts/discover_weekly.py):
  1. RECOLECTAR candidatos: (a) listas "más populares" por región y categoría (1 unidad por 50 videos; trae
     canales consolidados) y (b) búsquedas de videos recientes por categoría (100 unidades cada una; trae canales
     chicos y medianos). Las consultas de (b) rotan cada semana, así no se repiten.
  2. FILTRAR con filtros duros que no cuestan cuota extra (país, suscriptores, idioma de los títulos...).
  3. PUNTUAR (puntaje de preselección, todo con datos que ya trajo channels.list) y ELEGIR quién se ingesta:
     un porcentaje de lugares reservado para PROSPECTOS (canales chicos o nuevos) y el resto para CONSOLIDADOS,
     con tope por nicho para que ninguno se coma todo el cupo.
Lo que no se elige queda en la banca (status 'new') y vuelve a competir la semana siguiente.

El puntaje es una guía inicial, no algo validado: mide actividad (cuánto publica), apariciones recientes y si
YouTube lo está empujando. NO usa las vistas del canal, porque la etiqueta del modelo ya compara cada video
contra el promedio de su propio canal. La calidad real (constancia, ratio) se mide después, con los videos ya
ingestados.
"""
import hashlib
import json
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.discover_channels import NICHE_CATEGORY, NICHE_QUERIES, SPANISH_COUNTRIES, other_language
from services.quota import StepCapReached
from services.youtube_client import YouTubeError, YouTubeQuotaError

log = logging.getLogger("discovery")

# --- filtros duros (los mismos de discover_channels.py)
MIN_SUBS = 1000
MIN_VIDEO_COUNT = 30
# --- consolidados vs prospectos
PROSPECT_MAX_SUBS = 50_000       # menos suscriptores que esto = prospecto
PROSPECT_MAX_AGE_MONTHS = 18     # canal "nuevo" (suma puntos de frescura)
EXPLORE_SHARE = 0.25             # fracción de los lugares reservada a prospectos
NICHE_CAP_FACTOR = 1.5           # ningún nicho recibe más de 1.5 veces su parte justa
# --- pesos del puntaje (suman 1.0)
W_ACTIVITY, W_HITS, W_POPULAR, W_FRESH = 0.45, 0.35, 0.10, 0.10
ACTIVITY_SAT = 8.0               # 8 videos al mes o más = actividad máxima
HITS_SAT = 4                     # 4 apariciones o más = máximo
SHORTS_FACTORY_UPM = 30          # más de ~30 videos al mes de vida casi siempre son Shorts o clips: la actividad se penaliza
# --- preselección con datos reales (ver probe_candidates)
PROBE_MIN = 20                   # videos largos mínimos en 180 días para gastar una ingesta (el modelo exige 15; margen)
PROBE_FRESH_DAYS = 28            # una preselección aprobada vale 4 semanas


# ----------------------------------------------------------------------------- recolección
@dataclass
class Found:
    hits: dict = field(default_factory=lambda: defaultdict(Counter))   # channel_id -> nicho -> veces
    titles: dict = field(default_factory=lambda: defaultdict(set))     # channel_id -> títulos vistos
    popular: set = field(default_factory=set)                          # channel_id que salieron en "populares"

    def add(self, channel_id: str, niche: str, title: str, popular: bool = False) -> None:
        self.hits[channel_id][niche] += 1
        self.titles[channel_id].add(title)
        if popular:
            self.popular.add(channel_id)

    def hits_total(self, channel_id: str) -> int:
        return int(sum(self.hits[channel_id].values()))

    def best_niche(self, channel_id: str, order_of: dict) -> str:
        return max(self.hits[channel_id].items(), key=lambda kv: (kv[1], -order_of[kv[0]]))[0]


def week_queries(niche: str, week: int, k: int) -> list[str]:
    """Las k consultas de la semana para un nicho: la lista rota con el número de semana."""
    qs = NICHE_QUERIES[niche]
    return [qs[(week * k + i) % len(qs)] for i in range(k)]


def collect_popular(yt, found: Found, niches, regions, pages: int) -> int:
    """Devuelve cuántas listas se leyeron. Se detiene sin error si se acaba el tope del paso."""
    n_ok = 0
    for niche in niches:
        for region in regions:
            try:
                vids = yt.most_popular(region, NICHE_CATEGORY[niche], pages)
            except StepCapReached:
                return n_ok
            except YouTubeQuotaError:
                raise
            except YouTubeError as e:     # esa categoría no tiene lista de populares en esa región
                log.info("populares %s/%s sin lista (%s)", niche, region, e)
                continue
            for v in vids:
                found.add(v["channel_id"], niche, v["title"], popular=True)
            n_ok += 1
    return n_ok


def _search_cached(yt, params: dict, cache_dir: Path | None) -> list[dict]:
    """search.list con caché en disco: repetir la misma búsqueda el mismo día no gasta cuota."""
    f = None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        f = cache_dir / (hashlib.md5(("w1" + json.dumps(params, sort_keys=True)).encode()).hexdigest() + ".json")
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    items = yt.search_videos(params)
    if f:
        f.write_text(json.dumps(items), encoding="utf-8")
    return items


def collect_search(yt, found: Found, niches, regions, week: int, per_niche: int, order: str, window_days: int,
                   cache_dir: Path | None, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    after = (now - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00Z")
    n_ok = turn = 0
    for niche in niches:
        for q in week_queries(niche, week, per_niche):
            region = regions[turn % len(regions)]
            turn += 1
            params = {"type": "video", "q": q, "videoCategoryId": str(NICHE_CATEGORY[niche]), "order": order,
                      "publishedAfter": after, "relevanceLanguage": "es", "regionCode": region}
            try:
                items = _search_cached(yt, params, cache_dir)
            except StepCapReached:
                return n_ok
            except YouTubeQuotaError:
                raise
            except YouTubeError as e:
                log.info("búsqueda '%s' falló (%s)", q, e)
                continue
            for it in items:
                found.add(it["channel_id"], niche, it["title"])
            n_ok += 1
    return n_ok


# ----------------------------------------------------------------------------- filtros duros
def screen(found: Found, details: dict, niches, allowed_countries: set | None = None, lang_filter: bool = True,
           min_subs: int = MIN_SUBS, min_videos: int = MIN_VIDEO_COUNT) -> tuple[list[dict], list[dict]]:
    """Devuelve (aceptados, rechazados). Cada fila trae el nicho más frecuente del canal."""
    allowed = SPANISH_COUNTRIES.split(",") if allowed_countries is None else allowed_countries
    allowed = {c.strip().upper() for c in allowed if c.strip()}
    order_of = {n: i for i, n in enumerate(niches)}
    ok, bad = [], []
    for cid, d in details.items():
        if cid not in found.hits:
            continue
        row = {"yt_channel_id": cid, "handle": d["handle"], "title": d["title"], "niche": found.best_niche(cid, order_of),
               "country": d["country"], "subscribers": d["subscribers"] or 0, "video_count": d["video_count"],
               "created": d["created"], "in_popular": cid in found.popular, "hits": found.hits_total(cid)}
        reason = None
        if d["subscribers"] is None:
            reason = "suscriptores ocultos"
        elif not d["handle"].startswith("@"):
            reason = "sin @handle utilizable"
        elif d["subscribers"] < min_subs:
            reason = f"menos de {min_subs} suscriptores"
        elif d["video_count"] < min_videos:
            reason = f"menos de {min_videos} videos"
        elif allowed and d["country"] and d["country"].upper() not in allowed:
            reason = "país no hispanohablante"
        elif lang_filter:
            lang = other_language(sorted(found.titles[cid]))
            if lang:
                reason = f"videos en otro idioma ({lang})"
        (bad if reason else ok).append({**row, "reason": reason} if reason else row)
    return ok, bad


# ----------------------------------------------------------------------------- puntaje y elección
def _age_months(created: datetime | None, now: datetime) -> float:
    if created is None:
        return 60.0     # sin fecha: se asume un canal viejo
    return max((now - created).total_seconds() / (86400 * 30.4), 0.0)


def prescreen_score(video_count: int, created: datetime | None, hits: int, in_popular: bool, now: datetime,
                    longform_180d: int | None = None) -> float:
    """0 a 1. Actividad, apariciones recientes, presencia en "populares" y frescura del canal.
    Actividad: si ya se midió (longform_180d, videos largos en 180 días) se usa ese dato real. Si no, se aproxima con
    los videos totales por mes de vida del canal, que INCLUYEN Shorts: por eso, por encima de ~30 al mes se
    penaliza (casi siempre es una fábrica de Shorts, que al modelo no le sirve)."""
    age = _age_months(created, now)
    if longform_180d is not None:
        activity = min(longform_180d / (ACTIVITY_SAT * 6), 1.0)
    else:
        upm = video_count / max(age, 3.0)
        activity = min(upm / ACTIVITY_SAT, 1.0)
        if upm > SHORTS_FACTORY_UPM:
            activity = max(0.0, 1.0 - (upm - SHORTS_FACTORY_UPM) / SHORTS_FACTORY_UPM)
    hits_n = min(hits, HITS_SAT) / HITS_SAT
    fresh = 1.0 if age <= PROSPECT_MAX_AGE_MONTHS else 0.0
    return W_ACTIVITY * activity + W_HITS * hits_n + W_POPULAR * (1.0 if in_popular else 0.0) + W_FRESH * fresh


def pool_of(subscribers: int) -> str:
    return "prospect" if subscribers < PROSPECT_MAX_SUBS else "established"


def pick_for_ingest(cands: list[dict], n: int, explore_share: float = EXPLORE_SHARE,
                    n_niches: int | None = None) -> list[dict]:
    """Elige hasta n candidatos (cada uno con niche_id, pool, score, yt_channel_id).
    1) primero los mejores PROSPECTOS hasta el cupo de exploración; 2) luego los mejores CONSOLIDADOS hasta n;
    3) si faltaron consolidados, se rellena con prospectos; 4) si aún falta (pocos nichos con candidatos), se
    rellena sin el tope por nicho. En todos los pasos, mejor puntaje primero."""
    if n <= 0 or not cands:
        return []
    n_niches = n_niches or len({c["niche_id"] for c in cands}) or 1
    cap = max(1, math.ceil(NICHE_CAP_FACTOR * n / n_niches))
    by_score = sorted(cands, key=lambda c: (-c["score"], c["yt_channel_id"]))
    chosen: list[dict] = []
    ids: set = set()
    per_niche: Counter = Counter()

    def fill(pool: str, target: int) -> None:
        for c in by_score:
            if len(chosen) >= target:
                return
            if c["pool"] != pool or c["yt_channel_id"] in ids or per_niche[c["niche_id"]] >= cap:
                continue
            chosen.append(c)
            ids.add(c["yt_channel_id"])
            per_niche[c["niche_id"]] += 1

    fill("prospect", round(n * explore_share))
    fill("established", n)
    fill("prospect", n)
    for c in by_score:
        if len(chosen) >= n:
            break
        if c["yt_channel_id"] not in ids:
            chosen.append(c)
            ids.add(c["yt_channel_id"])
    return chosen


# ----------------------------------------------------------------------------- base de datos
def load_known(conn) -> tuple[set, dict]:
    """(yt_channel_id de canales que ya están en la BD, {yt_channel_id: status} de candidatos)."""
    channels = {r["yt_channel_id"] for r in conn.execute("SELECT yt_channel_id FROM channels").fetchall()}
    cands = {r["yt_channel_id"]: r["status"] for r in conn.execute(
        "SELECT yt_channel_id, status FROM channel_candidates").fetchall()}
    return channels, cands


_INSERT = ("INSERT INTO channel_candidates (yt_channel_id, handle, title, niche_id, country, subscribers, video_count, "
           "channel_created, in_popular, hits, status, reject_reason, decided_at) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (yt_channel_id) DO NOTHING")


def insert_candidates(conn, rows: list[dict], niche_ids: dict, rejected: bool = False) -> None:
    now = datetime.now(timezone.utc)
    data = [(r["yt_channel_id"], r["handle"], r["title"], niche_ids[r["niche"]], r["country"], r["subscribers"],
             r["video_count"], r["created"], r["in_popular"], r["hits"], "rejected" if rejected else "new",
             r.get("reason"), now if rejected else None) for r in rows]
    if data:
        with conn.cursor() as cur:
            cur.executemany(_INSERT, data)


def bump_known(conn, found: Found, ids) -> None:
    """Candidatos 'new' que volvieron a salir: suma sus apariciones sin volver a gastar cuota en su perfil.
    Si ya salió hoy (por ejemplo, una segunda corrida el mismo día) no se suma dos veces."""
    sql = ("UPDATE channel_candidates SET "
           "hits = CASE WHEN last_seen::date < CURRENT_DATE THEN hits + %s ELSE GREATEST(hits, %s) END, "
           "in_popular = in_popular OR %s, last_seen = now() WHERE yt_channel_id = %s AND status = 'new'")
    data = [(found.hits_total(c), found.hits_total(c), c in found.popular, c) for c in ids]
    if data:
        with conn.cursor() as cur:
            cur.executemany(sql, data)


def pending(conn) -> list[dict]:
    """Candidatos en la banca que todavía no son canales de la BD."""
    return conn.execute(
        "SELECT c.* FROM channel_candidates c WHERE c.status = 'new' AND NOT EXISTS "
        "(SELECT 1 FROM channels h WHERE h.yt_channel_id = c.yt_channel_id)").fetchall()


def score_pending(rows: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    out = []
    for r in rows:
        out.append({**r, "score": prescreen_score(r["video_count"], r["channel_created"], r["hits"], r["in_popular"], now,
                                         r.get("longform_180d")),
                    "pool": pool_of(r["subscribers"])})
    return out


def save_scores(conn, scored: list[dict]) -> None:
    if scored:
        with conn.cursor() as cur:
            cur.executemany("UPDATE channel_candidates SET score = %s, pool = %s WHERE yt_channel_id = %s",
                            [(round(c["score"], 4), c["pool"], c["yt_channel_id"]) for c in scored])


def mark_candidate(conn, yt_channel_id: str, status: str, reason: str | None = None) -> None:
    conn.execute("UPDATE channel_candidates SET status = %s, reject_reason = %s, decided_at = now() "
                 "WHERE yt_channel_id = %s", (status, reason, yt_channel_id))


def log_quota(conn, by_step: dict) -> None:
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO quota_log (step, units) VALUES (%s, %s)",
                        [(k, int(v)) for k, v in by_step.items() if v])


# ----------------------------------------------------------------------------- preselección con datos reales
def split_probed(scored: list[dict], now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """(canales con preselección vigente y aprobada, canales por preseleccionar). Los reprobados ya no están en la
    banca: probe_candidates los marca como rechazados."""
    now = now or datetime.now(timezone.utc)
    vigentes, por_probar = [], []
    for c in scored:
        p, n = c.get("probed_at"), c.get("longform_180d")
        if p is not None and n is not None and n >= PROBE_MIN and (now - p) <= timedelta(days=PROBE_FRESH_DAYS):
            vigentes.append(c)
        else:
            por_probar.append(c)
    return vigentes, por_probar


def probe_candidates(conn, yt, cands: list[dict], now: datetime | None = None) -> tuple[list[dict], int, int]:
    """Mide cuántos videos largos publicó cada candidato en 180 días (1 a 3 unidades por canal). Los que no llegan a
    PROBE_MIN se rechazan con ese motivo; los aprobados se devuelven con su puntaje recalculado con el dato real.
    Se detiene sin error si se agota el tope del paso. Devuelve (aprobados, n_rechazados, n_sin_dato)."""
    now = now or datetime.now(timezone.utc)
    passed: list[dict] = []
    rejected = unknown = 0
    try:
        for c in cands:
            n = yt.recent_long_form_count(c["yt_channel_id"], now=now)
            if n is None:
                unknown += 1
                continue
            if n >= PROBE_MIN:
                conn.execute("UPDATE channel_candidates SET longform_180d = %s, probed_at = now() "
                             "WHERE yt_channel_id = %s", (n, c["yt_channel_id"]))
                passed.append({**c, "longform_180d": n, "probed_at": now,
                               "score": prescreen_score(c["video_count"], c["channel_created"], c["hits"],
                                                        c["in_popular"], now, n)})
            else:
                conn.execute("UPDATE channel_candidates SET longform_180d = %s, probed_at = now(), status = 'rejected', "
                             "reject_reason = %s, decided_at = now() WHERE yt_channel_id = %s",
                             (n, f"solo {n} videos largos en 180 días (preselección)", c["yt_channel_id"]))
                rejected += 1
    except StepCapReached:
        pass
    finally:
        conn.commit()
    return passed, rejected, unknown