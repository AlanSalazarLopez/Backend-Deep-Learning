import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

import db
from controllers.deps import get_current_user
from models import user as user_model
from models.user import LoginIn, LoginOut, RegisterIn, UserOut
from services.security import DUMMY_HASH, create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, conn=Depends(db.get_db)):
    try:
        row = user_model.create(conn, body.username, body.name, body.password, role="client")  # el rol nunca viene del cliente
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(409, "Ese usuario ya existe")
    conn.commit()
    return UserOut.model_validate(row)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, conn=Depends(db.get_db)):
    row = user_model.get_auth_row(conn, body.username)
    # Siempre se verifica un hash (el real o uno ficticio) para igualar tiempos de respuesta.
    ok = verify_password(row["password_hash"] if row else DUMMY_HASH, body.password)
    if not row or not ok:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    try:
        user = UserOut.model_validate(row)
    except ValidationError:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    return LoginOut(token=create_token(user.id, user.username), id=user.id, username=user.username, role=user.role)


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return user
