"""Ideas que rinden por nicho: calcula desde la BD, guarda en niche_ideas y las sirve a la API."""
import json
from datetime import datetime, timezone

import numpy as np

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows
from ml.ideas import IdeasParams, compute_niche_ideas
from services.training import load_videos_df


def _np(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"No serializable: {type(o)}")


def _patrones(ds, grupo: str) -> list[dict]:
    """Patrones de título con evidencia (reusa scripts/hot_evergreen.py). Si no se puede importar, devuelve []."""
    try:
        from scripts.hot_evergreen import analizar_patrones
    except Exception:
        return []
    keep = ("grupo", "patron", "clase", "efecto", "ic99_bajo", "ic99_alto", "canales", "pct_canales_a_favor")
    return [{k: f[k] for k in keep} for f in analizar_patrones(ds, grupo) if f["clase"] != "sin evidencia"]


def compute_and_store(conn, niche_ids: list[int] | None = None, params: IdeasParams | None = None) -> dict[int, dict]:
    df = load_videos_df(conn)
    if df.empty:
        return {}
    cfg = merge_cfg({"data": {"niche_ids": niche_ids}} if niche_ids else None)
    ds, _ = select_training_rows(build_dataset(df, cfg), cfg)
    if ds.empty:
        return {}
    handles = {r["id"]: r["handle"] for r in conn.execute("SELECT id, handle FROM channels").fetchall()}
    patrones_todos = _patrones(ds, "todos")
    now = datetime.now(timezone.utc).isoformat()
    results: dict[int, dict] = {}
    for nid, g in ds.groupby("niche_id"):
        res = compute_niche_ideas(g, params)
        for lista in (res["hot"], res["evergreen"]):
            for tema in lista:
                for ej in tema["ejemplos"]:
                    ej["canal"] = handles.get(ej["channel_id"])
        res["patrones"] = patrones_todos + (_patrones(g, f"nicho {int(nid)}") if res["estado"] == "ok" else [])
        res["calculado"] = now
        res["nota"] = ("Describe qué temas rinden por encima de lo normal de su propio canal en las últimas semanas. "
                       "No predice el rendimiento de un video nuevo.")
        payload = json.dumps(res, default=_np, ensure_ascii=False)
        conn.execute(
            "INSERT INTO niche_ideas (niche_id, computed_at, payload) VALUES (%s, now(), %s::jsonb) "
            "ON CONFLICT (niche_id) DO UPDATE SET computed_at = now(), payload = EXCLUDED.payload",
            (int(nid), payload))
        results[int(nid)] = json.loads(payload)
    conn.commit()
    return results


def get_ideas(conn, niche_id: int) -> dict | None:
    row = conn.execute("SELECT payload FROM niche_ideas WHERE niche_id = %s", (niche_id,)).fetchone()
    return row["payload"] if row else None