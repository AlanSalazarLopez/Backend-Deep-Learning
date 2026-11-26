"""Guarda y carga modelos en la tabla model_runs (el disco de Render gratis es efímero)."""
import json

from config import settings

_cache: dict = {"run_id": None, "model": None}


def get_active(conn):
    """Devuelve (run_id, LoadedModel) del modelo activo, o None. Recarga solo si cambió el activo."""
    row = conn.execute("SELECT id FROM model_runs WHERE is_active").fetchone()
    if row is None:
        return None
    if _cache["run_id"] != row["id"]:
        from ml.service import load_model  # import tardío: pandas y scikit-learn pesan al arrancar
        art = conn.execute("SELECT artifact FROM model_runs WHERE id = %s", (row["id"],)).fetchone()["artifact"]
        _cache.update(run_id=row["id"], model=load_model(bytes(art)))
    return _cache["run_id"], _cache["model"]


def get_active_config(conn) -> dict:
    from ml.config import merge_cfg
    row = conn.execute("SELECT config FROM model_runs WHERE is_active").fetchone()
    return merge_cfg(row["config"] if row else None)


def save_run(conn, result, trained_by: int | None = None, activate: bool = True) -> int:
    """Inserta el modelo (y lo activa). Sin commit: lo hace quien llama."""
    if activate:
        conn.execute("UPDATE model_runs SET is_active = FALSE WHERE is_active")
    row = conn.execute(
        "INSERT INTO model_runs (trained_by, config, metrics, n_videos, n_channels, artifact, is_active) "
        "VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, %s, %s) RETURNING id",
        (trained_by, json.dumps(result.config), json.dumps(result.metrics), result.n_videos,
         result.n_channels, result.artifact, activate)).fetchone()
    conn.execute(
        "DELETE FROM model_runs WHERE NOT is_active AND id NOT IN "
        "(SELECT id FROM model_runs ORDER BY id DESC LIMIT %s)", (settings.model_keep_last,))
    return row["id"]
