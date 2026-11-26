"""Pruebas de scripts/run_experiments.py (utilidades) y de la penalización L1 entre versiones de scikit-learn."""
import io

import joblib
import numpy as np
import pandas as pd

from ml import service
from ml.config import DEFAULT_CFG, merge_cfg
from scripts.run_experiments import cfg_diff, deep_merge, semaforo, shuffle_views_within_channel


def _df(n_ch=6, per=10):
    rng = np.random.default_rng(0)
    rows = []
    for ch in range(n_ch):
        for k in range(per):
            rows.append(dict(channel_id=ch, views=int(rng.integers(100, 10_000)) * (ch + 1), title=f"t{ch}_{k}"))
    return pd.DataFrame(rows)


def test_cfg_diff_solo_deja_lo_que_cambia():
    cfg = merge_cfg({"features": {"min_df": 3}, "weights": {"half_life_days": None}, "data": {"niche_ids": [1]}})
    assert cfg_diff(cfg) == {"features": {"min_df": 3}, "weights": {"half_life_days": None}, "data": {"niche_ids": [1]}}
    assert cfg_diff(merge_cfg()) == {}


def test_deep_merge_no_modifica_el_original():
    base = {"label": {"theta": 1.5, "mode": "threshold"}}
    out = deep_merge(base, {"label": {"theta": 2.0}})
    assert out["label"] == {"theta": 2.0, "mode": "threshold"} and base["label"]["theta"] == 1.5


def test_barajar_vistas_conserva_el_nivel_de_cada_canal():
    df = _df()
    sh = shuffle_views_within_channel(df, seed=1)
    for ch, g in df.groupby("channel_id"):
        assert sorted(g["views"]) == sorted(sh[sh["channel_id"] == ch]["views"])   # mismas vistas, dentro del mismo canal
    assert (sh["views"].to_numpy() != df["views"].to_numpy()).any()                # pero en otro orden
    assert (sh["title"] == df["title"]).all()


def test_semaforo():
    assert semaforo(0.63, 1.5).startswith("VERDE")
    assert semaforo(0.57, 1.5).startswith("AMARILLO")
    assert semaforo(0.52, 1.1).startswith("ROJO")


def test_l1_deja_ceros_en_cualquier_version_de_sklearn():
    from test_ml import make_df  # noqa: PLC0415
    res = service.train(make_df(30, 30), {"model": {"penalty": "l1", "C": 0.1}, "features": {"min_df": 3}})
    clf = joblib.load(io.BytesIO(res.artifact))["pipeline"].named_steps["clf"]
    assert (clf.coef_ == 0).mean() > 0.3


def test_sin_peso_y_con_peso_entrenan():
    from test_ml import make_df  # noqa: PLC0415
    df = make_df(30, 30)
    for hl in (None, 60):
        res = service.train(df, {"weights": {"half_life_days": hl}, "features": {"min_df": 3}})
        assert res.metrics["auc_mean"] > 0.55
    assert DEFAULT_CFG["weights"]["half_life_days"] == 21        # el valor de fábrica no cambia sin tabla con datos reales


def _textos_con_terminos_de_un_canal():
    rng = np.random.default_rng(0)
    rows = []
    for ch in range(8):
        for k in range(12):
            comun = "comun" if k % 2 == 0 and ch < 6 else "otro"
            propio = "zzpropio" if ch == 0 else "algo"
            rows.append(dict(channel_id=ch, text=f"{comun} {propio} palabra{rng.integers(0, 4)}"))
    return pd.DataFrame(rows)


def test_vocabulario_por_canales_quita_terminos_de_un_solo_canal():
    from ml.features import channel_vocabulary
    d = _textos_con_terminos_de_un_canal()
    assert channel_vocabulary(d["text"], d["channel_id"], merge_cfg()) is None            # apagado por defecto
    vocab = channel_vocabulary(d["text"], d["channel_id"], merge_cfg({"features": {"min_channels": 3, "min_df": 2}}))
    assert "comun" in vocab and "zzpropio" not in vocab
    assert vocab == sorted(vocab)


def test_train_con_min_channels_guarda_y_predice():
    from test_ml import make_df
    res = service.train(make_df(30, 30), {"features": {"min_df": 3, "min_channels": 4}})
    model = service.load_model(res.artifact)
    kw = dict(duration_s=600, publish_hour=18, publish_weekday=4, niche_id=1)
    a = service.predict(model, title="Truco gratis increible", **kw)
    assert a == service.predict(service.load_model(res.artifact), title="Truco gratis increible", **kw)
    assert all(tt["term"] in set(model.terms) for tt in a.top_terms)
    assert DEFAULT_CFG["features"]["min_channels"] is None       # el valor de fábrica no cambia sin tabla con datos reales


def test_auc_dentro_de_canal_ignora_diferencias_entre_canales():
    from ml.service import _within_channel_auc
    # canal A: y=1 casi siempre; canal B: casi nunca. Las probabilidades separan bien AL CANAL pero no dentro de cada uno.
    y = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1])
    g = np.array(["A"] * 8 + ["B"] * 8)
    p = np.array([0.9] * 8 + [0.1] * 8)
    assert _within_channel_auc(y, p, g, min_n=8) == 0.5   # sin orden interno, dentro de cada canal queda en 0.5
    from sklearn.metrics import roc_auc_score
    assert roc_auc_score(y, p) > 0.8                       # el global sí se infla por la diferencia entre canales


def test_train_reporta_auc_dentro_de_canal():
    from test_ml import make_df
    m = service.train(make_df(30, 30), {"features": {"min_df": 3}}).metrics
    assert 0.0 <= m["auc_within_channel"] <= 1.0 and m["auc_within_std"] >= 0


def test_backtest_de_temas_distingue_persistencia():
    from scripts.backtest_topics import backtest_niche
    rng = np.random.default_rng(0)
    rows = []
    for persist in (True, False):
        for ch in range(40):
            for k in range(60):
                age, hot = rng.uniform(4, 175), rng.random() < 0.25
                title = " ".join(([f"tema{rng.integers(0, 4)}"] if hot else []) + [f"p{i}" for i in rng.integers(0, 60, 4)])
                rows.append(dict(persist=persist, channel_id=ch + (0 if persist else 100), age_days=age, title=title,
                                 y=int(rng.random() < (0.55 if (hot and persist) else 0.25))))
    d = pd.DataFrame(rows)
    si = backtest_niche(d[d.persist], cutoff=60, k=4, min_videos=5, min_channels=3, draws=100)
    no = backtest_niche(d[~d.persist], cutoff=60, k=4, min_videos=5, min_channels=3, draws=100)
    assert si["lift_top"] > si["azar_p95"] and si["lift_top"] > 1.3
    assert no["lift_top"] <= no["azar_p95"]