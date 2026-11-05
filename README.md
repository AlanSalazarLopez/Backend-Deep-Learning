# Backend US01-US08 (FastAPI + PostgreSQL)

Reemplaza a Fake Store API. Las tablas se crean y se llenan solas la primera
vez que arranca (usuarios y 13 productos semilla). Ya no se usa SQLite: todo
vive en PostgreSQL, así los datos sobreviven a los reinicios de Render.

## Variables de entorno

| Variable       | Qué es |
|----------------|--------|
| `DATABASE_URL` | Cadena de conexión de PostgreSQL, ej. `postgresql://usuario:clave@host:5432/basedatos` |
| `JWT_SECRET`   | Texto largo y aleatorio para firmar los tokens |

## Opción A: Supabase (gratis)

1. Crea un proyecto en supabase.com y guarda la contraseña de la base.
2. Botón **Connect** del proyecto -> copia la cadena **Session pooler**
   (puerto 5432). Usa esa y no la "Direct connection": la directa suele ser
   solo IPv6 y Render gratis no la alcanza.
3. Esa cadena es tu `DATABASE_URL` (reemplaza `[YOUR-PASSWORD]` por tu contraseña).
4. Los proyectos gratis se pausan tras ~1 semana sin actividad; se reactivan
   desde el panel.

## Opción B: alwaysdata (gratis)

1. Crea cuenta en alwaysdata.com -> **Databases -> PostgreSQL -> Add a database**.
2. Crea también un usuario de base de datos con contraseña y dale permisos.
3. `DATABASE_URL = postgresql://USUARIO:CLAVE@postgresql-CUENTA.alwaysdata.net:5432/CUENTA_nombrebd`
   (host, usuario y nombre exactos los ves en el panel).

> Los límites de los planes gratis cambian: confirma en la página de cada
> proveedor antes de depender de ellos.

## Correr local (WSL)

```bash
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && export DATABASE_URL='postgresql://USUARIO:CLAVE@HOST:5432/BASE' && export JWT_SECRET='un-texto-largo-y-aleatorio' && uvicorn main:app --reload --port 8000
```

Prueba: abre http://localhost:8000/docs

## Desplegar en Render (gratis)

1. Sube esta carpeta a un repo de GitHub.
2. Render -> New -> Web Service -> conecta el repo.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment -> agrega `DATABASE_URL` y `JWT_SECRET`.
6. Cuando termine, tu URL es `https://TU-SERVICIO.onrender.com`.

Nota: en el plan gratis el servicio se duerme tras ~15 min sin tráfico y la
primera petición tarda ~30-60 s. Abre `/health` antes de una demo (también
comprueba que la base responde).

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
| POST | /products | Crear (US06); 201 con el producto y su nuevo `id` | Bearer, solo Administrador |
| PUT | /products/{id} | Editar (US07) | Bearer, solo Administrador |
| DELETE | /products/{id} | Eliminar (US08) | Bearer, solo Administrador |

Cada producto: `{id, title, price, category, description, image}`.
Los cambios ahora SÍ se guardan (a diferencia de Fake Store API). Las
escrituras responden 401 sin token y 403 si el usuario no es administrador
(ids 1 y 2, la misma regla que la app aplica en US01).

## Imágenes de productos

Viven en `static/products/<id>.png` y el backend las sirve en
`/static/products/<id>.png`; la API devuelve la URL absoluta en `image`.
Los productos nuevos usan la URL externa que escriba el administrador.

Los íconos son [Twemoji](https://github.com/jdecked/twemoji) (Copyright
Twitter, Inc. y colaboradores), licencia CC-BY 4.0.
