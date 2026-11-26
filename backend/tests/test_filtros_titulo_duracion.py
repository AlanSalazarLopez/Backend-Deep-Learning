"""Pruebas del filtro de duración (181 a 7200 s) y de la limpieza de títulos (hashtags y "Parte N")."""
import numpy as np
import pandas as pd
import pytest

from ml.config import merge_cfg
from ml.dataset import build_dataset, select_training_rows
from ml.service import load_model, predict, train
from ml.text import clean_title


BINS = {"label": {"method": "bins"}}   # método anterior: el único que usa el respaldo de nicho


def _videos(n_channels=30, per_channel=40, seed=0) -> pd.DataFrame:
    """Videos sintéticos con señal real (palabras 'buenas' rinden más) y con ruido: Shorts, streams, hashtags."""
    rng = np.random.default_rng(seed)
    good_w = ["gratis", "secreto", "increible", "nuevo"]
    bad_w = ["resumen", "entrevista", "vlog", "directo"]
    filler = ["juego", "tutorial", "mundo", "historia", "review", "camino", "ciudad", "truco", "guia", "mejor"]
    fetched = pd.Timestamp("2026-11-15", tz="UTC")
    rows = []
    for ch in range(n_channels):
        for k in range(per_channel):
            good = rng.random() < 0.3
            words = list(rng.choice(good_w if good else bad_w, 1)) + list(rng.choice(filler, 3))
            title = " ".join(words)
            r = rng.random()
            if r < 0.3:
                title += f" Parte {rng.integers(1, 9)}"
            if r > 0.6:
                title += " #gamer #historia"
            dur = int(rng.choice([45, 80, 150, 600, 1500, 5000, 20000], p=[.15, .1, .05, .3, .2, .15, .05]))
            age = rng.uniform(4, 85)
            views = int(1000 * (1 + ch % 5) * age * (2.5 if good else 0.8) * rng.lognormal(0, 0.3))
            rows.append(dict(channel_id=ch, niche_id=1 + ch % 2, language="es", yt_video_id=f"v{ch}_{k}",
                             title=title, published_at=fetched - pd.Timedelta(days=age), duration_s=dur,
                             views=views, yt_category_id=20, is_short=dur <= 60, fetched_at=fetched))
    return pd.DataFrame(rows)


@pytest.mark.parametrize("raw, esperado", [
    ("ZELDA Gameplay Parte 2 | PS5 #historia #gamer", "ZELDA Gameplay | PS5"),
    ("Cap. 12 - La batalla final", "- La batalla final"),
    ("Probé 5 IAs gratis", "Probé 5 IAs gratis"),      # los números sueltos no se tocan
    ("#solo #hashtags", ""),
    ("Parte 2", ""),
])
def test_clean_title(raw, esperado):
    assert clean_title(raw) == esperado


def test_build_dataset_solo_duraciones_entre_181_y_7200():
    df = _videos()
    ds = build_dataset(df)
    assert 0 < len(ds) < len(df)
    assert ds["duration_s"].between(181, 7200).all()
    assert not ds["title"].str.contains("#").any()
    assert not ds["title"].str.contains(r"(?i)\bparte\s*\d").any()


def test_los_limites_de_duracion_se_pueden_cambiar_en_cfg():
    df = _videos()
    ds = build_dataset(df, {"data": {"min_duration_s": 61, "max_duration_s": 700}})
    assert ds["duration_s"].between(61, 700).all()


def test_predict_ignora_parte_n_y_hashtags():
    model = load_model(train(_videos()).artifact)
    kw = dict(duration_s=600, publish_hour=18, publish_weekday=4, niche_id=1)
    a = predict(model, title="gratis juego tutorial", **kw)
    b = predict(model, title="gratis juego tutorial Parte 2 #gamer #historia", **kw)
    assert a.probability == b.probability
    assert a.top_terms == b.top_terms


def test_dataset_marca_el_origen_de_la_linea_base():
    ds = build_dataset(_videos(), BINS)
    assert set(ds["baseline_src"]) <= {"canal", "nicho", "global"}
    assert (ds["baseline_src"] == "canal").any()
    assert (ds["baseline_src"] != "canal").any()          # la franja más joven casi siempre cae al respaldo


def test_select_training_rows_solo_deja_linea_base_de_canal():
    ds = build_dataset(_videos(), BINS)
    train, quitados = select_training_rows(ds, BINS)
    assert (train["baseline_src"] == "canal").all()
    assert quitados == len(ds) - len(train) > 0
    todo, cero = select_training_rows(ds, {"label": {"method": "bins", "require_channel_baseline": False}})
    assert len(todo) == len(ds) and cero == 0


def test_train_quita_videos_sin_linea_base_de_su_canal():
    df = _videos()
    con = train(df, BINS)
    sin = train(df, {"label": {"method": "bins", "require_channel_baseline": False}})
    assert con.metrics["n_dropped_no_channel_baseline"] > 0
    assert sin.metrics["n_dropped_no_channel_baseline"] == 0
    assert con.n_videos < sin.n_videos


def _videos_que_se_estancan(seed=3) -> pd.DataFrame:
    """Canales de distinta frecuencia cuyas vistas se estancan con la edad (velocidad ~ edad^-0.45)."""
    rng = np.random.default_rng(seed)
    fetched = pd.Timestamp("2026-11-15", tz="UTC")
    rows = []
    for ch in range(40):
        for k in range(int([14, 25, 40, 48][ch % 4])):
            age = rng.uniform(4, 175)
            good = rng.random() < 0.3
            views = int(3000 * (1 + ch % 5) * age ** 0.55 * (2.5 if good else 0.8) * rng.lognormal(0, 0.3))
            rows.append(dict(channel_id=ch, niche_id=1 + ch % 2, language="es", yt_video_id=f"s{ch}_{k}",
                             title=f"video {k} {ch}", published_at=fetched - pd.Timedelta(days=age),
                             duration_s=900, views=views, yt_category_id=20, is_short=False, fetched_at=fetched))
    return pd.DataFrame(rows)


def _rho_edad_ratio(ds) -> float:
    """Correlación media (Spearman) entre edad y ratio dentro de cada franja; ideal: cerca de 0."""
    base = ds[ds["baseline_src"] == "canal"]
    vals = [g["age_days"].corr(g["ratio"], method="spearman") for _, g in base.groupby("age_bin") if len(g) >= 30]
    return float(np.mean(vals))


def test_ajuste_por_edad_quita_la_tendencia_de_edad_y_usa_linea_base_de_canal():
    df = _videos_que_se_estancan()
    con_franjas = build_dataset(df, BINS)
    ajustado = build_dataset(df)                                   # método por defecto: age_adjusted
    assert _rho_edad_ratio(con_franjas) < -0.15                    # las franjas dejan la edad dentro de la etiqueta
    assert abs(_rho_edad_ratio(ajustado)) < 0.12                   # el ajuste la quita
    assert (ajustado["baseline_src"] == "canal").all()             # y todos los videos usan la línea base de su canal


def test_metodo_desconocido_da_error_claro():
    with pytest.raises(ValueError):
        build_dataset(_videos(), {"label": {"method": "otro"}})


def _videos_con_frecuencias_distintas(seed=11) -> pd.DataFrame:
    """Canales que publican cada 1 a 10 días: los rápidos solo cubren edades jóvenes y los lentos todo el rango."""
    rng = np.random.default_rng(seed)
    fetched = pd.Timestamp("2026-11-15", tz="UTC")
    rows = []
    for ch in range(60):
        dias, n = [(1, 50), (1.5, 50), (3, 50), (7, 26), (10, 18)][ch % 5]
        alpha = rng.normal(6, 1.2)                      # tamaño del canal
        for k in range(n):
            age = 3 + k * dias + rng.uniform(0, dias)
            if age > 180:
                continue
            good = rng.random() < 0.3
            lv = alpha - 0.45 * np.log(age) + (0.9 if good else 0.0) + rng.normal(0, 0.5)
            rows.append(dict(channel_id=ch, niche_id=1 + ch % 3, language="es", yt_video_id=f"f{ch}_{k}",
                             title=f"video {k} {ch}", published_at=fetched - pd.Timedelta(days=age), duration_s=900,
                             views=int(np.exp(lv) * age), yt_category_id=20, is_short=False, fetched_at=fetched))
    return pd.DataFrame(rows)


def test_ajuste_por_edad_funciona_con_canales_de_frecuencias_distintas():
    """Regresión: con un solo paso la curva mezclaba tipos de canal y los videos jóvenes salían 'mejores'."""
    ds = build_dataset(_videos_con_frecuencias_distintas())
    por_franja = ds.groupby("age_bin").agg(med=("ratio", "median"), y1=("y", "mean"))
    assert por_franja["med"].max() - por_franja["med"].min() < 0.15     # el nivel del ratio no cambia con la edad
    assert por_franja["y1"].max() - por_franja["y1"].min() < 0.10       # ni la tasa de y=1


def test_niche_ids_deja_solo_esos_nichos():
    ds = build_dataset(_videos(), {"data": {"niche_ids": [1]}})
    assert len(ds) > 0 and set(ds["niche_id"]) == {1}


def test_diagnostico_corre_sin_errores(capsys):
    from scripts.diagnostico_dataset import diagnose
    cfg = merge_cfg()
    diagnose(build_dataset(_videos(), cfg), cfg)
    salida = capsys.readouterr().out
    assert "se comparó" in salida and "Qué entra al entrenamiento" in salida


# --- esquema de /predict (ajusta el import si tu archivo no se llama models/prediction.py) ---
from pydantic import ValidationError  # noqa: E402
from models.prediction import PredictIn  # noqa: E402

_BASE = dict(niche_id=1, title="Probé 5 IAs gratis", duration_s=600, publish_hour=18)


@pytest.mark.parametrize("dur, valido", [(180, False), (181, True), (7200, True), (7201, False)])
def test_predictin_limites_de_duracion(dur, valido):
    if valido:
        assert PredictIn(**{**_BASE, "duration_s": dur}).duration_s == dur
    else:
        with pytest.raises(ValidationError):
            PredictIn(**{**_BASE, "duration_s": dur})


@pytest.mark.parametrize("titulo", ["#hola #gamer", "Parte 2"])
def test_predictin_rechaza_titulos_que_quedan_vacios(titulo):
    with pytest.raises(ValidationError):
        PredictIn(**{**_BASE, "title": titulo})