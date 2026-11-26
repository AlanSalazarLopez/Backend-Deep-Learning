"""Crea el primer administrador directamente en la BD, con el mismo hash Argon2id que el registro.

Uso (desde backend/):
  python -m scripts.init_admin --username admin --name "Administrador"
  python -m scripts.init_admin --username ana_01 --promote     # convierte a un usuario existente en admin
"""
import argparse
import getpass

from pydantic import ValidationError

from models import user as user_model
from models.user import RegisterIn
from scripts._common import connect


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", default="admin")
    ap.add_argument("--name", default="Administrador")
    ap.add_argument("--promote", action="store_true", help="promueve a un usuario que ya existe")
    args = ap.parse_args()

    with connect() as conn:
        if args.promote:
            row = user_model.get_auth_row(conn, args.username)
            if not row:
                raise SystemExit(f"No existe el usuario {args.username}.")
            user_model.set_role(conn, row["id"], "admin")
            conn.commit()
            print(f"{args.username} ahora es administrador.")
            return
        pw = getpass.getpass("Contraseña del administrador: ")
        if pw != getpass.getpass("Repite la contraseña: "):
            raise SystemExit("Las contraseñas no coinciden.")
        try:
            data = RegisterIn(username=args.username, password=pw, name=args.name)   # mismas reglas que el registro
        except ValidationError as e:
            raise SystemExit(e.errors()[0]["msg"].removeprefix("Value error, "))
        if user_model.get_auth_row(conn, data.username):
            raise SystemExit("Ese usuario ya existe (usa --promote para convertirlo en admin).")
        user_model.create(conn, data.username, data.name, data.password, role="admin")
        conn.commit()
        print(f"Administrador {data.username} creado.")


if __name__ == "__main__":
    main()
