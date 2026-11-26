"""Los scripts de línea de comandos, contra la BD de pruebas y con YouTube simulado."""
import sys

from conftest import FakeYouTube, login, make_user
from synth import seed_training_data


def run(module, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", [module.__name__, *argv])
    module.main()


def test_init_db_is_idempotent(monkeypatch):
    from scripts import init_db
    run(init_db, monkeypatch)
    run(init_db, monkeypatch)


def test_init_admin_and_seed_demo(client, conn, monkeypatch):
    from scripts import init_admin, seed_demo
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "Admin1234")
    run(init_admin, monkeypatch, "--username", "admin", "--name", "Administrador")
    row = conn.execute("SELECT role, password_hash FROM users WHERE username='admin'").fetchone()
    assert row["role"] == "admin" and row["password_hash"].startswith("$argon2id$")
    assert client.post("/auth/login", json={"username": "admin", "password": "Admin1234"}).json()["role"] == "admin"

    run(seed_demo, monkeypatch)
    assert client.post("/auth/login", json={"username": "cliente_demo", "password": "Cliente1234"}).json()["role"] == "client"
    h = login(client, "admin", "Admin1234")
    n = client.get("/admin/users", headers=h).json()["total"]
    run(seed_demo, monkeypatch, "--invalid")
    assert conn.execute("SELECT COUNT(*) AS c FROM users WHERE username=''").fetchone()["c"] == 1
    assert client.get("/admin/users", headers=h).json()["total"] == n        # el inválido no aparece
    run(seed_demo, monkeypatch, "--remove-invalid")
    assert conn.execute("SELECT COUNT(*) AS c FROM users WHERE username=''").fetchone()["c"] == 0


def test_ingest_script_filters_weak_channels(conn, monkeypatch, tmp_path, capsys):
    from scripts import ingest
    fake = FakeYouTube()
    fake.known = {"@canalbueno": 30, "@canalpobre": 4}
    monkeypatch.setattr(ingest, "YouTubeClient", lambda: fake)
    csv_file = tmp_path / "seed.csv"
    csv_file.write_text("handle,niche_slug\n@canalbueno,gaming\n@canalpobre,gaming\n@fantasma,gaming\n@x,noexiste\n",
                        encoding="utf-8")
    run(ingest, monkeypatch, "--csv", str(csv_file))
    out = capsys.readouterr().out
    rows = {r["handle"]: r for r in conn.execute("SELECT handle, source, niche_id, language FROM channels").fetchall()}
    assert "@canalbueno" in rows and rows["@canalbueno"]["source"] == "seed" and rows["@canalbueno"]["niche_id"] == 1
    assert "@canalpobre" not in rows and "descartado" in out and "no existe" in out and "nicho desconocido" in out
    assert conn.execute("SELECT COUNT(*) AS c FROM videos").fetchone()["c"] == 30
    run(ingest, monkeypatch, "--refresh")                                      # no duplica videos
    assert conn.execute("SELECT COUNT(*) AS c FROM videos").fetchone()["c"] == 30


def test_train_model_script(conn, monkeypatch, capsys):
    from scripts import train_model
    seed_training_data(conn)
    run(train_model, monkeypatch)
    out = capsys.readouterr().out
    assert "AUC en canales no vistos" in out and "activo" in out
    assert conn.execute("SELECT COUNT(*) AS c FROM model_runs WHERE is_active").fetchone()["c"] == 1
    for _ in range(3):                                                         # conserva solo los últimos 3 (MODEL_KEEP_LAST)
        run(train_model, monkeypatch, "--no-activate")
    assert conn.execute("SELECT COUNT(*) AS c FROM model_runs").fetchone()["c"] <= 4
    assert conn.execute("SELECT COUNT(*) AS c FROM model_runs WHERE is_active").fetchone()["c"] == 1
