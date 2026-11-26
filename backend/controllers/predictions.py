import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

import db
from controllers.deps import get_current_user
from models import niche as niche_model
from models import prediction as pm
from models.common import validate_one, validate_rows
from models.prediction import PredictIn, PredictionOut
from models.user import UserOut
from services import model_store

router = APIRouter(tags=["predictions"])


@router.post("/predict", response_model=PredictionOut)
def predict(body: PredictIn, user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    from ml.service import predict as ml_predict
    if niche_model.get(conn, body.niche_id) is None:
        raise HTTPException(404, "Ese nicho no existe")
    active = model_store.get_active(conn)
    if active is None:
        raise HTTPException(503, "Todavía no hay un modelo entrenado")
    run_id, model = active
    tz = ZoneInfo(model.config["data"]["timezone"])
    weekday = body.publish_weekday if body.publish_weekday is not None else datetime.now(tz).weekday()
    res = ml_predict(model, title=body.title, duration_s=body.duration_s, publish_hour=body.publish_hour,
                     publish_weekday=weekday, niche_id=body.niche_id)
    row = conn.execute(
        f"INSERT INTO predictions (user_id, niche_id, model_run_id, title, duration_s, publish_hour, publish_weekday, "
        f"probability, score, top_terms) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING {pm.COLS}",
        (user.id, body.niche_id, run_id, body.title, body.duration_s, body.publish_hour, weekday,
         res.probability, res.score, json.dumps(res.top_terms))).fetchone()
    conn.commit()
    return PredictionOut.model_validate(row)


@router.get("/predictions/mine", response_model=list[PredictionOut])
def my_predictions(limit: int = Query(20, ge=1, le=100), user: UserOut = Depends(get_current_user),
                   conn=Depends(db.get_db)):
    rows = conn.execute(f"SELECT {pm.COLS} FROM predictions WHERE user_id = %s ORDER BY created_at DESC, id DESC "
                        f"LIMIT %s", (user.id, limit)).fetchall()
    return validate_rows(PredictionOut, [{**r, "id": r["prediction_id"]} for r in rows], "predictions")


@router.get("/predictions/{prediction_id}", response_model=PredictionOut)
def one_prediction(prediction_id: int, user: UserOut = Depends(get_current_user), conn=Depends(db.get_db)):
    # Solo el dueño: cambiar el id en la URL no da acceso a datos ajenos (ni siquiera a un admin).
    row = conn.execute(f"SELECT {pm.COLS} FROM predictions WHERE id = %s AND user_id = %s",
                       (prediction_id, user.id)).fetchone()
    if row is None:
        raise HTTPException(404, "Predicción no encontrada")
    return validate_one(PredictionOut, {**row, "id": row["prediction_id"]}, "predictions")
