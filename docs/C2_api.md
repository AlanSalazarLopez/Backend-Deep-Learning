# C2. Contrato de la API (FastAPI) — Proyecto 3er parcial

Si algo de este contrato no alcanza, se cambia **este archivo primero** y después el código.

## 1. Convenciones

- JSON UTF-8. Fechas en ISO 8601 con zona (`2026-11-13T18:30:00Z`).
- Autenticación: `Authorization: Bearer <token>`. JWT HS256 con `sub` (id), `username`, `iat`, `exp` (24 h). **El token no lleva el rol:** el backend lee el rol vigente de la BD en cada petición protegida.
- Códigos de error:

| Código | Cuándo |
|---|---|
| 401 | Falta el token, es inválido o expiró; credenciales incorrectas |
| 403 | Token válido pero el rol no permite la operación (cliente en ruta de admin) |
| 404 | No existe, **o pertenece a otro usuario** (no se revela su existencia) |
| 409 | Conflicto de estado (canal ya registrado, falta registrar canal) |
| 422 | Datos inválidos en la petición, o registro inválido leído de la BD en una consulta individual |
| 502 | Falla la API de YouTube (cuota, red) |
| 503 | No hay modelo activo |

- Formato de error (todos): `{"detail": "mensaje legible"}`. En 422 de validación se agrega `"errors": [{"field": "title", "message": "Debe tener entre 3 y 100 caracteres"}]`. La app Flutter muestra `detail`.
- Los cuerpos de petición **rechazan campos desconocidos** (`extra="forbid"`): enviar `role` en el registro da 422.

## 2. Matriz de permisos

| Ruta | Público | Cliente | Admin |
|---|:-:|:-:|:-:|
| `GET /health`, `POST /auth/register`, `POST /auth/login` | ✔ | ✔ | ✔ |
| `GET /auth/me`, `GET /niches`, `GET /niches/{id}/overview`, `GET /niches/{id}/topics` | | ✔ | ✔ |
| `POST /channels`, `GET /channels/mine`, `PUT /channels/mine/niche` | | ✔ | ✔ |
| `POST /predict`, `GET /predictions/mine`, `GET /predictions/{id}` (solo el dueño) | | ✔ | ✔ |
| `GET /admin/stats`, `GET /admin/users`, `POST /admin/users/{id}/promote`, `GET /admin/model` | | ✖ (403) | ✔ |

## 3. Autenticación

**`POST /auth/register`** → 201
```json
// petición
{"username": "ana_01", "password": "Clave1234", "name": "Ana Pérez"}
// respuesta
{"id": 7, "username": "ana_01", "name": "Ana Pérez", "role": "client"}
```
Validación: `username` 3–30 (`[A-Za-z0-9._]`), `password` mínimo 8 con letra y número, `name` 1–80. Usuario repetido → 409. El rol siempre es `client`.

**`POST /auth/login`** → 200 (401 si falla; mismo mensaje para usuario inexistente y contraseña errónea)
```json
// petición
{"username": "ana_01", "password": "Clave1234"}
// respuesta
{"token": "<jwt>", "id": 7, "username": "ana_01", "role": "client"}
```

**`GET /auth/me`** → `{"id": 7, "username": "ana_01", "name": "Ana Pérez", "role": "client"}`

## 4. Canal y nicho

**`POST /channels`** → 201 (carga el canal y hasta 50 videos recientes con la API de YouTube)
```json
// petición
{"handle": "@micanal"}
// respuesta
{
  "id": 3, "yt_channel_id": "UCxxxx", "handle": "@micanal", "title": "Mi Canal",
  "niche_id": null, "suggested_niche_id": 4, "videos_loaded": 38, "language": "es"
}
```
- `suggested_niche_id`: la categoría más frecuente de sus videos, **solo si tiene 10 videos o más**; si no, `null` y el cliente elige de la lista.
- `niche_id` queda `null` hasta confirmar con `PUT /channels/mine/niche`.
- `language`: idioma mayoritario de sus títulos. El modelo está entrenado solo con español: si no es `es`, el canal se registra igual, pero sus videos no entran al entrenamiento.
- Errores: 422 handle inválido (`^@?[A-Za-z0-9._-]{3,30}$`); 404 no existe en YouTube; 409 el cliente ya tiene un canal, o el canal es de otro usuario; 502 falla de YouTube.

**`GET /channels/mine`** → mismo objeto sin `suggested_niche_id` ni `videos_loaded`; 404 si no ha registrado canal.

**`PUT /channels/mine/niche`** `{"niche_id": 4}` → canal actualizado. 404 si el nicho no existe; 409 si no tiene canal.

**`GET /niches`** → `[{"id": 1, "slug": "gaming", "name": "Gaming", "n_videos": 812}]`

**`GET /niches/{id}/overview`** (409 si el cliente aún no registra canal)
```json
{
  "niche": {"id": 4, "name": "Ciencia y tecnología"},
  "window_days": 90,
  "own":   {"n_videos": 24, "median_views_per_day": 310.5, "pct_outperformers": 0.25},
  "niche_stats": {"n_channels": 27, "n_videos": 1180, "median_views_per_day": 420.0, "pct_outperformers": 0.28},
  "own_top_videos": [{"yt_video_id": "abc", "title": "…", "views": 52000, "ratio": 2.4}]
}
```
`own_top_videos`: máximo 5. `pct_outperformers` = proporción con `y = 1` (definición en `C3_ml.md`).

**`GET /niches/{id}/topics?limit=10`** → temas que pegan ahora (lift ponderado por recencia, ver `C3_ml.md` sección 4)
```json
[{"term": "inteligencia artificial", "lift": 2.1, "win_rate": 0.52, "n_videos": 34}]
```

## 5. Predicción

**`POST /predict`** → 200 (503 si no hay modelo activo)
```json
// petición (publish_weekday opcional: 0 = lunes ... 6 = domingo; por defecto, el día de hoy)
{"niche_id": 4, "title": "Probé 5 IAs gratis", "duration_s": 600, "publish_hour": 18, "publish_weekday": 4}
// respuesta
{
  "prediction_id": 12, "score": 71.4, "probability": 0.43, "model_run_id": 5,
  "top_terms": [{"term": "gratis", "weight": 0.8}, {"term": "probé", "weight": 0.5}],
  "created_at": "2026-11-13T18:30:00Z"
}
```
Validación: `title` 3–100, `duration_s` 1–7200, `publish_hour` 0–23, `publish_weekday` 0–6 (422); `niche_id` inexistente → 404. La hora y el día se interpretan en la zona horaria `America/Mexico_City` (la misma con la que se entrena).
`score` = percentil (0–100) de la probabilidad dentro del nicho. La app lo muestra como "puntuación", no como probabilidad literal.

**`GET /predictions/mine?limit=20`** (1 a 100) → lista de objetos con los mismos campos de la respuesta de `/predict` más `title`, `niche_id`, `duration_s`, `publish_hour` y `publish_weekday`, de la más reciente a la más antigua.
**`GET /predictions/{id}`** → un registro; **404 si pertenece a otro usuario** (aunque quien consulta sea admin).

## 6. Administración (solo admin, 403 a clientes)

**`GET /admin/stats`** — todo calculado solo con registros válidos
```json
{
  "totals": {"users": 14, "clients": 12, "admins": 2, "channels": 11, "videos": 9300, "predictions": 57},
  "per_client": [{"user_id": 7, "username": "ana_01", "channel_handle": "@micanal", "niche": "Gaming", "n_predictions": 6, "last_activity": "2026-11-13T18:30:00Z"}],
  "by_niche": [{"niche_id": 1, "name": "Gaming", "n_clients": 3, "n_videos": 812, "n_predictions": 21}],
  "activity_by_day": [{"date": "2026-11-12", "n_predictions": 9}]
}
```
`per_client` = tabla; `by_niche` o `activity_by_day` = gráfica (últimos 14 días).

**`GET /admin/users?limit=50&offset=0`** → `{"items": [{"id": 7, "username": "ana_01", "name": "Ana Pérez", "role": "client", "channel_handle": "@micanal", "created_at": "…"}], "total": 14}`
Cada fila se valida con Pydantic antes de salir; **las inválidas se omiten** (y se registran en el log del servidor), y `total` cuenta solo las válidas. `limit` y `offset` se aplican después de omitirlas. Nunca incluye contraseñas ni hashes.

**`POST /admin/users/{id}/promote`** → `{"id": 7, "username": "ana_01", "role": "admin"}`. Persiste en la BD; idempotente; 404 si no existe o es un registro inválido. El usuario ejerce permisos de admin al volver a iniciar sesión.

**`GET /admin/model`** (solo lectura; el modelo se entrena con `scripts/train_model.py`, ver `C3_ml.md` sección 9) → `{"active": {"id": 5, "trained_at": "…", "n_videos": 9300, "n_channels": 210, "metrics": {…}, "config": {…}}}` (`active` es `null` si no hay modelo).

**`GET /health`** → `{"status": "ok"}` (consulta la BD).

## 7. Seguridad (requisitos de la rúbrica)

1. **Contraseñas:** `argon2-cffi` (Argon2id). Ninguna respuesta incluye contraseñas, hashes ni secretos.
2. **Primer administrador:** `python -m scripts.init_admin --username admin --name "Admin"` (pide la contraseña por consola y usa la misma función de hash que el registro). Documentado en el README.
3. **Rol:** siempre de la BD, nunca del token ni del cuerpo de la petición.
4. **Validación de entrada:** todas las entradas (cuerpo, parámetros de ruta y de query) pasan por clases Pydantic; debe funcionar igual desde Postman o curl.
5. **Validación de lectura:** todo lo leído de la BD pasa por modelos `*Out`. En listas y estadísticas los inválidos se excluyen; en consultas individuales → 422 con `{"detail": "Registro con datos inválidos"}`.
6. **Dueño del registro:** cada consulta de datos de cliente filtra por `user_id` del token; cambiar un id en la URL da 404.
7. **SQL:** solo consultas parametrizadas.
8. **Variables de entorno:** `DATABASE_URL`, `JWT_SECRET` (obligatoria, sin valor por defecto), `YOUTUBE_API_KEY`.

## 8. Estructura MC del backend

```
backend/
  main.py            # app, CORS, manejadores de error, routers
  models/            # Pydantic (entrada y *Out) + acceso a tablas: user, channel, niche, video, prediction
  controllers/       # routers: auth, channels, niches, predictions, admin
  services/          # security (argon2, jwt), youtube_client, model_store
  ml/                # paquete de ML puro (ver `C3_ml.md`); sin imports de FastAPI ni de la BD
  scripts/           # init_admin.py, discover_channels.py, ingest.py, train_model.py
```
