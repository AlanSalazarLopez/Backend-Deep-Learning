"""Contraseñas (Argon2id) y tokens JWT. El token NO lleva el rol: se lee de la BD en cada petición."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from config import settings

_ph = PasswordHasher()  # Argon2id por defecto
DUMMY_HASH = _ph.hash("contraseña-ficticia-para-igualar-tiempos")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def create_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "username": username, "iat": now,
               "exp": now + timedelta(hours=settings.jwt_expire_hours)}
    return jwt.encode(payload, settings.require("jwt_secret"), algorithm="HS256")


def decode_token(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token es inválido o expiró."""
    return jwt.decode(token, settings.require("jwt_secret"), algorithms=["HS256"], options={"require": ["exp", "sub"]})
