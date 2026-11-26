"""Conexión a PostgreSQL con pool. Las escrituras hacen commit explícito en cada controlador."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import settings

pool: ConnectionPool | None = None


def open_pool() -> None:
    global pool
    if pool is None:
        pool = ConnectionPool(
            conninfo=settings.require("database_url"),
            min_size=1,
            max_size=5,
            timeout=30,
            open=False,
            check=ConnectionPool.check_connection,   # descarta conexiones cerradas por el proveedor
            kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 15},
        )
    pool.open(wait=True, timeout=30)


def close_pool() -> None:
    global pool
    if pool is not None:
        pool.close()
        pool = None


def get_db():
    """Dependencia de FastAPI: una conexión por petición. Sin commit explícito, no se guarda nada."""
    with pool.connection() as conn:
        yield conn
        conn.rollback()  # si el controlador ya hizo commit, esto no hace nada
