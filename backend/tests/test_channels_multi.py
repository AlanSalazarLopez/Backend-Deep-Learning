"""Bloque 2: varios canales por usuario, aislamiento entre clientes, consentimiento de entrenamiento y panel.
Insertan canales y videos directo en la BD (sin YouTube) y usan las fixtures client y conn de conftest.py."""
from conftest import login, make_user
from synth import seed_training_data


def _uid(conn, username):
    return conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()["id"]


def _add_channel(conn, user_id, handle, niche_id=1, share=True, source="client"):
    row = conn.execute(
        "INSERT INTO channels (user_id, yt_channel_id, handle, title, niche_id, source, language, share_for_training) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'es', %s) RETURNING id",
        (user_id, "UC" + handle.strip("@"), handle, "Canal " + handle.strip("@"), niche_id, source, share)).fetchone()
    conn.commit()
    return row["id"]


def _add_video(conn, channel_id, yt_id):
    conn.execute(
        "INSERT INTO videos (channel_id, yt_video_id, title, published_at, duration_s, views, is_short, fetched_at) "
        "VALUES (%s, %s, %s, now() - interval '10 days', 600, 1000, false, now())",
        (channel_id, yt_id, "Titulo de prueba " + yt_id))
    conn.commit()


def test_cliente_ve_solo_sus_canales_y_no_toca_los_ajenos(client, conn):
    make_user(conn, "ana_01")
    make_user(conn, "beto_01")
    ana, beto = _uid(conn, "ana_01"), _uid(conn, "beto_01")
    a1, a2 = _add_channel(conn, ana, "@ana_uno"), _add_channel(conn, ana, "@ana_dos", niche_id=3)
    b1 = _add_channel(conn, beto, "@beto_uno")
    h = login(client, "ana_01")

    assert sorted(c["id"] for c in client.get("/channels/mine", headers=h).json()) == sorted([a1, a2])
    assert client.get(f"/channels/{a1}", headers=h).status_code == 200
    # cambiar el id en la URL no da acceso a un canal ajeno
    assert client.get(f"/channels/{b1}", headers=h).status_code == 404
    assert client.put(f"/channels/{b1}/niche", json={"niche_id": 2}, headers=h).status_code == 404
    assert client.put(f"/channels/{b1}/training", json={"share": False}, headers=h).status_code == 404
    assert client.delete(f"/channels/{b1}", headers=h).status_code == 404
    row = conn.execute("SELECT niche_id, share_for_training FROM channels WHERE id = %s", (b1,)).fetchone()
    assert row["niche_id"] == 1 and row["share_for_training"] is True      # la BD no cambió


def test_cambiar_nicho_consentimiento_y_borrar(client, conn):
    make_user(conn, "ana_01")
    cid = _add_channel(conn, _uid(conn, "ana_01"), "@ana_uno")
    h = login(client, "ana_01")

    r = client.put(f"/channels/{cid}/niche", json={"niche_id": 3}, headers=h)
    assert r.status_code == 200 and r.json()["niche_id"] == 3
    assert client.put(f"/channels/{cid}/niche", json={"niche_id": 999}, headers=h).status_code == 404
    assert client.put(f"/channels/{cid}/niche", json={"niche_id": 3, "x": 1}, headers=h).status_code == 422

    r = client.put(f"/channels/{cid}/training", json={"share": False}, headers=h)
    assert r.status_code == 200 and r.json()["share_for_training"] is False
    assert client.put(f"/channels/{cid}/training", json={"share": "quizas"}, headers=h).status_code == 422

    assert client.delete(f"/channels/{cid}", headers=h).status_code == 204
    assert conn.execute("SELECT COUNT(*) AS n FROM channels WHERE id = %s", (cid,)).fetchone()["n"] == 0
    assert client.get(f"/channels/{cid}", headers=h).status_code == 404


def test_tope_y_duplicados_se_rechazan_antes_de_gastar_cuota(client, conn):
    from models.channel import MAX_CHANNELS_PER_USER
    make_user(conn, "ana_01")
    make_user(conn, "beto_01")
    ana, beto = _uid(conn, "ana_01"), _uid(conn, "beto_01")
    h_ana, h_beto = login(client, "ana_01"), login(client, "beto_01")

    _add_channel(conn, beto, "@canalgrande")
    r = client.post("/channels", json={"handle": "@CanalGrande"}, headers=h_beto)   # mismo handle, otra capitalización
    assert r.status_code == 409 and "Ya registraste" in r.json()["detail"]

    for i in range(MAX_CHANNELS_PER_USER):
        _add_channel(conn, ana, f"@canal_{i}")
    r = client.post("/channels", json={"handle": "@otrocanal"}, headers=h_ana)
    assert r.status_code == 409 and str(MAX_CHANNELS_PER_USER) in r.json()["detail"]


def test_overview_solo_con_canales_propios(client, conn):
    make_user(conn, "ana_01")
    make_user(conn, "beto_01")
    b1 = _add_channel(conn, _uid(conn, "beto_01"), "@beto_uno")
    h = login(client, "ana_01")
    assert client.get("/niches/1/overview", headers=h).status_code == 409                   # aún no tiene canales
    assert client.get(f"/niches/1/overview?channel_id={b1}", headers=h).status_code == 404  # canal ajeno


def test_consentimiento_filtra_cargas_agregadas_pero_no_las_de_un_canal(conn):
    from services.training import load_videos_df, sources
    make_user(conn, "ana_01")
    ana = _uid(conn, "ana_01")
    seed = _add_channel(conn, None, "@semilla", source="seed")
    si, no = _add_channel(conn, ana, "@ana_si", share=True), _add_channel(conn, ana, "@ana_no", share=False)
    for ch, v in ((seed, "v1"), (si, "v2"), (no, "v3")):
        _add_video(conn, ch, v)

    assert set(load_videos_df(conn)["channel_id"]) == {seed, si}
    assert set(load_videos_df(conn, niche_id=1)["channel_id"]) == {seed, si}
    assert set(load_videos_df(conn, channel_id=no)["channel_id"]) == {no}        # su dueño sí ve lo suyo
    assert set(load_videos_df(conn, shared_only=False)["channel_id"]) == {seed, si, no}
    s = sources(conn)
    assert s["canales_semilla"] == 1 and s["canales_clientes"] == 1 and s["videos_clientes"] == 1


def test_entrenamiento_guarda_de_donde_salieron_los_datos(conn):
    from services.training import train_from_db
    seed_training_data(conn)
    run_id, _ = train_from_db(conn)
    f = conn.execute("SELECT metrics->'fuentes' AS f FROM model_runs WHERE id = %s", (run_id,)).fetchone()["f"]
    assert set(f) == {"canales_semilla", "canales_clientes", "videos_semilla", "videos_clientes"}
    assert f["canales_semilla"] + f["canales_clientes"] >= 1


def test_panel_con_varios_canales_no_duplica_y_cuenta_solo_clientes_validos(client, conn):
    make_user(conn, "admin_t", role="admin")
    make_user(conn, "ana_01")
    ana = _uid(conn, "ana_01")
    c1, c2 = _add_channel(conn, ana, "@ana_uno", niche_id=1), _add_channel(conn, ana, "@ana_dos", niche_id=3)
    seed = _add_channel(conn, None, "@semilla", source="seed")
    _add_video(conn, c1, "v_cliente")
    _add_video(conn, seed, "v_semilla")
    # usuario inválido (prueba 5 de la rúbrica) con un canal: no debe contarse en nada
    bad = conn.execute("INSERT INTO users (username, password_hash, name, role) VALUES ('', 'x', '', 'superadmin') "
                       "RETURNING id").fetchone()["id"]
    _add_channel(conn, bad, "@invalido")

    h = login(client, "admin_t")
    users = client.get("/admin/users", headers=h).json()
    assert users["total"] == 2                                   # admin + ana; el inválido se omite
    ana_rows = [u for u in users["items"] if u["username"] == "ana_01"]
    assert len(ana_rows) == 1                                    # varios canales no duplican al usuario
    assert "@ana_uno" in ana_rows[0]["channel_handle"] and "@ana_dos" in ana_rows[0]["channel_handle"]

    st = client.get("/admin/stats", headers=h).json()
    assert st["totals"]["channels"] == 2 and st["totals"]["seed_channels"] == 1
    assert st["totals"]["videos"] == 1 and st["totals"]["seed_videos"] == 1
    row = next(c for c in st["per_client"] if c["username"] == "ana_01")
    assert row["n_channels"] == 2 and set(row["niche"].split(", ")) == {"Gaming", "Educación"}
    by = {n["name"]: n for n in st["by_niche"]}
    assert by["Gaming"]["n_clients"] == 1 and by["Gaming"]["n_videos"] == 1
    assert by["Educación"]["n_clients"] == 1