"""Punto de entrada de la API (arquitectura MC: models/ + controllers/). Ver docs/C2_api.md."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import db
from config import settings
from controllers import admin, auth, channels, niches, predictions

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.require("jwt_secret")     # sin secreto no se arranca (no hay valor por defecto)
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="YT Trends API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, channels.router, niches.router, predictions.router, admin.router):
    app.include_router(r)


def _message(err: dict) -> tuple[str, str]:
    loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
    field = ".".join(loc) or "body"
    kind, msg = err["type"], err["msg"]
    if kind == "missing":
        return field, f"Falta el campo {field}"
    if kind == "extra_forbidden":
        return field, f"Campo no permitido: {field}"
    if kind == "value_error":
        return field, msg.removeprefix("Value error, ")
    if kind == "json_invalid":
        return field, "El cuerpo de la petición no es un JSON válido"
    return field, f"{field}: {msg}"


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        field, message = _message(e)
        errors.append({"field": field, "message": message})
    return JSONResponse(status_code=422, content={"detail": "; ".join(e["message"] for e in errors), "errors": errors})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


@app.get("/health")
def health():
    try:
        with db.pool.connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(503, "Base de datos no disponible")
    return {"status": "ok"}
