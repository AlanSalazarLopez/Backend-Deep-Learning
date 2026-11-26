from fastapi import APIRouter, Depends, HTTPException, Response

import db
from controllers.deps import get_current_user
from models import channel as channel_model
from models import niche as niche_model
from models.channel import MAX_CHANNELS_PER_USER, ChannelCreatedOut, ChannelIn, ChannelOut, NicheIn, TrainingIn
from models.common import validate_one, validate_rows
from models.user import UserOut
from services import ingest_service
from services.youtube_client import YouTubeClient, YouTubeError

router = APIRouter(prefix="/channels", tags=["channels"])


def get_youtube() -> YouTubeClient:
    """Dependencia reemplazable en pruebas."""
    try:
        return YouTubeClient()
    except RuntimeError:
        raise HTTPException(503, "YouTube no está configurado en el servidor")


@router.post("", response_model=ChannelCreatedOut, status_code=201)
def register_channel(body: ChannelIn, user: UserOut = Depends(get_current_user),
                     conn=Depends(db.get_db), yt=Depends(get_youtube)):
    if channel_model.count_by_user(conn, user.id) >= MAX_CHANNELS_PER_USER:
        raise HTTPException(409, f"Puedes registrar hasta {MAX_CHANNELS_PER_USER} canales")
    if conn.execute("SELECT 1 FROM channels WHERE user_id = %s AND lower(handle) = lower(%s)",
                    (user.id, body.handle)).fetchone():
        raise HTTPException(409, "Ya registraste ese canal")     # antes de gastar cuota de YouTube
    try:
        info, videos = ingest_service.fetch_from_youtube(yt, body.handle)
    except ingest_service.ChannelNotFound:
        raise HTTPException(404, "No encontramos ese canal en YouTube")
    except YouTubeError as e:
        raise HTTPException(502, str(e))
    if conn.execute("SELECT 1 FROM channels WHERE user_id = %s AND yt_channel_id = %s",
                    (user.id, info.yt_channel_id)).fetchone():
        raise HTTPException(409, "Ya registraste ese canal")     # mismo canal con otro handle
    try:
        res = ingest_service.save_channel(conn, info, videos, user_id=user.id, source="client")
    except ingest_service.ChannelTaken:
        conn.rollback()
        raise HTTPException(409, "Ese canal ya pertenece a otro usuario")
    conn.commit()
    out = ChannelOut.model_validate({**res.channel, "id": res.channel["id"]})
    return ChannelCreatedOut(**out.model_dump(), suggested_niche_id=res.suggested_niche_id, videos_loaded=len(videos))


@router.get("/mine", response_model=list[ChannelOut])
def my_channels(user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    # siempre filtra por el usuario del token; los registros inválidos se omiten
    return validate_rows(ChannelOut, channel_model.list_by_user(conn, user.id), "channels")


@router.get("/{channel_id}", response_model=ChannelOut)
def one_channel(channel_id: int, user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    row = channel_model.get_owned(conn, channel_id, user.id)
    if row is None:
        raise HTTPException(404, "Canal no encontrado")
    return validate_one(ChannelOut, row, "channels")


@router.put("/{channel_id}/niche", response_model=ChannelOut)
def set_niche(channel_id: int, body: NicheIn, user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    if niche_model.get(conn, body.niche_id) is None:
        raise HTTPException(404, "Ese nicho no existe")
    row = conn.execute(f"UPDATE channels SET niche_id = %s WHERE id = %s AND user_id = %s RETURNING {channel_model.COLS}",
                       (body.niche_id, channel_id, user.id)).fetchone()
    if row is None:
        conn.rollback()
        raise HTTPException(404, "Canal no encontrado")
    conn.commit()
    return validate_one(ChannelOut, row, "channels")


@router.put("/{channel_id}/training", response_model=ChannelOut)
def set_training(channel_id: int, body: TrainingIn, user: UserOut = Depends(get_current_user),
                 conn=Depends(db.get_db)):
    """El cliente decide si los videos de SU canal entran al entrenamiento y a las ideas del nicho."""
    row = conn.execute(f"UPDATE channels SET share_for_training = %s WHERE id = %s AND user_id = %s "
                       f"RETURNING {channel_model.COLS}", (body.share, channel_id, user.id)).fetchone()
    if row is None:
        conn.rollback()
        raise HTTPException(404, "Canal no encontrado")
    conn.commit()
    return validate_one(ChannelOut, row, "channels")


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: int, user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    row = conn.execute("DELETE FROM channels WHERE id = %s AND user_id = %s RETURNING id",
                       (channel_id, user.id)).fetchone()
    if row is None:
        conn.rollback()
        raise HTTPException(404, "Canal no encontrado")
    conn.commit()
    return Response(status_code=204)