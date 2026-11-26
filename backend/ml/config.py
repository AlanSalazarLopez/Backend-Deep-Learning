"""Configuración por defecto del modelo (docs/C3_ml.md, sección 2)."""
import copy

DEFAULT_CFG = {
    "data": {"language": "es", "timezone": "America/Mexico_City",
             "min_duration_s": 181,    # 3 min: debajo de esto se consideran Shorts y no se usan
             "max_duration_s": 7200,   # 2 h: igual que el máximo de /predict
             "niche_ids": None},       # None = todos los nichos; o una lista de ids para entrenar solo con esos
    "label": {
        "version": 1,
        "min_age_days": 3,
        "max_age_days": 180,
        "age_bins": [3, 8, 31, 91, 181],
        "min_videos_in_bin": 3,
        # "age_adjusted": línea base del canal con todos sus videos, ajustando por edad (recomendado).
        # "bins": línea base por franja de edad (método anterior; age_bins solo se usa aquí y en el diagnóstico).
        "method": "age_adjusted",
        "min_videos_in_channel": 5,   # age_adjusted: otros videos que necesita el canal para tener línea base propia
        "age_curve_bins": 12,         # age_adjusted: puntos con los que se mide la curva de edad
        "theta": 1.5,
        "mode": "threshold",      # "threshold" | "percentile"
        "gray_zone": None,        # None | {"win": 2.0, "lose": 0.8}
        # True: al entrenar solo se usan videos cuya línea base salió de SU canal. Si salió del nicho o global,
        # la etiqueta mediría el tamaño del canal y no la calidad del título (ver baseline_src en dataset.py).
        "require_channel_baseline": True,
    },
    "weights": {"half_life_days": 21},
    "features": {
        "ngram_range": [1, 2],
        "min_df": 5,
        "max_features": 20000,
        "char_ngrams": False,
        "niche_prefix": False,
        # None = sin filtro. Un número k: el vocabulario de texto solo conserva términos que aparecen en al menos k
        # CANALES distintos del entrenamiento. min_df cuenta videos, y un término que sale 5 veces en un solo canal
        # (nombre de un juego o de una serie) entra igual pero no generaliza a canales nuevos.
        "min_channels": None,
    },
    "model": {"type": "logreg", "C": 1.0, "class_weight": None, "penalty": "l2"},
    "seed": 42,
}

FEATURE_VERSION = "v1"


def merge_cfg(override: dict | None = None) -> dict:
    """Mezcla (en profundidad) una configuración parcial sobre la de por defecto."""
    cfg = copy.deepcopy(DEFAULT_CFG)

    def _merge(base, extra):
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _merge(base[k], v)
            else:
                base[k] = v

    if override:
        _merge(cfg, override)
    return cfg