"""Dependencias de autenticación y autorización (el rol siempre sale de la BD)."""
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

import db
from models import user as user_model
from models.user import UserOut
from services.security import decode_token

_bearer = HTTPBearer(auto_error=False)
_UNAUTH = {"WWW-Authenticate": "Bearer"}


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     conn=Depends(db.get_db)) -> UserOut:
    if creds is None:
        raise HTTPException(401, "Falta iniciar sesión", headers=_UNAUTH)
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Sesión inválida o vencida", headers=_UNAUTH)
    row = user_model.get_row(conn, user_id)
    if row is None:
        raise HTTPException(401, "Sesión inválida o vencida", headers=_UNAUTH)
    try:
        return UserOut.model_validate(row)
    except ValidationError:
        raise HTTPException(401, "Cuenta no válida", headers=_UNAUTH)


def require_admin(user: UserOut = Depends(get_current_user)) -> UserOut:
    if user.role != "admin":
        raise HTTPException(403, "Se requiere rol de administrador")
    return user
