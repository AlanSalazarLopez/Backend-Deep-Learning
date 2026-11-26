"""Pruebas con un PostgreSQL real y local (pgserver) y un YouTube simulado."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pgserver  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

_srv = pgserver.get_server(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = _srv.get_uri()
os.environ["JWT_SECRET"] = "secreto-de-pruebas-" + "x" * 32
os.environ["YOUTUBE_API_KEY"] = "clave-falsa"

from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
from controllers import channels as channels_ctrl  # noqa: E402
from main import app  # noqa: E402
from models import user as user_model  # noqa: E402
from services.youtube_client import ChannelInfo, VideoInfo, YouTubeError  # noqa: E402

SCHEMA = (BACKEND.parent / "docs" / "C1_esquema_bd.sql").read_text(encoding="utf-8")
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as _c:
    _c.execute(SCHEMA)


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


class FakeYouTube:
    """Simula la API de YouTube. 'known' mapea handle -> número de videos."""
    def __init__(self):
        self.known = {"@canalgrande": 30, "@canalchico": 4}
        self.fail = False

    def resolve_channel(self, handle):
        if self.fail:
            raise YouTubeError("YouTube no responde")
        if handle not in self.known:
            return None
        return ChannelInfo(f"UCfake{handle[1:]}", handle, f"Título {handle}", f"UUfake{handle[1:]}")

    def recent_videos(self, playlist_id, max_videos=50):
        rng = np.random.default_rng(abs(hash(playlist_id)) % 1000)
        n = self.known["@" + playlist_id.removeprefix("UUfake")]
        now = datetime.now(timezone.utc)
        out = []
        for i in range(n):
            out.append(VideoInfo(f"{playlist_id}-{i}", f"Video {int(rng.integers(1000))} de prueba para el canal número {i}",
                                 now - timedelta(days=float(rng.uniform(4, 80))), 600, int(rng.integers(500, 90000)),
                                 10, 2, 20, audio_language="es"))
        return out


@pytest.fixture(scope="session")
def fake_yt():
    return FakeYouTube()


@pytest.fixture(scope="session")
def client(fake_yt):
    app.dependency_overrides[channels_ctrl.get_youtube] = lambda: fake_yt
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean(fake_yt):
    with connect() as c:
        c.execute("TRUNCATE predictions, model_runs, videos, channels, users RESTART IDENTITY CASCADE")
        c.commit()
    fake_yt.fail = False
    from services import model_store
    model_store._cache.update(run_id=None, model=None)


@pytest.fixture
def conn():
    with connect() as c:
        yield c


def make_user(conn, username, password="Clave1234", role="client", name="Usuario Prueba"):
    row = user_model.create(conn, username, name, password, role)
    conn.commit()
    return row


def login(client, username, password="Clave1234"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}