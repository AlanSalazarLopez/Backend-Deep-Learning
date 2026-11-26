"""Datos sintéticos para pruebas: títulos con palabras que suben o bajan las vistas."""
from datetime import datetime, timedelta, timezone

import numpy as np

GOOD = ["gratis", "secreto", "increible", "truco", "rapido"]
BAD = ["parte", "vlog", "update", "resumen", "semana"]
FILL = ["minecraft", "casa", "musica", "tutorial", "guitarra", "ciencia", "robot", "cocina", "viaje", "mundo",
        "historia", "juego"]


def make_title(rng, good=None, bad=None):
    words = list(rng.choice(FILL, 3))
    g = rng.random() < 0.3 if good is None else good
    b = rng.random() < 0.3 if bad is None else bad
    if g:
        words.append(str(rng.choice(GOOD)))
    if b:
        words.append(str(rng.choice(BAD)))
    rng.shuffle(words)
    return " ".join(words).capitalize(), g, b


def seed_training_data(conn, n_channels=60, per_channel=40, niche_ids=(1, 2), seed=0):
    """Inserta canales semilla y videos con señal real (las palabras GOOD suben las vistas)."""
    rng = np.random.default_rng(seed)
    now = datetime.now(timezone.utc)
    vid = 0
    for ch in range(n_channels):
        niche = niche_ids[ch % len(niche_ids)]
        scale = 10 ** rng.uniform(2, 5)
        row = conn.execute(
            "INSERT INTO channels (user_id, yt_channel_id, handle, title, niche_id, source, language, fetched_at) "
            "VALUES (NULL, %s, %s, %s, %s, 'seed', 'es', %s) RETURNING id",
            (f"UCseed{ch}", f"@seed{ch}", f"Seed {ch}", niche, now)).fetchone()
        for _ in range(per_channel):
            age = rng.uniform(3, 90)
            title, g, b = make_title(rng)
            mult = (3.0 if g else 1.0) * (0.5 if b else 1.0)
            views = int(scale * mult * rng.lognormal(0, 0.5) * (1 + 20 / (age + 2)) * age ** 0.3)
            vid += 1
            conn.execute(
                "INSERT INTO videos (channel_id, yt_video_id, title, published_at, duration_s, views, is_short, "
                "yt_category_id, fetched_at) VALUES (%s,%s,%s,%s,%s,%s,false,20,%s)",
                (row["id"], f"vs{vid}", title, now - timedelta(days=age), int(rng.integers(30, 1500)), views, now))
    conn.commit()
