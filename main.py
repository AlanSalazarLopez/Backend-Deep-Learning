"""Backend mínimo para US01-US05 (login, logout, catálogo, filtro y detalle).

FastAPI + SQLite. La base se crea y se llena sola al arrancar, así que no
hay nada que configurar. Expone el mismo contrato que usaban las apps:
  POST   /auth/login               -> {token, id, username}  (401 si credenciales malas)
  GET    /users                    -> lista de usuarios (sin contraseñas)
  GET    /products                 -> catálogo completo               (US03)
  GET    /products/categories      -> lista de categorías             (US04)
  GET    /products/category/{cat}  -> productos de una categoría      (US04)
  GET    /products/{id}            -> detalle                         (US05)
  PUT    /products/{id}            -> editar    (solo Administrador)  (US05)
  DELETE /products/{id}            -> eliminar  (solo Administrador)  (US05)
  GET    /health                   -> chequeo de conectividad
  GET    /auth/me                  -> valida el token (Authorization: Bearer <token>)
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = os.getenv("DB_PATH", "app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-cambiame-en-produccion")
JWT_HOURS = 24
PBKDF2_ITER = 120_000
# Ids que la app mapea a "Administrador" (US01). Solo se usan para proteger
# PUT/DELETE en el servidor; la UI sigue decidiendo qué mostrar con el rol local.
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


# ---------- base de datos ----------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _create_products_table(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT NOT NULL DEFAULT '')"""
    )


def init_db() -> None:
    with closing(get_db()) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL)"""
        )
        _create_products_table(db)
        # Migración: si la tabla viene de la versión anterior (sin columna
        # image) se recrea; los productos son datos semilla.
        cols = [r["name"] for r in db.execute("PRAGMA table_info(products)")]
        if "image" not in cols:
            db.execute("DROP TABLE products")
            _create_products_table(db)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO users (id, username, password_hash, name) VALUES (?,?,?,?)",
                [(i, u, hash_password(p), n) for i, u, p, n in SEED_USERS],
            )
        # Migración: BD de la versión anterior con imágenes de picsum.photos.
        db.execute(
            "UPDATE products SET image = '/static/products/' || id || '.png' "
            "WHERE image LIKE 'https://picsum.photos/%'"
        )
        db.commit()
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO products (id, title, price, category, description, image) VALUES (?,?,?,?,?,?)",
                SEED_PRODUCTS,
            )
        db.commit()


# ---------- app ----------
app = FastAPI(title="Backend US01-US05")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
init_db()

# Hash falso para igualar tiempos cuando el usuario no existe.
_DUMMY_HASH = hash_password("x")


class LoginBody(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(body: LoginBody):
    with closing(get_db()) as db:
        row = db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
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
    with closing(get_db()) as db:
        rows = db.execute("SELECT id, username, name FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _product_out(row, request: Request) -> dict:
    """Producto listo para el cliente: si la imagen es una ruta relativa
    (/static/...) la vuelve URL absoluta con el host real de la petición
    (detrás del proxy de Render usa x-forwarded-* para conservar https)."""
    product = dict(row)
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
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return [_product_out(r, request) for r in rows]


# OJO: /products/categories y /products/category/{c} se declaran ANTES de
# /products/{product_id}; si no, FastAPI intentaría leer "categories" como id.
@app.get("/products/categories")
def list_categories():
    with closing(get_db()) as db:
        rows = db.execute(
            "SELECT DISTINCT category FROM products ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@app.get("/products/category/{category}")
def list_products_by_category(category: str, request: Request):
    with closing(get_db()) as db:
        rows = db.execute(
            "SELECT * FROM products WHERE category = ? ORDER BY id", (category,)
        ).fetchall()
    return [_product_out(r, request) for r in rows]


@app.get("/products/{product_id}")
def get_product(product_id: int, request: Request):
    with closing(get_db()) as db:
        row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return _product_out(row, request)


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    price: float | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    image: str | None = None


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    request: Request,
    _admin: int = Depends(require_admin),
):
    fields = body.model_dump(exclude_none=True)  # solo columnas del modelo
    with closing(get_db()) as db:
        if not db.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        if fields:
            sets = ", ".join(f"{col} = ?" for col in fields)
            db.execute(
                f"UPDATE products SET {sets} WHERE id = ?",
                (*fields.values(), product_id),
            )
            db.commit()
        row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _product_out(row, request)


@app.delete("/products/{product_id}")
def delete_product(product_id: int, _admin: int = Depends(require_admin)):
    with closing(get_db()) as db:
        cur = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return {"deleted": product_id}
