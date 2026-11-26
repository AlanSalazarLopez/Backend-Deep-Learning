"""Utilidades compartidas por los scripts (se ejecutan desde backend/: python -m scripts.<nombre>)."""
import psycopg
from psycopg.rows import dict_row

from config import ROOT, settings

SCHEMA_FILE = ROOT / "docs" / "C1_esquema_bd.sql"


def connect():
    return psycopg.connect(settings.require("database_url"), row_factory=dict_row, prepare_threshold=None)
