"""Entrenamiento desde la BD: lee videos y canales, entrena y guarda en model_runs."""
import json

import pandas as pd

from services import model_store

VIDEOS_SQL = (
    "SELECT v.channel_id, c.niche_id, c.language, v.yt_video_id, v.title, v.published_at, v.duration_s, "
    "v.views, v.is_short, v.fetched_at FROM videos v JOIN channels c ON c.id = v.channel_id "
    "WHERE c.niche_id IS NOT NULL"
)


# Los canales semilla (user_id NULL) siempre entran; los de clientes solo si activaron share_for_training.
SHARED_ONLY = " AND (c.user_id IS NULL OR c.share_for_training)"


def load_videos_df(conn, niche_id: int | None = None, channel_id: int | None = None,
                   shared_only: bool = True) -> pd.DataFrame:
    """Videos con canal y nicho. Las cargas AGREGADAS (sin channel_id: entrenamiento, ideas, temas y la comparación
    del nicho) dejan fuera los canales de clientes que no dieron su consentimiento. La carga de UN canal
    (channel_id) no filtra: es para que su dueño vea sus propias estadísticas. shared_only=False desactiva el filtro
    (por ejemplo, para diagnósticos propios)."""
    sql, params = VIDEOS_SQL, []
    if channel_id is None and shared_only:
        sql += SHARED_ONLY
    if niche_id is not None:
        sql += " AND c.niche_id = %s"
        params.append(niche_id)
    if channel_id is not None:
        sql += " AND c.id = %s"
        params.append(channel_id)
    return pd.DataFrame(conn.execute(sql, params).fetchall())


def sources(conn) -> dict:
    """Cuántos canales y videos de semilla y de clientes se CARGAN para entrenar (antes de los filtros de idioma,
    duración y edad del dataset). Sirve para demostrar que el modelo usa datos de clientes."""
    r = conn.execute(
        "SELECT COUNT(DISTINCT c.id) FILTER (WHERE c.user_id IS NULL) AS canales_semilla, "
        "COUNT(DISTINCT c.id) FILTER (WHERE c.user_id IS NOT NULL) AS canales_clientes, "
        "COUNT(v.id) FILTER (WHERE c.user_id IS NULL) AS videos_semilla, "
        "COUNT(v.id) FILTER (WHERE c.user_id IS NOT NULL) AS videos_clientes "
        "FROM videos v JOIN channels c ON c.id = v.channel_id WHERE c.niche_id IS NOT NULL"
        + SHARED_ONLY).fetchone()
    return {k: int(v or 0) for k, v in r.items()}


def train_from_db(conn, cfg: dict | None = None, activate: bool = True, trained_by: int | None = None):
    from ml.service import train
    df = load_videos_df(conn)
    if df.empty:
        from ml.service import NotEnoughData
        raise NotEnoughData("No hay videos en la base de datos.")
    result = train(df, cfg)
    run_id = model_store.save_run(conn, result, trained_by=trained_by, activate=activate)
    conn.execute("UPDATE model_runs SET metrics = metrics || %s::jsonb WHERE id = %s",
                 (json.dumps({"fuentes": sources(conn)}), run_id))
    conn.commit()
    return run_id, result