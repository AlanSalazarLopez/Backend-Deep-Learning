import numpy as np
import pandas as pd
import pytest

from ml import service
from ml.dataset import build_dataset, clean_videos
from synth import make_title


def make_df(n_channels=60, per=40, seed=0):
    rng = np.random.default_rng(seed)
    fetched = pd.Timestamp("2026-11-10", tz="UTC")
    rows, vid = [], 0
    for ch in range(n_channels):
        scale = 10 ** rng.uniform(2, 5)
        for _ in range(per):
            age = rng.uniform(3, 90)
            title, g, b = make_title(rng)
            views = scale * (3.0 if g else 1.0) * (0.5 if b else 1.0) * rng.lognormal(0, 0.5) * (1 + 20 / (age + 2)) * age ** 0.3
            vid += 1
            rows.append(dict(channel_id=ch, niche_id=1 + ch % 2, language="es", yt_video_id=f"v{vid}", title=title,
                             published_at=fetched - pd.Timedelta(days=age), duration_s=int(rng.integers(30, 1500)),
                             views=int(views), is_short=False, fetched_at=fetched))
    return pd.DataFrame(rows)


def test_clean_excludes_invalid_rows():
    df = make_df(2, 10)
    df.loc[0, "views"] = -1
    df.loc[1, "title"] = "  "
    df.loc[2, "duration_s"] = 0
    df.loc[3, "published_at"] = df.loc[3, "fetched_at"] + pd.Timedelta(days=1)
    assert len(clean_videos(df)) == len(df) - 4


def test_label_compares_same_age_bin_and_language_filter():
    df = make_df(10, 30)
    ds = build_dataset(df)
    assert ds["age_days"].between(3, 90).all() and set(ds["y"].unique()) <= {0, 1}
    assert (ds["baseline"] > 0).all()
    df2 = df.copy(); df2["language"] = "en"
    assert build_dataset(df2).empty


def test_recency_weights_and_gray_zone():
    ds = build_dataset(make_df(10, 30), {"label": {"gray_zone": {"win": 2.0, "lose": 0.8}}})
    young, old = ds[ds.age_days < 10].weight.mean(), ds[ds.age_days > 60].weight.mean()
    assert young > 4 * old
    assert (~ds.train_ok).any() and ds[~ds.train_ok].ratio.between(0.8, 2.0, inclusive="neither").all()


def test_train_predict_roundtrip_and_metrics():
    df = make_df()
    res = service.train(df, {"features": {"min_df": 3}})
    m = res.metrics
    assert m["auc_mean"] > 0.65 and m["auc_mean"] > m["format_only_auc"] > 0.5 and m["lift_at_10"] > 1.3
    assert m["ablation"]["text_only"] > m["ablation"]["format_only"]
    model = service.load_model(res.artifact)
    kw = dict(duration_s=600, publish_hour=18, publish_weekday=4, niche_id=1)
    good = service.predict(model, title="Truco gratis increible", **kw)
    bad = service.predict(model, title="Vlog parte resumen semana", **kw)
    assert good.score > bad.score and 0 <= good.score <= 100 and 0 <= good.probability <= 1
    again = service.predict(service.load_model(res.artifact), title="Truco gratis increible", **kw)
    assert again == good                                  # el artefacto serializado predice igual


def test_shuffled_labels_give_chance_level():
    df = make_df()
    rng = np.random.default_rng(1)
    df["views"] = rng.permutation(df["views"].to_numpy())  # rompe la relación título -> vistas
    res = service.train(df, {"features": {"min_df": 3}})
    assert res.metrics["auc_mean"] < 0.58                  # revisión de fuga: sin señal, ~0.50


def test_not_enough_data():
    with pytest.raises(service.NotEnoughData):
        service.train(make_df(3, 10))


def test_backup_toggles_run():
    df = make_df(30, 30)
    for override in ({"features": {"min_df": 3, "niche_prefix": True}},
                     {"features": {"min_df": 3, "char_ngrams": True}},
                     {"label": {"mode": "percentile"}, "features": {"min_df": 3}},
                     {"model": {"penalty": "l1"}, "features": {"min_df": 3}}):
        assert service.train(df, override).metrics["auc_mean"] > 0.55


def test_l1_really_sparsifies():
    import joblib, io
    res = service.train(make_df(30, 30), {"model": {"penalty": "l1", "C": 0.1}, "features": {"min_df": 3}})
    clf = joblib.load(io.BytesIO(res.artifact))["pipeline"].named_steps["clf"]
    assert (clf.coef_ == 0).mean() > 0.3
