# Proyecto 3er parcial — Plan por tareas y plan del modelo

App móvil para creadores de YouTube: dice qué ideas de título superan el rendimiento normal de un canal, por nicho.
Stack: **FastAPI + PostgreSQL (backend ya desplegado en Render/GitHub) + Flutter (MVVM)** + scikit-learn.

> Regla de este documento: cada tarea se puede trabajar en una sesión de IA **separada**.
> Cada sesión solo recibe (1) el contrato que consume, (2) la definición de la tarea y (3) el código de esa tarea.
> Nunca se pega el proyecto entero.

---

## Parte 1. Tareas independientes

### Contratos (lo único que se comparte entre tareas)

| Contrato | Archivo | Qué contiene |
|---|---|---|
| C1. Esquema de BD | `docs/C1_esquema_bd.sql` | Tablas `users`, `niches`, `channels`, `videos`, `predictions`, `model_runs` |
| C2. Contrato de API | `docs/C2_api.md` | Rutas, cuerpo de petición, respuestas, códigos de error, qué rol puede usarlas |
| C3. Contrato de ML | `docs/C3_ml.md` | Columnas de `videos`, funciones `train()`, `predict()`, `topic_ranking()` con firma y tipos |

Si un contrato cambia, se avisa en el chat del equipo y se actualiza **primero el contrato**, después el código.

### Archivos del proyecto (todos en `docs/`)

| Archivo | Para qué |
|---|---|
| `PLAN_proyecto.md` | Este documento: mapa de tareas, plan del modelo y decisiones |
| `REF_frontend_flutter.md` | Referencia del frontend (T8, T9, T10) |
| `C1_esquema_bd.sql` | Contrato C1: esquema de la base de datos |
| `C2_api.md` | Contrato C2: API |
| `C3_ml.md` | Contrato C3: paquete de ML e ingesta |

### Mapa de tareas

| # | Tarea | Entrada | Salida | Depende de | Contexto que necesita la IA |
|---|---|---|---|---|---|
| T0 | Contratos y repo | Este plan + PDF de la rúbrica | C1, C2, C3 en `docs/` + repo en GitHub | — | PDF + este MD |
| T1a | Descubrir canales semilla | Consultas por nicho + API Key de YouTube | `channels_seed.csv` | — | Nada: el script ya existe (`scripts/discover_channels.py`) |
| T1 | Ingesta de YouTube | `channels_seed.csv` | Tablas `channels` y `videos` | C1, C3, T1a | C1 + C3 (sección 7) + ejemplo de respuesta de la API de YouTube |
| T2 | Dataset y etiqueta | `videos` | `dataset.parquet` (features + `y`) | C3 | C3 + definición de etiqueta (Parte 2) |
| T3 | Entrenamiento y evaluación | `dataset.parquet` | `model.joblib` + `metrics.json` + `runs_log.csv` | T2 | C3 + Parte 2 |
| T4 | Servicio de predicción y entrenamiento desde la BD | `model.joblib` | `ml/service.py` (funciones puras + pruebas) y `scripts/train_model.py` | T3, C3 | C3 (secciones 4, 6 y 9) |
| T5 | Backend base: auth y roles | C1, C2 | Registro, login, Argon2id, roles en BD, promover a admin, validación de lectura | C1, C2 | C1 + C2 (secciones auth/usuarios) |
| T6 | Backend dominio | C1, C2 | Endpoints de canales, nichos, videos con control de dueño | T5 | C1 + C2 + `auth` (solo la dependencia de usuario actual) |
| T7 | Backend ML y panel | T4, T6 | `/predict`, `/niches/{id}/topics`, `/admin/stats`, `/admin/model` | T4, T6 | C2 + C3 |
| T8 | Frontend base | C2 | Login, sesión persistente, navegación, cliente HTTP (MVVM) | C2 | C2 (auth) + `REF_frontend_flutter.md` |
| T9 | Frontend cliente | C2 | Pantallas: @handle, nicho, comparación, predicción | T8 | C2 + `REF_frontend_flutter.md` |
| T10 | Frontend admin | C2 | Tabla, gráfica, promover a admin | T8 | C2 (admin) + `REF_frontend_flutter.md` |
| T11 | Pruebas de la rúbrica y datos de prueba | App funcionando | Checklist de las 8 pruebas con evidencia + script de datos de prueba (incluye registro inválido insertado a mano) | T7, T9, T10 | Solo la tabla de pruebas del PDF + C2 |
| T12 | Entrega | Todo | APK, README, cuentas de prueba, video de demo | T11 | — |
| T13 | **Tal vez:** Google Trends | CSV por nicho | Ajuste de demanda en la puntuación | T4 | C3 + Parte 4 |
| T14 | **Tal vez:** reentrenar desde la app | T4, T7 | `POST /admin/retrain` en segundo plano + botón en el panel admin | T7, T10 | C2 + C3 (sección 9) |

### Qué se puede hacer en paralelo (equipo de 3 a 4)

- **Persona A (backend):** T0 → T5 → T6 → T7
- **Persona B (modelo):** T1a → T1 → T2 → T3 → T4
- **Persona C (frontend):** T8 → T9 → T10
- **Persona D, si existe:** T11 desde temprano (escribe las pruebas mientras los demás construyen) y T12

Con una sola persona, el orden es: T0, T1a, T1, T2, T3, T4 (el modelo es el riesgo mayor), T5, T6, T7, T8, T9, T10, T11, T12.

### Plantilla para abrir una sesión de IA (copiar y pegar)

```
Tarea: [T#, nombre]
Contrato que consumes: [pega solo la sección necesaria de C1/C2/C3]
Qué debes entregar: [archivos exactos]
Reglas: no cambies los contratos; si algo del contrato no alcanza, dímelo antes de inventar.
Código existente relevante: [solo los archivos que esta tarea toca]
```

### Definición de "terminado" por tarea

Cada tarea termina cuando: (1) cumple su salida, (2) tiene al menos una prueba que corre sola, (3) no rompe el contrato.

---

## Parte 2. Plan del modelo

El modelo es lo que más pesa. Aquí está el protocolo completo. Los valores son **puntos de partida** para probar, no verdades.

### 2.1 Qué predice

Para un título de video (más duración y hora de publicación), la probabilidad de que ese video supere el rendimiento normal de su canal **a su misma edad**.

### 2.2 Datos de partida

| Parámetro | Valor inicial |
|---|---|
| Nichos | 8 |
| Idioma | Español (canales y títulos); el modelo entrena solo con `language = 'es'` |
| Canales por nicho | 20 a 30, mezclando tamaños chico, mediano y grande |
| Videos por canal | hasta 50 más recientes |
| Total esperado | 5,000 a 12,000 videos |
| Cuota de la API | Usa `channels.list` → `playlistItems.list` → `videos.list` (1 unidad c/u). **No uses `search.list` para cargar videos** (100 unidades por llamada; solo sirve, una vez, para descubrir canales semilla, ver Parte 5) |
| Ventana de edad usada | de 3 a 90 días |

Más canales es la palanca más confiable si los resultados salen flojos. Con unos 200 canales gastas cerca de 800 unidades de las 10,000 diarias.

### 2.3 Etiqueta (versión 1)

1. `edad_dias` = días desde la publicación. Se descartan videos con menos de 3 días.
2. `velocidad = vistas / edad_dias`.
3. Franjas de edad: `[3-7]`, `[8-30]`, `[31-90]`.
4. `base` = mediana de velocidad de los **otros** videos del mismo canal en esa misma franja. Si hay menos de 3, se usa la mediana del nicho en esa franja.
5. `ratio = velocidad / base`.
6. `y = 1` si `ratio >= θ`, y `0` en caso contrario.

### 2.4 Variables

| Grupo | Variables |
|---|---|
| Texto del título | TF-IDF de palabras (1 a 2 gramas), minúsculas, `strip_accents='unicode'` |
| Formato | `log1p(duración)`, `es_short` (60 s o menos), largo del título en caracteres y en palabras, tiene número, tiene "?", proporción de mayúsculas, tiene emoji |
| Publicación | hora (seno y coseno), día de la semana |
| Contexto | nicho (one-hot) |
| **Nunca** | id del canal, vistas, likes, comentarios, `ratio` (eso es fuga de información) |

### 2.5 Protocolo de evaluación

1. **Separación por canal.** 80 % de canales para entrenar y 20 % para probar (`GroupShuffleSplit`, semilla fija).
2. **Selección de hiperparámetros** solo con validación cruzada por canal dentro del 80 % (`GroupKFold`, k = 5). El 20 % de prueba se mira **una sola vez**, al final.
3. **Repite con 5 semillas distintas** y reporta promedio ± desviación.
4. **Prueba temporal (opcional, muy útil):** entrena con videos de 31 a 90 días y prueba con los de 3 a 30 días.
5. **Métricas:**
   - ROC-AUC (principal)
   - PR-AUC
   - Precisión en el 10 % superior (`precision@10%`)
   - Lift@10 % = `precision@10% / tasa_base`
6. **Contra qué comparar:** (a) moneda al azar (AUC 0.50), (b) modelo que siempre predice la clase mayoritaria, (c) modelo solo con variables de formato (sin texto).
7. **Ablación:** solo texto, solo formato, ambos. Sirve para explicar "qué variables usa el modelo".
8. **Revisión de fuga:** mezcla las etiquetas al azar y reentrena; el AUC debe caer a cerca de 0.50. Si no cae, hay fuga.

### 2.6 Búsqueda de valores (en este orden, uno a la vez)

Se prueba por orden de impacto. En cada paso se fija lo mejor y se pasa al siguiente. Todo se anota en `runs_log.csv`.

| Paso | Qué se prueba | Valores |
|---|---|---|
| 1. Etiqueta | Umbral θ | 1.3, 1.5, 2.0 y "percentil 75 dentro de nicho × franja" |
| 2. Etiqueta | Franjas de edad | 3 franjas (arriba) vs 5 franjas: `[3-5] [6-10] [11-20] [21-45] [46-90]` |
| 3. Texto | `min_df` | 3, 5, 10 |
| 3. Texto | `max_features` | 5,000 y 20,000 |
| 3. Texto | Tipo | palabras (1-2 gramas) vs caracteres (3-5 gramas) vs ambos |
| 4. Modelo | Regresión logística, `C` | 0.1, 0.3, 1, 3, 10 |
| 4. Modelo | `class_weight` | ninguno y `'balanced'` |
| 4. Modelo | Penalización | L2 (por defecto) y L1 (más interpretable) |
| 5. Recencia | Vida media τ de `peso = 0.5 ^ (edad / τ)` | 7, 14, 21, 45 días y sin peso |
| 6. Otro modelo | `HistGradientBoostingClassifier` | solo con variables de formato + SVD(100) del TF-IDF, comparado contra la regresión logística |

Total aproximado: unas 40 corridas pequeñas. Cada una debería tardar segundos a un par de minutos.

### 2.7 Semáforo (cuándo pasar a los planes de respaldo)

Valores esperables para modelos de solo-título: AUC entre 0.58 y 0.68. Un resultado modesto está bien **si lo mides bien y lo explicas**: la rúbrica pide explicar variables y cómo comprobaron el desempeño, no un AUC alto.

| Resultado en canales no vistos | Qué hacer |
|---|---|
| AUC ≥ 0.60 y lift@10 % ≥ 1.3 | Verde. Congela la configuración y avanza |
| AUC entre 0.55 y 0.60 | Amarillo. Aplica el Respaldo 0 y el Respaldo 1 |
| AUC < 0.55 | Rojo. Revisa fuga y calidad de etiqueta, luego los Respaldos 2, 3 y 4 en orden |

**Tope de tiempo:** máximo 2 días de experimentos. Pasado ese tiempo, se congela la mejor configuración y se sigue con el backend, aunque no sea perfecta.

### 2.8 Planes de respaldo (cambios pequeños)

**Respaldo 0. Más y mejores datos.** Es lo más barato y lo más confiable.
- Sube a 40 canales por nicho.
- Amplía la ventana de edad a 3-120 días.
- Quita canales con menos de 15 videos válidos.
- Quita videos de menos de 30 segundos que no sean Shorts reales.

**Respaldo 1. Quitar la zona gris.** Las etiquetas cerca del umbral son ruido.
- Entrena solo con ganadores claros (`ratio ≥ 2.0`) y perdedores claros (`ratio ≤ 0.8`), descartando el medio.
- Evalúa en **todos** los videos de prueba (sin descartar nada), para no inflar la métrica.

**Respaldo 2. Cambiar de clasificación a ranking.** Binarizar tira información.
- Regresión Ridge sobre `log(ratio)` en lugar de clasificación.
- Métricas: correlación de Spearman y `precision@10%` usando el ranking.
- La app muestra un puntaje de 0 a 100 (percentil dentro del nicho), no una probabilidad.

**Respaldo 3. Hacer que el nicho cambie el significado de las palabras.** Una palabra pesa distinto en cada nicho.
- Prefija cada palabra con el nicho (`gaming__speedrun`) para que el modelo aprenda por nicho.
- O entrena un modelo por nicho cuando haya más de 800 videos, y uno global como alternativa en los demás.

**Respaldo 4. Representar el tema en vez de las palabras exactas.** Útil si los títulos varían mucho en redacción.
- Embeddings multilingües pequeños (por ejemplo con `fastembed`, que usa ONNX) + regresión logística.
- O agrupa los embeddings en 30 a 60 temas (KMeans) y usa el tema como variable. Esto además da directamente "qué temas están pegando".
- **Cuidado:** en Render gratis (poca RAM) no cargues PyTorch. Calcula embeddings con la librería ligera y confirma el consumo de memoria antes de desplegar.

**Plan de emergencia (si nada sube de 0.55).** Aun así hay demo válida:
- Deja el modelo con la mejor configuración y repórtalo con honestidad (la rúbrica evalúa el proceso).
- El ranking "temas pegando ahora" usa **lift ponderado por recencia** (tasa de ganadores del término entre todos los videos que lo contienen, con el peso de recencia), que es estadística robusta y no depende de que el clasificador sea bueno.

### 2.9 Qué se guarda de cada entrenamiento

Para que `ml_service.py` y la defensa sean reproducibles, `model.joblib` va acompañado de un `metrics.json` con: configuración de etiqueta (θ, franjas), versión de variables, hiperparámetros, semillas, número de canales y videos usados, AUC, PR-AUC, `precision@10%`, lift, y los 20 términos con más peso positivo y negativo.

### 2.10 Cómo se explica en la defensa

1. Qué variables usa (tabla 2.4) y por qué se excluyen las de fuga.
2. Cómo se construye la etiqueta y por qué se corrige por edad.
3. Cómo se midió: separación por canal, baseline, AUC y lift (tabla comparativa).
4. Qué aprendió (términos con más peso, ablación).
5. Límites: relación con el tamaño de datos, y que los títulos explican solo una parte del éxito.

---

## Parte 3. Frontend (se completa al recibir la app Flutter)

Ya existe: `docs/REF_frontend_flutter.md` (estructura MVVM objetivo, qué se reutiliza de la app actual, qué cambiar, validaciones y detalles del APK). Se usa solo en T8, T9 y T10.

---

## Parte 4. Google Trends (tal vez, al final)

Solo si sobra tiempo después de T12 o en paralelo sin bloquear nada.

- Camino garantizado: CSV bajado a mano por nicho, guardado en el repo.
- Ajuste en la puntuación (fuera del modelo): `puntuacion_final = probabilidad × (0.8 + 0.4 × demanda_normalizada_del_nicho)`.
- Automatización opcional: script con `trendspy` en GitHub Actions programado; si Google responde 429, el script falla sin romper nada y se usa el último CSV.
- `pytrends` está archivado y falla con 429; no lo uses.

---

## Parte 5. Decisiones de diseño y pendientes

### Tomadas

| Decisión | Qué pide el PDF | Consecuencia | Alternativa |
|---|---|---|---|
| Sin `CHECK` en la BD (solo NOT NULL, UNIQUE y llaves foráneas) | Prueba 5: insertar un registro inválido directo en la BD y que la API lo excluya | La prueba se puede demostrar. La BD no se defiende sola: toda la protección está en la API, que es lo que el PDF pide | Dejar `CHECK` y quitarlos en una BD de prueba antes de la demo |
| Rol leído de la BD en cada petición, no del token | "Permisos vigentes en el servidor" | Una consulta extra por petición protegida; el rol vigente siempre se respeta | Rol dentro del JWT (queda desactualizado hasta que expire) |
| Campos extra rechazados con 422 | "El backend rechazará los intentos de asignarse un rol" | Enviar `role` en el registro da error, no se ignora | Ignorar el campo en silencio |
| Registro ajeno responde 404 | "Cambiar un identificador deberá ser insuficiente" | No revela que el registro existe | 403 |
| Modelo guardado en la BD (`model_runs.artifact`) | Entrenar con datos de clientes y mostrar el resultado en la app | Sobrevive a los despliegues; ocupa unos MB por entrenamiento (conservar los últimos 3) | Archivo en el repo o en disco |
| Edad medida contra `fetched_at` | No lo pide; es calidad del modelo | Hay que guardar `fetched_at`; refrescar vistas actualiza la etiqueta | Medir contra la fecha de hoy |
| Un cliente = un canal | No lo pide | Simplifica nichos y panel | Varios canales por usuario |
| Entrenar con un script (`train_model.py`), sin ruta de reentrenar | Entrenar con datos de la BD; no pide un botón de reentrenar | Menos código y sin límites de tiempo de Render; para incluir datos nuevos de clientes se vuelve a correr el script | `POST /admin/retrain` (opcional, T14) |

### Decididas por el equipo

- [x] **P1. Español.** Mezclar idiomas parte el vocabulario del TF-IDF en dos, reduce los datos por idioma y obliga a manejar stopwords y evaluación por idioma. Consecuencias: las consultas de descubrimiento son en español; la ingesta calcula `channels.language`; el modelo entrena solo con `language = 'es'`; un cliente con canal en otro idioma se registra, pero sus videos no entran al entrenamiento (se menciona como límite en la defensa).
- [x] **P2. Lista de canales:** con `scripts/discover_channels.py`, sin IA. Busca canales por nicho, filtra por tamaño y mezcla tamaños. Con los valores por defecto gasta unas 3,200 unidades de cuota. Falta correrlo con la API Key del equipo.
- [x] **P3. BD:** se reutiliza el proyecto de Supabase existente. Orden obligatorio: (1) detener el servicio viejo de Render o apuntarlo a este repo, porque al arrancar vuelve a crear y sembrar `users` y `products`; (2) en el editor SQL: `DROP TABLE IF EXISTS products, users CASCADE;`; (3) correr `C1_esquema_bd.sql`; (4) desplegar el backend nuevo.
- [x] **P4. Sin `POST /admin/retrain`.** El modelo se entrena con `scripts/train_model.py` (lee la BD, entrena, guarda en `model_runs` y lo activa). Se conserva `GET /admin/model` (modelo activo y métricas). Queda como T14, opcional.
- [x] **P5. 404 al pedir un registro ajeno.** Se queda así.

### Pendiente

- [ ] **P6. Preguntar al profe** si la prueba del registro inválido se hace en una BD de prueba sin restricciones, y qué campo espera que sea inválido (el PDF menciona "edad negativa" y nuestros usuarios no tienen edad).

---

## Parte 6. Estado del código (15-nov)

| Tarea | Estado |
|---|---|
| T0 Contratos | Hecho |
| T1a Descubrir canales | Script listo; falta correrlo con la API Key real |
| T1 Ingesta | Código listo y probado con YouTube simulado (`scripts/ingest.py`); falta correrlo con datos reales |
| T2 Dataset y etiqueta | Código listo y probado (`backend/ml/dataset.py`) |
| T3 Entrenamiento y evaluación | Código listo y probado con datos sintéticos; **falta correr los experimentos con datos reales** (sección 2.6) |
| T4 Servicio de predicción y entrenamiento desde la BD | Hecho (`ml/service.py`, `scripts/train_model.py`) |
| T5 Backend base (auth, roles, validación) | Hecho y probado contra Postgres real |
| T6 Backend dominio (canales, nichos, dueño del registro) | Hecho y probado con YouTube simulado |
| T7 Backend ML y panel | Hecho y probado (`/predict`, `/niches/{id}/topics`, `/admin/stats`, `/admin/model`) |
| T8, T9, T10 Frontend | Pendiente |
| T11 Pruebas de la rúbrica con la app | Las 8 pruebas del PDF están cubiertas por `backend/tests/` a nivel de API; falta repetirlas en la app instalada |
| T12 Entrega | Pendiente |
| T13, T14 | Opcionales |
