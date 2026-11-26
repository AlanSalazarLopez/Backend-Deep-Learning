from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

import db
from controllers.deps import require_admin
from models import user as user_model
from models.admin import ModelOut, ModelRunOut, StatsOut
from models.common import VALID_PRED, VALID_VIDEO, validate_one, validate_rows
from models.user import AdminUserOut, PromoteOut, UserOut, UsersPage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=UsersPage)
def list_users(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               admin: UserOut = Depends(require_admin), conn=Depends(db.get_db)):
    valid = validate_rows(AdminUserOut, user_model.list_with_channel(conn), "users")  # los inválidos se omiten
    return UsersPage(items=valid[offset: offset + limit], total=len(valid))


@router.post("/users/{user_id}/promote", response_model=PromoteOut)
def promote(user_id: int, admin: UserOut = Depends(require_admin), conn=Depends(db.get_db)):
    row = user_model.get_row(conn, user_id)
    if row is None:
        raise HTTPException(404, "Usuario no encontrado")
    try:
        target = validate_one(UserOut, row, "users")
    except HTTPException:
        raise HTTPException(404, "Usuario no encontrado")   # un registro inválido no se puede promover
    user_model.set_role(conn, target.id, "admin")
    conn.commit()
    return PromoteOut(id=target.id, username=target.username, role="admin")


@router.get("/stats", response_model=StatsOut)
def stats(admin: UserOut = Depends(require_admin), conn=Depends(db.get_db)):
    users = validate_rows(AdminUserOut, user_model.list_with_channel(conn), "users")
    niches = conn.execute("SELECT id, name FROM niches ORDER BY id").fetchall()
    niche_name = {n["id"]: n["name"] for n in niches}

    pred_by_user = {r["user_id"]: r for r in conn.execute(
        f"SELECT p.user_id, COUNT(*) AS n, MAX(p.created_at) AS last FROM predictions p WHERE {VALID_PRED} "
        "GROUP BY p.user_id").fetchall()}
    valid_ids = [u.id for u in users]     # canales y videos de clientes: solo de usuarios válidos
    n_videos = conn.execute(f"SELECT COUNT(*) AS n FROM videos v JOIN channels c ON c.id = v.channel_id "
                            f"WHERE {VALID_VIDEO} AND c.user_id = ANY(%s::int[])", (valid_ids,)).fetchone()["n"]
    seed_videos = conn.execute(f"SELECT COUNT(*) AS n FROM videos v JOIN channels c ON c.id = v.channel_id "
                               f"WHERE {VALID_VIDEO} AND c.user_id IS NULL").fetchone()["n"]
    n_preds = conn.execute(f"SELECT COUNT(*) AS n FROM predictions p WHERE {VALID_PRED}").fetchone()["n"]
    n_channels = conn.execute("SELECT COUNT(*) AS n FROM channels WHERE handle <> '' AND title <> '' "
                              "AND user_id = ANY(%s::int[])", (valid_ids,)).fetchone()["n"]
    seed_channels = conn.execute("SELECT COUNT(*) AS n FROM channels WHERE handle <> '' AND title <> '' "
                                 "AND user_id IS NULL").fetchone()["n"]

    # un cliente puede tener varios canales: nichos y cantidad por usuario, solo con usuarios válidos
    client_ids = {u.id for u in users if u.role == "client"}
    niches_of: dict[int, set] = defaultdict(set)
    n_ch: Counter = Counter()
    for r in conn.execute("SELECT user_id, niche_id FROM channels WHERE user_id IS NOT NULL").fetchall():
        if r["user_id"] not in client_ids:
            continue
        n_ch[r["user_id"]] += 1
        if r["niche_id"] is not None:
            niches_of[r["user_id"]].add(r["niche_id"])

    per_client = []
    for u in users:
        if u.role != "client":
            continue
        pr = pred_by_user.get(u.id)
        names = ", ".join(niche_name[n] for n in sorted(niches_of.get(u.id, ())) if n in niche_name) or None
        per_client.append({"user_id": u.id, "username": u.username, "channel_handle": u.channel_handle,
                           "niche": names, "n_channels": int(n_ch.get(u.id, 0)),
                           "n_predictions": int(pr["n"]) if pr else 0,
                           "last_activity": pr["last"] if pr else u.created_at})

    clients_by_niche = Counter(n for s_ in niches_of.values() for n in s_)
    videos_by_niche = {r["niche_id"]: r["n"] for r in conn.execute(
        f"SELECT c.niche_id, COUNT(*) AS n FROM videos v JOIN channels c ON c.id = v.channel_id "
        f"WHERE {VALID_VIDEO} AND c.niche_id IS NOT NULL AND c.user_id = ANY(%s::int[]) GROUP BY c.niche_id",
        (valid_ids,)).fetchall()}
    preds_by_niche = {r["niche_id"]: r["n"] for r in conn.execute(
        f"SELECT p.niche_id, COUNT(*) AS n FROM predictions p WHERE {VALID_PRED} GROUP BY p.niche_id").fetchall()}
    by_niche = [{"niche_id": n["id"], "name": n["name"], "n_clients": clients_by_niche.get(n["id"], 0),
                 "n_videos": int(videos_by_niche.get(n["id"], 0)), "n_predictions": int(preds_by_niche.get(n["id"], 0))}
                for n in niches]

    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    counts = {r["d"]: r["n"] for r in conn.execute(
        f"SELECT (p.created_at AT TIME ZONE 'UTC')::date AS d, COUNT(*) AS n FROM predictions p "
        f"WHERE {VALID_PRED} AND p.created_at >= now() - interval '15 days' GROUP BY d").fetchall()}
    activity = [{"date": d.isoformat(), "n_predictions": int(counts.get(d, 0))} for d in days]

    return StatsOut(
        totals={"users": len(users), "clients": sum(u.role == "client" for u in users),
                "admins": sum(u.role == "admin" for u in users), "channels": int(n_channels),
                "videos": int(n_videos), "predictions": int(n_preds),
                "seed_channels": int(seed_channels), "seed_videos": int(seed_videos)},
        per_client=per_client, by_niche=by_niche, activity_by_day=activity)


@router.get("/model", response_model=ModelOut)
def active_model(admin: UserOut = Depends(require_admin), conn=Depends(db.get_db)):
    row = conn.execute("SELECT id, trained_at, n_videos, n_channels, metrics, config FROM model_runs "
                       "WHERE is_active").fetchone()
    return ModelOut(active=ModelRunOut.model_validate(row) if row else None)