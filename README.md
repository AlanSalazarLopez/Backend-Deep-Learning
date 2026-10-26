# Backend US01-US05 (FastAPI + SQLite)

Reemplaza a Fake Store API. La base se crea y se llena sola al arrancar.

## Usuarios de prueba

| id | usuario  | contraseña  | rol (lo asigna la app) |
|----|----------|-------------|------------------------|
| 1  | admin1   | Admin123*   | Administrador          |
| 2  | admin2   | Admin456*   | Administrador          |
| 3  | auditor  | Audit123*   | Auditor                |
| 4  | cliente1 | Cliente123* | Cliente                |
| 5  | cliente2 | Cliente456* | Cliente                |
| 6  | cliente3 | Cliente789* | Cliente                |

## Endpoints

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| POST | /auth/login | Login -> `{token, id, username}` | - |
| GET | /users | Usuarios (sin contraseñas) | - |
| GET | /products | Catálogo completo (US03) | - |
| GET | /products/categories | Lista de categorías (US04) | - |
| GET | /products/category/{categoria} | Productos de una categoría (US04) | - |
| GET | /products/{id} | Detalle (US05); 404 si no existe | - |
| PUT | /products/{id} | Editar (US05) | Bearer, solo Administrador |
| DELETE | /products/{id} | Eliminar (US05) | Bearer, solo Administrador |

Cada producto: `{id, title, price, category, description, image}`.
PUT/DELETE responden 401 sin token y 403 si el usuario no es administrador
(ids 1 y 2, la misma regla que la app aplica en US01).

## Correr local (WSL)

```bash
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

Prueba: abre http://localhost:8000/docs

## Desplegar en Render (gratis)

1. Sube esta carpeta a un repo de GitHub.
2. Render -> New -> Web Service -> conecta el repo.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment -> agrega `JWT_SECRET` con un texto largo y aleatorio.
6. Cuando termine, tu URL es `https://TU-SERVICIO.onrender.com`.

Nota: en el plan gratis el servicio se duerme tras ~15 min sin tráfico y la
primera petición tarda ~30-60 s. Abre `/health` en el navegador antes de
una demo. Como la base se vuelve a crear en cada arranque, los datos
semilla siempre están.

## Cambio en las apps

Solo cambia la URL base:

- Flutter: `static const _baseUrl = 'https://TU-SERVICIO.onrender.com';` en `auth_service.dart`
- Flet: `BASE_URL = "https://TU-SERVICIO.onrender.com"` en `auth_service.py`

Sube el timeout de 8 s a ~60 s para tolerar el arranque en frío.
