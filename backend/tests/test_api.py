"""Las pruebas de la rúbrica (PDF, sección 9) y los controles de seguridad, contra Postgres real."""
from conftest import login, make_user


def count_users(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# ---- Prueba 1: iniciar sesión con ambas cuentas y con contraseña incorrecta
def test_login_roles_and_wrong_password(client, conn):
    make_user(conn, "admin_t", role="admin")
    r = client.post("/auth/register", json={"username": "ana_01", "password": "Clave1234", "name": "Ana"})
    assert r.status_code == 201 and r.json()["role"] == "client"
    a = client.post("/auth/login", json={"username": "admin_t", "password": "Clave1234"}).json()
    c = client.post("/auth/login", json={"username": "ana_01", "password": "Clave1234"}).json()
    assert a["role"] == "admin" and c["role"] == "client"
    bad = client.post("/auth/login", json={"username": "ana_01", "password": "Incorrecta1"})
    ghost = client.post("/auth/login", json={"username": "no_existe", "password": "Clave1234"})
    assert bad.status_code == ghost.status_code == 401 and bad.json() == ghost.json()  # no revela cuál falló


# ---- Prueba 2: promover a un cliente a administrador (persiste y aplica al volver a iniciar sesión)
def test_promote_persists(client, conn):
    make_user(conn, "admin_t", role="admin")
    ana = make_user(conn, "ana_01")
    h_admin, h_ana = login(client, "admin_t"), login(client, "ana_01")
    assert client.get("/admin/users", headers=h_ana).status_code == 403
    r = client.post(f"/admin/users/{ana['id']}/promote", headers=h_admin)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert conn.execute("SELECT role FROM users WHERE id=%s", (ana["id"],)).fetchone()["role"] == "admin"
    again = client.post("/auth/login", json={"username": "ana_01", "password": "Clave1234"}).json()
    assert again["role"] == "admin"
    assert client.get("/admin/users", headers=login(client, "ana_01")).status_code == 200
    assert client.post("/admin/users/9999/promote", headers=h_admin).status_code == 404


# ---- Prueba 3 y 4: dato inválido en el formulario / directo a la API (el backend lo rechaza y no guarda)
def test_invalid_data_rejected_and_not_saved(client, conn):
    casos = [
        ({"username": "ab", "password": "Clave1234", "name": "Ana"}, "username"),
        ({"username": "ana_01", "password": "corta", "name": "Ana"}, "password"),
        ({"username": "ana_01", "password": "sololetras", "name": "Ana"}, "password"),
        ({"username": "ana_01", "password": "Clave1234", "name": "  "}, "name"),
        ({"username": "ana_01", "password": "Clave1234"}, "name"),
    ]
    for body, field in casos:
        r = client.post("/auth/register", json=body)
        assert r.status_code == 422, body
        assert any(e["field"] == field for e in r.json()["errors"]), r.json()
        assert isinstance(r.json()["detail"], str) and r.json()["detail"]
    assert count_users(conn) == 0


def test_role_cannot_be_self_assigned(client, conn):
    r = client.post("/auth/register", json={"username": "ana_01", "password": "Clave1234", "name": "Ana", "role": "admin"})
    assert r.status_code == 422
    assert count_users(conn) == 0
    ana = make_user(conn, "ana_01")
    cid = conn.execute("INSERT INTO channels (user_id, yt_channel_id, handle, title, niche_id, source) "
                       "VALUES (%s,'UC1','@ana','Ana',1,'client') RETURNING id", (ana["id"],)).fetchone()["id"]
    conn.commit()
    # tampoco se puede cambiar el rol enviando campos extra en otras rutas
    h = login(client, "ana_01")
    assert client.put(f"/channels/{cid}/niche", json={"niche_id": 1, "role": "admin"}, headers=h).status_code == 422
    assert conn.execute("SELECT role FROM users WHERE id=%s", (ana["id"],)).fetchone()["role"] == "client"


# ---- Prueba 5: registro inválido insertado directo en la BD => la API lo excluye
def test_invalid_row_in_db_is_excluded(client, conn):
    make_user(conn, "admin_t", role="admin")
    make_user(conn, "ana_01")
    conn.execute("INSERT INTO users (username, password_hash, name, role) VALUES ('', 'x', '', 'superadmin')")
    from services.security import hash_password
    conn.execute("INSERT INTO users (username, password_hash, name, role) VALUES ('mal usuario!', %s, 'Mal', 'client')",
                 (hash_password("Clave1234"),))
    conn.commit()
    assert count_users(conn) == 4
    h = login(client, "admin_t")
    users = client.get("/admin/users", headers=h).json()
    assert users["total"] == 2 and {u["username"] for u in users["items"]} == {"admin_t", "ana_01"}
    assert client.get("/admin/stats", headers=h).json()["totals"]["users"] == 2
    bad_id = conn.execute("SELECT id FROM users WHERE username = 'mal usuario!'").fetchone()["id"]
    assert client.post(f"/admin/users/{bad_id}/promote", headers=h).status_code == 404
    # con contraseña correcta, un registro inválido tampoco puede iniciar sesión
    assert client.post("/auth/login", json={"username": "mal usuario!", "password": "Clave1234"}).status_code == 401
    assert conn.execute("SELECT role FROM users WHERE id=%s", (bad_id,)).fetchone()["role"] == "client"


def test_invalid_prediction_and_video_rows_excluded_from_stats(client, conn):
    make_user(conn, "admin_t", role="admin")
    ana = make_user(conn, "ana_01")
    conn.execute("INSERT INTO predictions (user_id, niche_id, title, duration_s, publish_hour, publish_weekday, probability, score) "
                 "VALUES (%s, 1, 'Titulo valido', 300, 10, 2, 0.4, 55)", (ana["id"],))
    conn.execute("INSERT INTO predictions (user_id, niche_id, title, duration_s, publish_hour, publish_weekday, probability, score) "
                 "VALUES (%s, 1, 'Titulo roto', -5, 99, 2, 7.0, 555)", (ana["id"],))
    ch = conn.execute("INSERT INTO channels (user_id, yt_channel_id, handle, title, niche_id, source) "
                      "VALUES (%s,'UC1','@ana','Ana',1,'client') RETURNING id", (ana["id"],)).fetchone()["id"]
    for i, views in enumerate([100, -50]):
        conn.execute("INSERT INTO videos (channel_id, yt_video_id, title, published_at, duration_s, views, fetched_at) "
                     "VALUES (%s,%s,'t',now()-interval '10 days',300,%s,now())", (ch, f"v{i}", views))
    conn.commit()
    st = client.get("/admin/stats", headers=login(client, "admin_t")).json()
    assert st["totals"]["predictions"] == 1 and st["totals"]["videos"] == 1
    row = next(c for c in st["per_client"] if c["username"] == "ana_01")
    assert row["n_predictions"] == 1 and row["niche"] == "Gaming"
    assert sum(d["n_predictions"] for d in st["activity_by_day"]) == 1 and len(st["activity_by_day"]) == 14
    assert next(n for n in st["by_niche"] if n["niche_id"] == 1) == {
        "niche_id": 1, "name": "Gaming", "n_clients": 1, "n_videos": 1, "n_predictions": 1}


# ---- Seguridad: hash Argon2id, sin secretos en respuestas, autenticación y permisos
def test_argon2_and_no_secrets_in_responses(client, conn):
    r = client.post("/auth/register", json={"username": "ana_01", "password": "Clave1234", "name": "Ana"})
    assert conn.execute("SELECT password_hash FROM users").fetchone()["password_hash"].startswith("$argon2id$")
    make_user(conn, "admin_t", role="admin")
    h = login(client, "admin_t")
    blob = r.text + client.get("/admin/users", headers=h).text + client.get("/auth/me", headers=h).text
    assert "argon2" not in blob.lower() and "password" not in blob.lower() and "hash" not in blob.lower()


def test_auth_required_and_admin_only(client, conn):
    make_user(conn, "ana_01")
    h = login(client, "ana_01")
    for path in ("/admin/users", "/admin/stats", "/admin/model"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer basura"}).status_code == 401
        assert client.get(path, headers=h).status_code == 403
    assert client.post("/admin/users/1/promote", headers=h).status_code == 403
    assert client.get("/niches").status_code == 401


# ---- Acceso a registros: cambiar un identificador no da acceso a datos ajenos
def test_idor_predictions(client, conn):
    a, b = make_user(conn, "ana_01"), make_user(conn, "beto_02")
    make_user(conn, "admin_t", role="admin")
    pid = conn.execute("INSERT INTO predictions (user_id, niche_id, title, duration_s, publish_hour, publish_weekday, "
                       "probability, score) VALUES (%s,1,'Mi idea',300,10,2,0.4,55) RETURNING id", (a["id"],)).fetchone()["id"]
    conn.commit()
    assert client.get(f"/predictions/{pid}", headers=login(client, "ana_01")).status_code == 200
    assert client.get(f"/predictions/{pid}", headers=login(client, "beto_02")).status_code == 404
    assert client.get(f"/predictions/{pid}", headers=login(client, "admin_t")).status_code == 404
    assert client.get("/predictions/mine", headers=login(client, "beto_02")).json() == []
    assert len(client.get("/predictions/mine", headers=login(client, "ana_01")).json()) == 1


def test_query_params_validated(client, conn):
    make_user(conn, "ana_01")
    h = login(client, "ana_01")
    assert client.get("/predictions/mine?limit=0", headers=h).status_code == 422
    assert client.get("/predictions/abc", headers=h).status_code == 422


def test_invalid_prediction_row_individual_query_is_controlled_error(client, conn):
    a = make_user(conn, "ana_01")
    pid = conn.execute("INSERT INTO predictions (user_id, niche_id, title, duration_s, publish_hour, publish_weekday, "
                       "probability, score) VALUES (%s,1,'roto',300,10,2,9.9,55) RETURNING id", (a["id"],)).fetchone()["id"]
    conn.commit()
    h = login(client, "ana_01")
    r = client.get(f"/predictions/{pid}", headers=h)
    assert r.status_code == 422 and "inválidos" in r.json()["detail"]
    assert client.get("/predictions/mine", headers=h).json() == []   # en listas se excluye


# ---- Canales (con YouTube simulado)
def test_channel_registration_rules(client, conn, fake_yt):
    make_user(conn, "ana_01"); make_user(conn, "beto_02")
    ha, hb = login(client, "ana_01"), login(client, "beto_02")
    assert client.post("/channels", json={"handle": "x"}, headers=ha).status_code == 422
    assert client.post("/channels", json={"handle": "@noexiste"}, headers=ha).status_code == 404
    fake_yt.fail = True
    assert client.post("/channels", json={"handle": "@canalgrande"}, headers=ha).status_code == 502
    fake_yt.fail = False
    assert conn.execute("SELECT COUNT(*) AS n FROM channels").fetchone()["n"] == 0   # nada a medias
    r = client.post("/channels", json={"handle": "canalgrande"}, headers=ha)
    assert r.status_code == 201
    body = r.json()
    assert body["handle"] == "@canalgrande" and body["videos_loaded"] == 30 and body["niche_id"] is None
    assert body["suggested_niche_id"] == 1                 # categoría 20 = Gaming
    assert body["share_for_training"] is True              # por defecto sus videos entran al entrenamiento
    big_id = body["id"]
    assert client.post("/channels", json={"handle": "@canalgrande"}, headers=ha).status_code == 409   # ya lo registró
    assert client.post("/channels", json={"handle": "@canalgrande"}, headers=hb).status_code == 409   # es de otro
    r2 = client.post("/channels", json={"handle": "@canalchico"}, headers=ha)      # un cliente puede tener varios
    assert r2.status_code == 201
    small = r2.json()
    assert small["suggested_niche_id"] is None             # menos de 10 videos: debe elegir de la lista
    assert client.post("/channels", json={"handle": "@canalchico"}, headers=hb).status_code == 409    # ya es de ana
    assert client.put(f"/channels/{small['id']}/niche", json={"niche_id": 999}, headers=ha).status_code == 404
    assert client.put(f"/channels/{small['id']}/niche", json={"niche_id": 3}, headers=ha).json()["niche_id"] == 3
    assert client.put(f"/channels/{big_id}/niche", json={"niche_id": 3}, headers=hb).status_code == 404   # no es de beto
    assert {c["handle"] for c in client.get("/channels/mine", headers=ha).json()} == {"@canalgrande", "@canalchico"}
    assert client.get("/channels/mine", headers=hb).json() == []   # cada quien ve los suyos