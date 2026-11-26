"""Descubrimiento semanal de canales con tope de cuota (bloque 1 del plan nuevo).

Uso (desde backend/, con el entorno activo):
  python -m scripts.discover_weekly --dry-run                  # solo estima la cuota, no llama a YouTube ni toca la BD
  python -m scripts.discover_weekly --no-ingest --budget 600   # prueba barata: descubre y puntúa, no ingesta
  python -m scripts.discover_weekly                            # corrida normal (presupuesto 3,000 unidades)
  python -m scripts.discover_weekly --niches gaming,educacion,ciencia-tech --max-new 30

Qué hace, en orden (cada paso con su tope de cuota; si uno se agota, los demás siguen):
  1. populares: listas "más populares" por región y categoría (1 unidad por 50 videos). Trae canales consolidados.
  2. búsqueda: search.list de videos recientes (100 unidades cada una). Trae canales chicos y medianos.
  3. perfiles: channels.list solo de los canales que no conocíamos (1 unidad por 50). Filtros duros: país, suscriptores,
     idioma. Los rechazados se guardan con su motivo para no gastar cuota en ellos otra vez.
  4. elección: puntaje de preselección; un cupo para PROSPECTOS (chicos/nuevos) y el resto para CONSOLIDADOS.
     Lo que no entra queda en la banca (channel_candidates, status 'new') y compite la semana siguiente.
  5. ingesta: los elegidos se cargan como canales semilla (~5 unidades cada uno) y pasan las mismas revisiones de
     scripts/ingest.py (idioma, mínimo de videos válidos, categoría). Los que no pasan se borran y quedan rechazados.
Todo lo gastado se anota en quota_log. Tablas: ver C1_candidatos.sql.
"""
import argparse
import logging
from collections import Counter
from datetime import datetime, timezone

from config import ROOT
from ml.config import merge_cfg
from scripts._common import connect
from scripts.discover_channels import DEFAULT_REGIONS, NICHE_CATEGORY, NICHE_QUERIES
from scripts.ingest import SEED_MAX_VIDEOS, check_channel
from services import discovery_service as ds
from services import ingest_service
from services.quota import Budget, BudgetedYouTube, QuotaStop
from services.youtube_client import YouTubeError, YouTubeQuotaError

INGEST_UNITS_PER_CHANNEL = 5    # channels.list/forHandle (1) + 2 páginas de playlistItems (2) + 2 lotes de videos (2)


def ingest_one(conn, yt, cand: dict, cfg: dict) -> tuple[str | None, str | None]:
    """Ingesta un candidato. Devuelve (status, motivo): 'ingested', 'rejected', o None si falló por algo pasajero
    (se queda en la banca para la próxima semana). Relanza YouTubeQuotaError."""
    d, lab = cfg["data"], cfg["label"]
    nid = cand["niche_id"]
    try:
        info, videos = ingest_service.fetch_from_youtube(yt, cand["handle"], max_videos=SEED_MAX_VIDEOS)
        res = ingest_service.save_channel(conn, info, videos, user_id=None, source="seed", niche_id=nid)
        conn.commit()
    except ingest_service.ChannelNotFound:
        return "rejected", "no existe"
    except ingest_service.ChannelTaken:
        conn.rollback()
        return "rejected", "ya es de un cliente"
    except YouTubeQuotaError:
        conn.rollback()
        raise
    except YouTubeError as e:
        conn.rollback()
        return None, str(e)[:200]
    reason, _ = check_channel(conn, res.channel["id"], nid, res.language, d["language"], d["min_duration_s"],
                              d["max_duration_s"], lab["min_age_days"], lab["max_age_days"])
    if reason and "categoría" in reason:
        # el nicho venía de la búsqueda (ruidosa): si sus videos largos son de otro de nuestros nichos, se reasigna
        new_nid = res.suggested_niche_id
        if new_nid and new_nid != nid:
            new_reason, _ = check_channel(conn, res.channel["id"], new_nid, res.language, d["language"],
                                          d["min_duration_s"], d["max_duration_s"], lab["min_age_days"],
                                          lab["max_age_days"])
            if new_reason is None:
                conn.execute("UPDATE channels SET niche_id = %s WHERE id = %s", (new_nid, res.channel["id"]))
                conn.commit()
                return "ingested", None
        cats = conn.execute(
            "SELECT yt_category_id AS c, COUNT(*) AS n FROM videos WHERE channel_id = %s "
            "GROUP BY yt_category_id ORDER BY n DESC LIMIT 3", (res.channel["id"],)).fetchall()
        reason += " [categorías: " + ", ".join(f"{r['c']}:{r['n']}" for r in cats) + "]"
    if reason and res.channel["source"] == "seed":
        conn.execute("DELETE FROM channels WHERE id = %s", (res.channel["id"],))
        conn.commit()
        return "rejected", reason
    return "ingested", None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--niches", default="", help="slugs separados por coma; por defecto, todos los nichos")
    ap.add_argument("--regions", default=",".join(DEFAULT_REGIONS))
    ap.add_argument("--budget", type=int, default=3000, help="tope TOTAL de unidades de la corrida")
    ap.add_argument("--popular-cap", type=int, default=300, help="tope del paso 'populares'")
    ap.add_argument("--search-cap", type=int, default=1200, help="tope del paso 'búsqueda' (100 por búsqueda)")
    ap.add_argument("--popular-pages", type=int, default=2, help="páginas de 50 por lista de populares")
    ap.add_argument("--queries-per-niche", type=int, default=1, help="búsquedas por nicho (rotan cada semana)")
    ap.add_argument("--order", default="viewCount", choices=["viewCount", "date", "relevance"])
    ap.add_argument("--window-days", type=int, default=14, help="antigüedad máxima de los videos buscados")
    ap.add_argument("--max-new", type=int, default=40, help="máximo de canales nuevos a ingestar")
    ap.add_argument("--probe-factor", type=int, default=3,
                    help="a cuántos canales se les mide la actividad real antes de ingestar (max-new x este número)")
    ap.add_argument("--probe-cap", type=int, default=300, help="tope del paso 'preseleccion' (1 a 3 unidades por canal)")
    ap.add_argument("--explore-share", type=float, default=ds.EXPLORE_SHARE, help="fracción de lugares para prospectos")
    ap.add_argument("--no-ingest", action="store_true", help="descubre y puntúa, pero no ingesta")
    ap.add_argument("--lang-filter", action="store_true",
                    help="descarta por idioma con los pocos títulos de la búsqueda (confunde el español con "
                         "catalán, portugués o italiano); por defecto lo decide la ingesta")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    niches = [n for n in (args.niches.split(",") if args.niches else NICHE_QUERIES) if n]
    unknown = [n for n in niches if n not in NICHE_CATEGORY]
    if unknown:
        raise SystemExit(f"Nichos desconocidos: {unknown}. Disponibles: {list(NICHE_CATEGORY)}")
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]

    pop_units = len(niches) * len(regions) * args.popular_pages
    search_units = len(niches) * args.queries_per_niche * 100
    ingest_units = 0 if args.no_ingest else args.max_new * INGEST_UNITS_PER_CHANNEL
    probe_units = 0 if args.no_ingest else min(args.max_new * args.probe_factor * 2, args.probe_cap)
    print(f"Estimado máximo: populares {pop_units} (tope {args.popular_cap}) + búsqueda {search_units} "
          f"(tope {args.search_cap}) + perfiles ~{max(1, pop_units // 10)} + preselección ~{probe_units} "
          f"+ ingesta ~{ingest_units} = ~{min(pop_units, args.popular_cap) + min(search_units, args.search_cap) + probe_units + ingest_units} "
          f"unidades de {args.budget} de presupuesto.")
    if args.dry_run:
        return

    week = datetime.now(timezone.utc).isocalendar().week
    budget = Budget(args.budget)
    yt = BudgetedYouTube(budget)
    cfg = merge_cfg()
    found = ds.Found()
    with connect() as conn:
        niche_ids = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM niches").fetchall()}
        niches = [n for n in niches if n in niche_ids]
        in_db, known = ds.load_known(conn)
        stopped = None
        summary: dict = {}
        try:
            # 1-2. recolectar
            with budget.step("populares", args.popular_cap):
                summary["listas_populares"] = ds.collect_popular(yt, found, niches, regions, args.popular_pages)
            with budget.step("busqueda", args.search_cap):
                summary["busquedas"] = ds.collect_search(yt, found, niches, regions, week, args.queries_per_niche,
                                                         args.order, args.window_days, ROOT / "data" / ".cache_discover")
            seen = set(found.hits)
            skip = {c for c in seen if c in in_db or known.get(c) in ("ingested", "rejected")}
            again = {c for c in seen if known.get(c) == "new" and c not in in_db}
            fresh = sorted(seen - skip - again)
            summary.update(canales_vistos=len(seen), ya_en_bd_o_decididos=len(skip), ya_en_banca=len(again),
                           desconocidos=len(fresh))
            ds.bump_known(conn, found, again)

            # 3. perfiles y filtros duros (solo de los desconocidos)
            with budget.step("perfiles"):
                details = yt.channels_by_ids(fresh) if fresh else {}
            ok, bad = ds.screen(found, details, niches, lang_filter=args.lang_filter)
            ds.insert_candidates(conn, ok, niche_ids)
            ds.insert_candidates(conn, bad, niche_ids, rejected=True)
            conn.commit()
            summary["rechazados_por_filtro"] = dict(Counter(r["reason"] for r in bad))
            summary["nuevos_en_banca"] = len(ok)

            # 4. puntuar y elegir
            scored = ds.score_pending(ds.pending(conn))
            ds.save_scores(conn, scored)
            conn.commit()
            summary["en_banca_total"] = len(scored)
            chosen = []
            if not args.no_ingest:
                # 4b. preselección: ¿de verdad publica videos largos? Mide los 'max-new x probe-factor' mejores
                vigentes, por_probar = ds.split_probed(scored)
                lote = ds.pick_for_ingest(por_probar, args.max_new * args.probe_factor, args.explore_share, len(niches))
                with budget.step("preseleccion", args.probe_cap):
                    passed, n_rej, n_unk = ds.probe_candidates(conn, yt, lote)
                summary["preseleccion"] = {"revisados": len(lote), "aprobados": len(passed), "rechazados": n_rej,
                                           "sin_dato": n_unk, "ya_aprobados_antes": len(vigentes)}
                chosen = ds.pick_for_ingest(vigentes + passed, args.max_new, args.explore_share, len(niches))
            summary["elegidos"] = Counter(c["pool"] for c in chosen)

            # 5. ingestar
            results = Counter()
            with budget.step("ingesta"):
                for i, cand in enumerate(chosen, 1):
                    status, reason = ingest_one(conn, yt, cand, cfg)
                    if status:
                        ds.mark_candidate(conn, cand["yt_channel_id"], status, reason)
                        conn.commit()
                    results[status or "error_pasajero"] += 1
                    print(f"[{i}/{len(chosen)}] {cand['handle']} ({cand['pool']}): "
                          f"{status or 'error pasajero'}{' - ' + reason if reason else ''}")
            summary["ingesta"] = dict(results)
        except QuotaStop as e:
            conn.rollback()
            stopped = str(e)
        except YouTubeQuotaError as e:       # cuota diaria real agotada (403)
            conn.rollback()
            stopped = f"{e}. Lo ya guardado se conserva; vuelve a correr mañana."
        finally:
            ds.log_quota(conn, budget.by_step)
            conn.commit()

    print("\n== Resumen")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  cuota gastada: {budget.used} de {budget.total} -> {dict(budget.by_step)}")
    if stopped:
        print(f"  AVISO: corrida detenida antes de terminar: {stopped}")


if __name__ == "__main__":
    main()