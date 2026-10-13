"""Backend mínimo para US01/US02 (login y logout) — reemplaza a Fake Store API.

FastAPI + SQLite. La base se crea y se llena sola al arrancar, así que no
hay nada que configurar. Expone el mismo contrato que usaban las apps:
  POST /auth/login   -> {token, id, username}  (401 si credenciales malas)
  GET  /users        -> lista de usuarios (sin contraseñas)
  GET  /products     -> catálogo
  GET  /products/{id}
  GET  /health       -> chequeo de conectividad
  GET  /auth/me      -> valida el token (Authorization: Bearer <token>)
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing

import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.getenv("DB_PATH", "app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-cambiame-en-produccion")
JWT_HOURS = 24
PBKDF2_ITER = 120_000

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

SEED_PRODUCTS = [
    (1, "Mochila para laptop", 29.99, "accesorios", "Mochila resistente al agua con compartimento acolchado."),
    (2, "Audífonos inalámbricos", 49.90, "electrónica", "Bluetooth 5.0, 20 horas de batería."),
    (3, "Teclado mecánico", 64.50, "electrónica", "Switches rojos, retroiluminado."),
    (4, "Mouse ergonómico", 22.00, "electrónica", "Inalámbrico, 6 botones programables."),
    (5, "Cuaderno profesional", 4.75, "papelería", "100 hojas, pasta dura."),
    (6, "Botella térmica", 18.30, "accesorios", "Acero inoxidable, 750 ml."),
]


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


def init_db() -> None:
    with closing(get_db()) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL)"""
        )
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO users (id, username, password_hash, name) VALUES (?,?,?,?)",
                [(i, u, hash_password(p), n) for i, u, p, n in SEED_USERS],
            )
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO products (id, title, price, category, description) VALUES (?,?,?,?,?)",
                SEED_PRODUCTS,
            )
        db.commit()


# ---------- app ----------
app = FastAPI(title="Backend US01/US02")
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


@app.get("/auth/me")
def me(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta el token")
    try:
        data = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return {"id": int(data["sub"]), "username": data["username"]}


@app.get("/users")
def list_users():
    # Se mantiene por compatibilidad con las apps que resuelven el id con
    # GET /users. Nunca expone contraseñas.
    with closing(get_db()) as db:
        rows = db.execute("SELECT id, username, name FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.get("/products")
def list_products():
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with closing(get_db()) as db:
        row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return dict(row)
