"""Validación de datos leídos de la BD (docs/C2_api.md, sección 7, punto 5)."""
import logging

from fastapi import HTTPException
from pydantic import ValidationError

log = logging.getLogger("api")


def validate_rows(model, rows, what: str) -> list:
    """Valida cada fila con el modelo; las inválidas se OMITEN y se registran en el log."""
    ok = []
    for row in rows:
        try:
            ok.append(model.model_validate(row))
        except ValidationError as e:
            log.warning("Registro inválido excluido de %s (id=%s): %s", what, row.get("id"), e.errors()[0]["msg"])
    return ok


def validate_one(model, row, what: str):
    """Consulta individual: un registro inválido produce un error controlado (422), no un 500."""
    try:
        return model.model_validate(row)
    except ValidationError:
        log.warning("Registro inválido en consulta individual de %s (id=%s)", what, row.get("id"))
        raise HTTPException(422, "Registro con datos inválidos")


# Predicados SQL de validez para agregados (estadísticas calculadas solo con datos válidos).
VALID_VIDEO = "v.views >= 0 AND v.duration_s > 0 AND v.title <> '' AND v.published_at <= v.fetched_at"
VALID_PRED = ("p.probability BETWEEN 0 AND 1 AND p.score BETWEEN 0 AND 100 AND p.duration_s > 0 "
              "AND p.publish_hour BETWEEN 0 AND 23 AND p.title <> ''")
