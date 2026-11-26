"""Cuentas de prueba para la demostración y el registro inválido de la prueba 5 de la rúbrica.

Uso (desde backend/):
  python -m scripts.seed_demo                  # crea admin_demo y cliente_demo (si no existen)
  python -m scripts.seed_demo --invalid        # inserta DIRECTO en la BD un usuario inválido
  python -m scripts.seed_demo --remove-invalid # lo borra
"""
import argparse

from models import user as user_model
from scripts._common import connect

ACCOUNTS = [
    ("admin_demo", "Admin Demo", "Admin1234", "admin"),
    ("cliente_demo", "Cliente Demo", "Cliente1234", "client"),
    ("cliente_demo2", "Cliente Demo 2", "Cliente1234", "client"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--invalid", action="store_true")
    ap.add_argument("--remove-invalid", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        if args.invalid:
            conn.execute("INSERT INTO users (username, password_hash, name, role) VALUES ('', 'x', '', 'superadmin')")
            conn.commit()
            print("Usuario inválido insertado (username vacío, nombre vacío, rol 'superadmin').")
            print("GET /admin/users NO debe mostrarlo.")
            return
        if args.remove_invalid:
            conn.execute("DELETE FROM users WHERE username = ''")
            conn.commit()
            print("Usuario inválido borrado.")
            return
        print(f"{'usuario':<15} {'contraseña':<13} rol")
        for username, name, pw, role in ACCOUNTS:
            if not user_model.get_auth_row(conn, username):
                user_model.create(conn, username, name, pw, role)
            print(f"{username:<15} {pw:<13} {role}")
        conn.commit()


if __name__ == "__main__":
    main()
