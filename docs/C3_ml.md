# C3. Contrato de ML — Proyecto 3er parcial

El paquete `ml/` es **Python puro**: no importa FastAPI ni la base de datos. Recibe DataFrames y devuelve objetos simples. Así se puede desarrollar y probar sin el backend, y el backend lo usa como una caja negra.

Parámetros por defecto y valores a probar: ver `PLAN_proyecto.md`, Parte 2.

## 1. Entrada: DataFrame `videos`

Mismas columnas que la tabla `videos` (C1) más `niche_id`, `channel_id` y `language` (del canal):

`channel_id, niche_id, language, yt_video_id, title, published_at, duration_s, views, yt_category_id, is_short, fetched_at`

**Limpieza al leer (obligatoria):** `build_dataset` excluye filas con `title` vacío, `views < 0`, `duration_s <= 0`, `published_at` nulo o posterior a `fetched_at`. Solo se usan canales cuyo `language` sea igual a `cfg.data.language` (por defecto `"es"`).
**Edad:** `age_days = (fetched_at - published_at)` en días (decimal). Nunca se mide contra la fecha de hoy.

## 2. Configuración (`cfg`, JSON; se guarda en `model_runs.config`)

```json
{
  "data": {"language": "es", "timezone": "America/Mexico_City"},
  "label": {
    "version": 1,
    "min_age_days": 3,
    "max_age_days": 90,
    "age_bins": [3, 8, 31, 91],
    "min_videos_in_bin": 3,
    "theta": 1.5,
    "mode": "threshold",
    "gray_zone": null
  },
  "weights": {"half_life_days": 21},
  "features": {"ngram_range": [1, 2], "min_df": 5, "max_features": 20000, "char_ngrams": false, "niche_prefix": false},
  "model": {"type": "logreg", "C": 1.0, "class_weight": null, "penalty": "l2"},
  "seed": 42
}
```
- `mode`: `"threshold"` (`ratio >= theta`) o `"percentile"` (top 25 % dentro de nicho × franja).
- `gray_zone`: `null` o `{"win": 2.0, "lose": 0.8}` (Respaldo 1: entrenar sin la zona gris; evaluar siempre en todos).
- `age_bins` son los bordes de las franjas (`[3,8)`, `[8,31)`, `[31,91)`).

## 3. Dataset (`build_dataset(videos_df, cfg) -> DataFrame`)

| Columna | Significado |
|---|---|
| `yt_video_id`, `channel_id`, `niche_id` | Identificadores. `channel_id` es el grupo para separar train/test; **nunca** es una variable del modelo |
| `title`, `duration_s`, `is_short`, `publish_hour`, `publish_weekday` | Variables de entrada (hora y día se sacan de `published_at` convertido a `cfg.data.timezone`; weekday 0 = lunes) |
| `views` | Solo informativa (se muestra en el resumen); **no** es variable del modelo |
| `age_days`, `velocity` | `velocity = views / max(age_days, 1)` |
| `baseline` | Mediana de `velocity` de los **otros** videos del canal en la misma franja; si hay menos de `min_videos_in_bin`, mediana del nicho en esa franja |
| `ratio` | `velocity / baseline` |
| `y` | 1 o 0 según `mode`, `theta` y `gray_zone` |
| `weight` | `0.5 ** (age_days / half_life_days)` (se usa como `sample_weight`) |

**Prohibido como variable:** `channel_id`, `views`, `likes`, `comments`, `velocity`, `baseline`, `ratio`, `age_days` (fuga de información).

## 4. Funciones públicas

```python
# ml/service.py
@dataclass
class TrainResult:
    artifact: bytes        # modelo serializado (ver sección 6); va a model_runs.artifact
    metrics: dict          # ver sección 5; va a model_runs.metrics
    config: dict           # cfg usado, completo; va a model_runs.config
    n_videos: int
    n_channels: int

def train(videos_df: pd.DataFrame, cfg: dict) -> TrainResult: ...
    # build_dataset + separación por canal + entrenamiento final + métricas.
    # Determinista: mismo cfg y mismos datos -> mismo resultado.

def load_model(artifact: bytes) -> "LoadedModel": ...

@dataclass
class PredictResult:
    probability: float                # 0..1
    score: float                      # 0..100, percentil de la probabilidad dentro de reference[niche_id]
    top_terms: list[dict]             # [{"term": str, "weight": float}], máx. 5, los que más empujan la predicción

def predict(model: "LoadedModel", *, title: str, duration_s: int,
            publish_hour: int, publish_weekday: int, niche_id: int) -> PredictResult: ...

def topic_ranking(videos_df: pd.DataFrame, niche_id: int, cfg: dict, limit: int = 10) -> list[dict]: ...
    # [{"term": str, "lift": float, "win_rate": float, "n_videos": int}]
```

**`topic_ranking`:** toma los videos válidos del nicho con edad entre `min_age_days` y `max_age_days`, extrae palabras y bigramas (sin stopwords en español e inglés), y para cada término con `n_videos >= 5` calcula
`win_rate = Σ(weight·y) / Σ(weight)` sobre los videos que lo contienen, y `lift = win_rate / base_rate_ponderada_del_nicho`. El `win_rate` se suaviza con 8 videos "virtuales" que tienen la tasa base del nicho, para que un término con 5 videos no encabece el ranking por azar. Ordena por `lift` descendente. No depende del clasificador, así que sirve como plan de emergencia.

## 5. Métricas (`metrics`, JSON; se guarda en `model_runs.metrics`)

```json
{
  "auc_mean": 0.63, "auc_std": 0.02, "pr_auc": 0.38,
  "precision_at_10": 0.41, "lift_at_10": 1.5, "base_rate": 0.27,
  "baseline_auc": 0.50, "format_only_auc": 0.55,
  "ablation": {"text_only": 0.61, "format_only": 0.55, "both": 0.63},
  "temporal_auc": null,
  "n_train_channels": 168, "n_test_channels": 42, "seeds": [1, 2, 3, 4, 5],
  "top_positive_terms": [["gratis", 0.8]], "top_negative_terms": [["parte 2", -0.6]]
}
```
Calculadas **solo sobre canales no vistos** (separación por canal). `temporal_auc` es opcional.

## 6. Artefacto del modelo

`artifact` = `joblib.dump` a bytes de:
```python
{
  "pipeline": <sklearn Pipeline: preprocesamiento + clasificador>,
  "config": cfg,
  "feature_version": "v1",
  "reference": {niche_id: [probabilidades ordenadas de los videos del nicho]},  # para calcular el percentil
  "sklearn_version": sklearn.__version__
}
```
- Se guarda en la BD (`model_runs.artifact`), no en disco.
- `load_model` verifica `sklearn_version`; si no coincide con la instalada, lanza un error claro.
- `scikit-learn`, `numpy`, `pandas` y `joblib` van **fijados** en `requirements.txt`, con la misma versión en entrenamiento y servidor.

## 7. Ingesta (T1 → T2)

```
python -m scripts.ingest --channels channels_seed.csv [--refresh]
```
- `channels_seed.csv`: columnas `handle,niche_slug` (20–30 canales por nicho **después** de los filtros de abajo, mezclando tamaños). Lo genera `scripts/discover_channels.py` (una sola vez); puede traer columnas extra, que se ignoran.
- Por canal: `channels.list` → lista de subidas (`playlistItems.list`) → `videos.list` por lotes de 50. **Nunca `search.list` para cargar videos** (100 unidades por llamada; confirmar la cuota vigente en la documentación de YouTube). Solo se usa, una vez, para descubrir canales semilla (ver `PLAN_proyecto.md`, Parte 5, P2).
- Hace *upsert* en `channels` (`source='seed'`) y `videos`; `--refresh` vuelve a leer las vistas y actualiza `fetched_at`.
- Calcula `is_short = duration_s <= 60`. Hasta 50 videos recientes por canal.
- Calcula `channels.language` con `langdetect` sobre los títulos de sus videos (idioma mayoritario).
- Marca como descartados los canales con menos de 15 videos válidos en la ventana de 3 a 90 días, y los canales donde menos del 50 % de los videos tienen la categoría de YouTube del nicho (umbral ajustable).
- Si la API responde con error de cuota, termina limpio con un mensaje y sin dejar datos a medias.

## 8. Pruebas mínimas del paquete `ml/`

1. `build_dataset` excluye filas inválidas.
2. La etiqueta usa la misma franja de edad (un video de 4 días nunca se compara contra uno de 60).
3. Entrenar con etiquetas mezcladas da AUC cercano a 0.50 (revisión de fuga).
4. `predict` devuelve `score` entre 0 y 100 y `probability` entre 0 y 1.
5. `load_model(train(...).artifact)` da las mismas predicciones que el modelo original.

## 9. Entrenamiento desde la BD (`scripts/train_model.py`)

```
python -m scripts.train_model [--config cfg.json] [--activate]
```
- Lee de la BD los videos y canales válidos (de clientes y semilla), los pasa por `ml.service.train` y guarda el resultado en `model_runs` (`trained_by` queda `NULL`).
- Con `--activate`, en una sola transacción desactiva el modelo anterior y activa el nuevo (`is_active`).
- Conserva los últimos 3 modelos y borra los anteriores que no estén activos (el artefacto ocupa espacio en la BD).
- Sin `--config` usa los valores por defecto de la sección 2.
- Cuando entran datos nuevos de clientes, se vuelve a correr el script. Si hay tiempo, `POST /admin/retrain` (tarea T14 del plan) solo envuelve este mismo código.

## 10. Estado de implementación

- **Hecho y probado** (con datos sintéticos que tienen señal real): `build_dataset`, `train` (evaluación por canal con 5 semillas, ablación, AUC temporal, referencia de percentiles fuera de muestra), `load_model`, `predict`, `topic_ranking`.
- **Interruptores de los respaldos:** el Respaldo 1 (zona gris: `label.gray_zone`) y el Respaldo 3 (`features.niche_prefix`) están implementados, además de `label.mode = "percentile"`, `features.char_ngrams` y `model.penalty = "l1"`.
- **No implementados:** Respaldo 2 (ranking con Ridge sobre `log(ratio)`) y Respaldo 4 (embeddings o temas con KMeans). Se agregan solo si los experimentos con datos reales los piden.
- **Pendiente con datos reales:** los valores por defecto (θ, franjas, vida media) son puntos de partida; los experimentos de `PLAN_proyecto.md`, sección 2.6, se hacen cuando exista `channels_seed.csv` ingestado.
