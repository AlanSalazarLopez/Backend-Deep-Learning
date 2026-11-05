"""Backend US01-US08 (login, catálogo, filtro, detalle y CRUD de productos).

FastAPI + PostgreSQL (Supabase, alwaysdata, Neon, etc.). La conexión sale de
la variable de entorno DATABASE_URL; las tablas se crean y se llenan solas
la primera vez que arranca. Contrato:
  POST   /auth/login               -> {token, id, username}  (401 si credenciales malas)
  GET    /auth/me                  -> valida el token (Authorization: Bearer <token>)
  GET    /users                    -> lista de usuarios (sin contraseñas)
  GET    /products                 -> catálogo completo               (US03)
  GET    /products/categories      -> lista de categorías             (US04)
  GET    /products/category/{cat}  -> productos de una categoría      (US04)
  GET    /products/{id}            -> detalle                         (US05)
  POST   /products                 -> crear     (solo Administrador)  (US06)
  PUT    /products/{id}            -> editar    (solo Administrador)  (US07)
  DELETE /products/{id}            -> eliminar  (solo Administrador)  (US08)
  GET    /health                   -> chequeo de conectividad (también toca la BD)
"""

import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field, field_validator

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Falta la variable de entorno DATABASE_URL "
        "(ej. postgresql://usuario:clave@host:5432/postgres)"
    )
# Algunos proveedores entregan "postgres://"; psycopg espera "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-cambiame-en-produccion")
JWT_HOURS = 24
PBKDF2_ITER = 120_000
# Ids que la app mapea a "Administrador" (US01). Solo se usan para proteger
# POST/PUT/DELETE en el servidor; la UI decide qué mostrar con el rol local.
ADMIN_IDS = {1, 2}

# id 1 y 2 -> Administrador, id 3 -> Auditor, el resto -> Cliente.
# (El mapeo de roles NO vive aquí: lo hace la app, como pide US01.)
SEED_USERS = [
    (1, "admin1", "Admin123*", "Ana Administradora"),
    (2, "admin2", "Admin456*", "Luis Administrador"),
    (3, "auditor", "Audit123*", "Marta Auditora"),
    (4, "cliente1", "Cliente123*", "Carlos Cliente"),
    (5, "cliente2", "Cliente456*", "Sofía Cliente"),
    (6, "cliente3", "Cliente789*", "Diego Cliente"),
]

STATIC_DIR = Path(__file__).parent / "static"


def _img(product_id: int) -> str:
    # Ruta relativa a las imágenes que viajan con el backend (static/products).
    # Al responder se convierte en URL absoluta (ver _product_out).
    return f"/static/products/{product_id}.png"


_SEED_RAW = [
    (1, "Mochila para laptop", 29.99, "accesorios", "Mochila resistente al agua con compartimento acolchado."),
    (2, "Audífonos inalámbricos", 49.90, "electrónica", "Bluetooth 5.0, 20 horas de batería."),
    (3, "Teclado mecánico", 64.50, "electrónica", "Switches rojos, retroiluminado."),
    (4, "Mouse ergonómico", 22.00, "electrónica", "Inalámbrico, 6 botones programables."),
    (5, "Cuaderno profesional", 4.75, "papelería", "100 hojas, pasta dura."),
    (6, "Botella térmica", 18.30, "accesorios", "Acero inoxidable, 750 ml."),
    (7, "Lámpara de escritorio", 24.90, "hogar", "LED regulable con puerto de carga USB."),
    (8, "Organizador de escritorio", 15.40, "hogar", "Madera de bambú, 5 compartimentos."),
    (9, "Set de plumas gel", 6.80, "papelería", "Paquete de 12 colores, punta de 0.5 mm."),
    (10, "Agenda semanal", 9.99, "papelería", "Planificador con vista semanal y pasta flexible."),
    (11, "Cargador USB-C 65 W", 35.00, "electrónica", "Carga rápida para laptop y celular."),
    (12, "Cartera de piel", 27.50, "accesorios", "Piel genuina con 6 ranuras para tarjetas."),
    (13, "Taza de cerámica", 8.90, "hogar", "Capacidad de 350 ml, apta para microondas."),
]
SEED_PRODUCTS = [(i, t, p, c, d, _img(i)) for i, t, p, c, d in _SEED_RAW]


# ---------- contraseñas ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITER
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------- base de datos (PostgreSQL) ----------
# Pool pequeño: los planes gratis limitan las conexiones simultáneas.
# - prepare_threshold=None: necesario si usas el pooler en modo "transaction"
#   (Supabase puerto 6543), que no soporta prepared statements.
# - check: descarta conexiones que el proveedor cerró por inactividad.
pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
    check=ConnectionPool.check_connection,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
)


def init_db() -> None:
    with pool.connection() as db:  # commit automático al salir sin error
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                price NUMERIC(10,2) NOT NULL CHECK (price > 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL DEFAULT '')"""
        )
        if db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
            with db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO users (id, username, password_hash, name) "
                    "VALUES (%s,%s,%s,%s)",
                    [(i, u, hash_password(p), n) for i, u, p, n in SEED_USERS],
                )
        if db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0:
            with db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO products (id, title, price, category, description, image) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    SEED_PRODUCTS,
                )
            # Los ids semilla se insertaron a mano: alinea la secuencia para
            # que el siguiente POST /products no choque con el id 1.
            db.execute(
                "SELECT setval(pg_get_serial_sequence('products','id'), "
                "(SELECT MAX(id) FROM products))"
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    pool.open(wait=True, timeout=60)
    init_db()
    yield
    pool.close()


# ---------- app ----------
app = FastAPI(title="Backend US01-US08", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Hash falso para igualar tiempos cuando el usuario no existe.
_DUMMY_HASH = hash_password("x")


class LoginBody(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    with pool.connection() as db:
        db.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/auth/login")
def login(body: LoginBody):
    with pool.connection() as db:
        row = db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (body.username,),
        ).fetchone()
    stored = row["password_hash"] if row else _DUMMY_HASH
    ok = verify_password(body.password, stored)
    if not row or not ok:
        raise HTTPException(status_code=401, detail="Usuario o contraseña inválidos")
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(row["id"]),
            "username": row["username"],
            "iat": now,
            "exp": now + JWT_HOURS * 3600,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"token": token, "id": row["id"], "username": row["username"]}


def _decode_token(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta el token")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def require_admin(authorization: str | None = Header(default=None)) -> int:
    data = _decode_token(authorization)
    user_id = int(data["sub"])
    if user_id not in ADMIN_IDS:
        raise HTTPException(
            status_code=403, detail="Solo un administrador puede realizar esta acción"
        )
    return user_id


@app.get("/auth/me")
def me(authorization: str | None = Header(default=None)):
    data = _decode_token(authorization)
    return {"id": int(data["sub"]), "username": data["username"]}


@app.get("/users")
def list_users():
    # Se mantiene por compatibilidad con las apps que resuelven el id con
    # GET /users. Nunca expone contraseñas.
    with pool.connection() as db:
        rows = db.execute("SELECT id, username, name FROM users ORDER BY id").fetchall()
    return rows


def _product_out(row: dict, request: Request) -> dict:
    """Producto listo para el cliente: price como número (Postgres devuelve
    Decimal) y, si la imagen es una ruta relativa (/static/...), la vuelve
    URL absoluta con el host real de la petición (detrás del proxy de Render
    usa x-forwarded-* para conservar https)."""
    product = dict(row)
    product["price"] = float(product["price"])
    image = product.get("image") or ""
    if image.startswith("/"):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        proto = proto.split(",")[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        host = (host or request.url.netloc).split(",")[0].strip()
        product["image"] = f"{proto}://{host}{image}"
    return product


@app.get("/products")
def list_products(request: Request):
    with pool.connection() as db:
        rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return [_product_out(r, request) for r in rows]


# OJO: /products/categories y /products/category/{c} se declaran ANTES de
# /products/{product_id}; si no, FastAPI intentaría leer "categories" como id.
@app.get("/products/categories")
def list_categories():
    with pool.connection() as db:
        rows = db.execute(
            "SELECT DISTINCT category FROM products ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@app.get("/products/category/{category}")
def list_products_by_category(category: str, request: Request):
    with pool.connection() as db:
        rows = db.execute(
            "SELECT * FROM products WHERE category = %s ORDER BY id", (category,)
        ).fetchall()
    return [_product_out(r, request) for r in rows]


@app.get("/products/{product_id}")
def get_product(product_id: int, request: Request):
    with pool.connection() as db:
        row = db.execute("SELECT * FROM products WHERE id = %s", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return _product_out(row, request)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("No puede estar vacío")
    return value


def _check_image(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("La imagen debe ser una URL http(s)")
    return value


class ProductCreate(BaseModel):
    # US06: todos los campos son obligatorios (la validación vive también en
    # el servidor aunque las apps ya validan antes de enviar).
    title: str = Field(min_length=1)
    price: float = Field(gt=0)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    image: str = ""

    _t = field_validator("title", "category", "description")(_clean_text)
    _i = field_validator("image")(_check_image)


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    price: float | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    image: str | None = None

    _t = field_validator("title", "category", "description")(_clean_text)
    _i = field_validator("image")(_check_image)


@app.post("/products", status_code=201)
def create_product(
    body: ProductCreate, request: Request, _admin: int = Depends(require_admin)
):
    with pool.connection() as db:
        row = db.execute(
            "INSERT INTO products (title, price, category, description, image) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (body.title, body.price, body.category, body.description, body.image),
        ).fetchone()
    return _product_out(row, request)


# Columnas que PUT puede tocar (lista blanca: los nombres vienen del código,
# nunca del cliente, así que el UPDATE dinámico es seguro).
_UPDATABLE = ("title", "price", "category", "description", "image")


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    request: Request,
    _admin: int = Depends(require_admin),
):
    fields = {k: v for k, v in body.model_dump(exclude_none=True).items() if k in _UPDATABLE}
    with pool.connection() as db:
        if not db.execute("SELECT 1 FROM products WHERE id = %s", (product_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        if fields:
            sets = ", ".join(f"{col} = %s" for col in fields)
            db.execute(
                f"UPDATE products SET {sets} WHERE id = %s",
                (*fields.values(), product_id),
            )
        row = db.execute("SELECT * FROM products WHERE id = %s", (product_id,)).fetchone()
    return _product_out(row, request)


@app.delete("/products/{product_id}")
def delete_product(product_id: int, _admin: int = Depends(require_admin)):
    with pool.connection() as db:
        cur = db.execute("DELETE FROM products WHERE id = %s", (product_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return {"deleted": product_id}
