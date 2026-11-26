"""Canal: esquemas y acceso a datos."""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

HANDLE_RE = re.compile(r"^@?[A-Za-z0-9._-]{3,30}$")
MAX_CHANNELS_PER_USER = 5   # cada registro cuesta ~5 unidades de la cuota diaria de YouTube
COLS = "id, yt_channel_id, handle, title, niche_id, language, share_for_training"


class ChannelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str

    @field_validator("handle")
    @classmethod
    def _handle(cls, v):
        v = v.strip()
        if not HANDLE_RE.match(v):
            raise ValueError("Escribe tu @handle, por ejemplo @micanal (3 a 30 caracteres)")
        return v if v.startswith("@") else "@" + v


class NicheIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    niche_id: int = Field(ge=1)


class TrainingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    share: bool


class ChannelOut(BaseModel):
    """También valida lo leído de la BD."""
    id: int = Field(ge=1)
    yt_channel_id: str = Field(min_length=1)
    handle: str = Field(min_length=2)
    title: str = Field(min_length=1)
    niche_id: int | None = None
    language: str | None = None
    share_for_training: bool = True


class ChannelCreatedOut(ChannelOut):
    suggested_niche_id: int | None = None
    videos_loaded: int


def list_by_user(conn, user_id: int) -> list:
    return conn.execute(f"SELECT {COLS} FROM channels WHERE user_id = %s ORDER BY id", (user_id,)).fetchall()


def get_owned(conn, channel_id: int, user_id: int):
    """El canal solo si es de ese usuario: cambiar el id en la URL no da acceso a canales ajenos."""
    return conn.execute(f"SELECT {COLS} FROM channels WHERE id = %s AND user_id = %s", (channel_id, user_id)).fetchone()


def count_by_user(conn, user_id: int) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM channels WHERE user_id = %s", (user_id,)).fetchone()["n"]