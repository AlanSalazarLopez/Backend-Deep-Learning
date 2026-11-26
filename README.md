# YT Trends — Proyecto 3er parcial (Aplicaciones móviles)

App para creadores de YouTube: dice qué ideas de título superan el rendimiento normal de su canal, por nicho.
FastAPI + PostgreSQL (Supabase) + scikit-learn + Flutter. Contratos y plan en `docs/`.

## Estructura

    docs/        PLAN, REF_frontend_flutter, C1 (BD), C2 (API), C3 (ML)
    backend/     FastAPI (MC): models/ controllers/ services/ ml/ scripts/ tests/
    data/        channels_seed.csv y cachés (los cachés no se suben)
    mobile/      Flutter
    .env         secretos (NO se sube; la plantilla es .env.example)

## Primera vez (Windows / PowerShell; en WSL cambia la activación por `source .venv/bin/activate`)

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r backend\requirements.txt

Llena `.env`: `YOUTUBE_API_KEY`, `DATABASE_URL` (Session pooler de Supabase) y `JWT_SECRET`
(`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

## Base de datos y cuentas (desde `backend/`)

    cd backend
    python -m scripts.init_db                                   # crea las tablas (docs/C1_esquema_bd.sql)
    python -m scripts.init_admin --username admin               # primer administrador (pide la contraseña)
    python -m scripts.seed_demo                                 # cuentas de prueba: admin_demo, cliente_demo, cliente_demo2

Antes, en Supabase: `DROP TABLE IF EXISTS products, users CASCADE;` (ver `docs/PLAN_proyecto.md`, P3).

## Datos y modelo (desde la raíz / desde `backend/`)

    python backend\scripts\discover_channels.py --niches gaming --queries-per-niche 1   # prueba de 100 unidades
    python backend\scripts\discover_channels.py                                         # lista completa -> data\channels_seed.csv
    cd backend
    python -m scripts.ingest                  # carga canales y videos (3 unidades por canal)
    python -m scripts.train_model             # entrena con la BD, imprime métricas y activa el modelo

El modelo se guarda **dentro de la base de datos**: se entrena en tu PC (con el mismo `DATABASE_URL` de producción)
y el servidor de Render lo carga solo. Cuando entren datos nuevos de clientes, se vuelve a correr `train_model`.

## Correr la API

    cd backend
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    # documentación interactiva: http://localhost:8000/docs

## Pruebas (necesitan pgserver: Linux, macOS o WSL)

    pip install -r backend/requirements-dev.txt
    cd backend && python -m pytest

Cubren las 8 pruebas del PDF a nivel de API contra un PostgreSQL real y local, con YouTube simulado.

## Desplegar en Render

- Root Directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Variables de entorno: `DATABASE_URL`, `JWT_SECRET`, `YOUTUBE_API_KEY`, `APP_ENV=production`, `PYTHON_VERSION=3.12.3`
- Secreto `HEALTH_URL` en GitHub (`https://tu-servicio.onrender.com/health`) para el workflow `keepalive`.

## Reglas

- `.env` nunca se sube a GitHub.
- Si cambia un contrato (C1, C2, C3), se actualiza primero el documento y después el código.
- Tareas y orden: `docs/PLAN_proyecto.md`.
