"""scripts/hot_evergreen.py: patrones pareados dentro del canal, temas hot/atemporales y calibración contra el azar."""
import numpy as np
import pandas as pd

from scripts.hot_evergreen import analizar_patrones, analizar_temas, flags_de_patrones


def _ds(seed=0, n_ch=50, estructura=True):
    """Dataset ya con las columnas de build_dataset. Con estructura: 'eterno' rinde siempre, 'momento' solo en lo
    reciente (y aparece más ahí), 'solocanal' solo existe en un canal, y 'top 10' ayuda dentro de cada canal."""
    rng = np.random.default_rng(seed)
    fill = [f"p{i}" for i in range(60)]
    rows = []
    for ch in range(n_ch):
        size = rng.normal(0, 1)
        for k in range(int(rng.integers(40, 90))):
            age = rng.uniform(3, 180)
            words = list(rng.choice(fill, 4))
            boost = 0.0
            if estructura:
                if rng.random() < 0.12:
                    words.append("eterno"); boost += 0.7
                if rng.random() < (0.25 if age < 45 else 0.03):
                    words.append("momento"); boost += 1.0 if age < 45 else 0.0
                if ch == 0 and rng.random() < 0.3:
                    words.append("solocanal"); boost += 1.5
                if rng.random() < 0.15:
                    words.insert(0, "top 10"); boost += 0.5
            lr = size * 0.0 + boost + rng.normal(0, 0.6)
            ratio = float(np.exp(lr))
            rows.append(dict(channel_id=ch, niche_id=1, title=" ".join(words), age_days=age, ratio=ratio, y=int(ratio >= 1.5)))
    return pd.DataFrame(rows)


def test_patrones_detecta_top_n_y_no_inventa_otros():
    ds = _ds()
    f = flags_de_patrones(ds)
    assert f["TOP N / N mejores"].sum() > 100
    filas = pd.DataFrame(analizar_patrones(ds, "demo")).set_index("patron")
    assert filas.loc["TOP N / N mejores", "clase"].startswith("ATEMPORAL")
    assert filas.loc["TOP N / N mejores", "efecto"] > 1.3
    sin = pd.DataFrame(analizar_patrones(_ds(estructura=False), "azar"))
    n_falsos = 0 if sin.empty else int(sin["clase"].str.startswith("ATEMPORAL").sum())
    assert n_falsos <= 1                                                   # con 99% de confianza, casi nunca por azar


def test_temas_hot_y_atemporales_y_calibracion():
    tabla, rs = analizar_temas(_ds(), n_null=10)
    clases = dict(zip(tabla["termino"], tabla["clase"]))
    assert clases.get("momento") == "HOT"
    assert clases.get("eterno") == "ATEMPORAL"
    assert "solocanal" not in clases                                       # dominado por un solo canal
    assert rs["hot"] >= 1 and rs["atemporal"] >= 1


def test_sin_estructura_no_supera_al_azar():
    tabla, rs = analizar_temas(_ds(estructura=False), n_null=15)
    assert rs["hot"] <= rs["hot_azar_p95"] + 2
    assert rs["atemporal"] <= rs["atemporal_azar_p95"] + 2