"""Configuración central: lee las variables del archivo .env de la raíz del proyecto."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    model_keep_last: int = int(os.getenv("MODEL_KEEP_LAST", "3"))
    cors_origins: list[str] = field(default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "*")))

    def require(self, name: str) -> str:
        """Devuelve el valor o falla con un mensaje claro (ej. settings.require('jwt_secret'))."""
        value = getattr(self, name)
        if not value:
            raise RuntimeError(f"Falta {name.upper()} en el archivo .env")
        return value


settings = Settings()
