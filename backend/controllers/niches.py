import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

import db
from controllers.deps import get_current_user
from models import channel as channel_model
from models import niche as niche_model
from models.common import VALID_VIDEO, validate_rows
from models.niche import NicheOut, OverviewOut, TopicOut
from models.user import UserOut
from services import model_store
from services.training import load_videos_df

router = APIRouter(prefix="/niches", tags=["niches"])


def _stats(ds) -> dict:
    if ds.empty:
        return {"n_videos": 0, "median_views_per_day": 0.0, "pct_outperformers": 0.0}
    return {"n_videos": int(len(ds)), "median_views_per_day": round(float(np.median(ds["velocity"])), 1),
            "pct_outperformers": round(float(ds["y"].mean()), 3)}


@router.get("", response_model=list[NicheOut])
def list_niches(user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    rows = conn.execute(
        "SELECT n.id, n.slug, n.name, (SELECT COUNT(*) FROM videos v JOIN channels c ON c.id = v.channel_id "
        f"WHERE c.niche_id = n.id AND {VALID_VIDEO}) AS n_videos FROM niches n ORDER BY n.id").fetchall()
    return validate_rows(NicheOut, rows, "niches")


@router.get("/{niche_id}/overview", response_model=OverviewOut)
def overview(niche_id: int, channel_id: int | None = Query(None, ge=1),
             user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    from ml.dataset import build_dataset
    niche = niche_model.get(conn, niche_id)
    if niche is None:
        raise HTTPException(404, "Ese nicho no existe")
    if channel_id is not None:
        ch = channel_model.get_owned(conn, channel_id, user.id)       # solo canales propios
        if ch is None:
            raise HTTPException(404, "Canal no encontrado")
    else:
        mine = channel_model.list_by_user(conn, user.id)
        if not mine:
            raise HTTPException(409, "Primero registra tu canal")
        ch = next((c for c in mine if c["niche_id"] == niche_id), mine[0])   # uno de ese nicho si existe
    cfg = model_store.get_active_config(conn)

    niche_df = load_videos_df(conn, niche_id=niche_id)
    niche_ds = build_dataset(niche_df, cfg) if not niche_df.empty else niche_df
    own_df = load_videos_df(conn, channel_id=ch["id"])
    if not own_df.empty:
        own_df["niche_id"] = niche_id        # la línea base de respaldo se toma del nicho explorado
    own_ds = build_dataset(own_df, cfg) if not own_df.empty else own_df

    top = []
    if not own_ds.empty:
        for _, r in own_ds.sort_values("ratio", ascending=False).head(5).iterrows():
            top.append({"yt_video_id": r["yt_video_id"], "title": r["title"], "views": int(r["views"]),
                        "ratio": round(float(r["ratio"]), 2)})
    return OverviewOut(
        niche={"id": niche["id"], "name": niche["name"]}, window_days=cfg["label"]["max_age_days"],
        own=_stats(own_ds),
        niche_stats={**_stats(niche_ds), "n_channels": int(niche_ds["channel_id"].nunique()) if len(niche_ds) else 0},
        own_top_videos=top)


@router.get("/{niche_id}/topics", response_model=list[TopicOut])
def topics(niche_id: int, limit: int = Query(10, ge=1, le=50), user: UserOut = Depends(get_current_user),
           conn=Depends(db.get_db)):
    from ml.topics import topic_ranking
    if niche_model.get(conn, niche_id) is None:
        raise HTTPException(404, "Ese nicho no existe")
    df = load_videos_df(conn, niche_id=niche_id)
    return topic_ranking(df, niche_id, model_store.get_active_config(conn), limit) if not df.empty else []