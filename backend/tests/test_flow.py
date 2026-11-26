"""Prueba 7: flujo completo de ML, de la captura a la visualización de un resultado generado por el modelo."""
from conftest import connect, login, make_user
from synth import seed_training_data


def test_ml_flow_end_to_end(client, conn):
    from services.training import train_from_db
    make_user(conn, "admin_t", role="admin")
    make_user(conn, "ana_01")
    h_admin, h_ana = login(client, "admin_t"), login(client, "ana_01")

    seed_training_data(conn)
    assert client.get("/admin/model", headers=h_admin).json() == {"active": None}
    assert client.post("/predict", headers=h_ana, json={"niche_id": 1, "title": "Truco gratis", "duration_s": 600,
                                                       "publish_hour": 18}).status_code == 503

    run1, res = train_from_db(conn)
    m = client.get("/admin/model", headers=h_admin).json()["active"]
    assert m["id"] == run1 and m["metrics"]["auc_mean"] > 0.65 and m["n_channels"] == 60
    assert m["metrics"]["auc_mean"] > m["metrics"]["format_only_auc"]

    # el cliente captura su canal, confirma el nicho y consulta resultados
    r = client.post("/channels", json={"handle": "@canalgrande"}, headers=h_ana)
    assert r.status_code == 201 and r.json()["suggested_niche_id"] == 1
    cid = r.json()["id"]
    assert client.put(f"/channels/{cid}/niche", json={"niche_id": 1}, headers=h_ana).status_code == 200
    assert [c["id"] for c in client.get("/channels/mine", headers=h_ana).json()] == [cid]
    ov = client.get("/niches/1/overview", headers=h_ana).json()
    assert ov["niche_stats"]["n_channels"] >= 30 and ov["own"]["n_videos"] > 0 and len(ov["own_top_videos"]) <= 5
    topics = client.get("/niches/1/topics?limit=5", headers=h_ana).json()
    assert 0 < len(topics) <= 5 and {"term", "lift", "win_rate", "n_videos"} <= set(topics[0])
    assert any(t["term"] in ("gratis", "secreto", "increible", "truco", "rapido") for t in
               client.get("/niches/1/topics?limit=15", headers=h_ana).json())

    body = {"niche_id": 1, "duration_s": 600, "publish_hour": 18, "publish_weekday": 4}
    good = client.post("/predict", headers=h_ana, json={**body, "title": "Truco gratis increible"}).json()
    bad = client.post("/predict", headers=h_ana, json={**body, "title": "Vlog parte resumen semana"}).json()
    assert good["score"] > bad["score"] and good["probability"] > bad["probability"]
    assert 0 <= good["score"] <= 100 and good["model_run_id"] == run1 and good["top_terms"]
    assert client.post("/predict", headers=h_ana, json={**body, "title": "ab"}).status_code == 422
    assert client.post("/predict", headers=h_ana, json={**body, "title": "ok titulo", "niche_id": 99}).status_code == 404
    hist = client.get("/predictions/mine", headers=h_ana).json()
    assert [p["title"] for p in hist][:2] == ["Vlog parte resumen semana", "Truco gratis increible"]
    assert client.get(f"/predictions/{good['prediction_id']}", headers=h_ana).json()["top_terms"]

    # panel del administrador: tabla y gráfica coherentes con los datos válidos
    st = client.get("/admin/stats", headers=h_admin).json()
    assert st["totals"]["predictions"] == 2 and st["totals"]["clients"] == 1
    row = next(c for c in st["per_client"] if c["username"] == "ana_01")
    assert row["n_predictions"] == 2 and row["channel_handle"] == "@canalgrande" and row["niche"] == "Gaming"
    assert sum(d["n_predictions"] for d in st["activity_by_day"]) == 2

    # reentrenar con los datos nuevos del cliente: el nuevo modelo queda activo y el servidor lo recarga
    run2, _ = train_from_db(conn)
    assert run2 != run1
    assert client.get("/admin/model", headers=h_admin).json()["active"]["id"] == run2
    again = client.post("/predict", headers=h_ana, json={**body, "title": "Truco gratis"}).json()
    assert again["model_run_id"] == run2
    assert conn.execute("SELECT COUNT(*) AS n FROM model_runs WHERE is_active").fetchone()["n"] == 1