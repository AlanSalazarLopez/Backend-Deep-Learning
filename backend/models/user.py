"""Modelo de usuario: esquemas Pydantic (entrada y salida) y acceso a la tabla users."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.security import hash_password

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{3,30}$")


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")   # enviar "role" u otro campo extra => 422
    username: str
    password: str
    name: str

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        if not USERNAME_RE.match(v):
            raise ValueError("El usuario debe tener entre 3 y 30 caracteres (letras, números, . o _)")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        if not (8 <= len(v) <= 128 and re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Usa al menos 8 caracteres con letras y números")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = v.strip()
        if not (1 <= len(v) <= 80):
            raise ValueError("Escribe tu nombre (máximo 80 caracteres)")
        return v


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Se usa también para VALIDAR lo leído de la BD: un registro que no cumpla se excluye."""
    id: int = Field(ge=1)
    username: str = Field(pattern=USERNAME_RE.pattern)
    name: str = Field(min_length=1, max_length=80)
    role: Literal["client", "admin"]

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v):
        if not v.strip():
            raise ValueError("nombre vacío")
        return v


class LoginOut(BaseModel):
    token: str
    id: int
    username: str
    role: Literal["client", "admin"]


class AdminUserOut(UserOut):
    channel_handle: str | None = None
    niche_id: int | None = Field(default=None, exclude=True)   # solo para estadísticas, no se devuelve
    created_at: datetime


class UsersPage(BaseModel):
    items: list[AdminUserOut]
    total: int


class PromoteOut(BaseModel):
    id: int
    username: str
    role: Literal["client", "admin"]


# ------------------------------------------------------------------ acceso a datos
def get_row(conn, user_id: int):
    return conn.execute("SELECT id, username, name, role, created_at FROM users WHERE id = %s", (user_id,)).fetchone()


def get_auth_row(conn, username: str):
    return conn.execute("SELECT id, username, name, role, password_hash FROM users WHERE username = %s",
                        (username,)).fetchone()


def create(conn, username: str, name: str, password: str, role: str = "client"):
    return conn.execute(
        "INSERT INTO users (username, password_hash, name, role) VALUES (%s, %s, %s, %s) "
        "RETURNING id, username, name, role, created_at",
        (username, hash_password(password), name, role),
    ).fetchone()


def list_with_channel(conn):
    """Una fila por usuario (puede tener varios canales): sus handles juntos y el nicho del primero."""
    return conn.execute(
        "SELECT u.id, u.username, u.name, u.role, u.created_at, "
        "string_agg(c.handle, ', ' ORDER BY c.id) AS channel_handle, "
        "(array_agg(c.niche_id ORDER BY c.id))[1] AS niche_id "
        "FROM users u LEFT JOIN channels c ON c.user_id = u.id "
        "GROUP BY u.id, u.username, u.name, u.role, u.created_at ORDER BY u.id"
    ).fetchall()


def set_role(conn, user_id: int, role: str) -> None:
    conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))