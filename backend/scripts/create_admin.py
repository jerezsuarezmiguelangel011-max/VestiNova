"""Alta explícita de personal; nunca guarda ni imprime contraseña en claro."""
import argparse
from getpass import getpass
import sys

from sqlalchemy import select

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import AccesoSucursal, Administrador, Empresa, MembresiaEmpresa, Sucursal
from app.password_policy import PASSWORD_POLICY_MESSAGE, validate_new_password
from app.schemas import normalizar_correo
from app.security import hash_password, verify_password


def main(argv: list[str] | tuple[str, ...] = ()) -> None:
    parser = argparse.ArgumentParser(description="Crea una cuenta local y su pertenencia explícita a empresa.")
    parser.add_argument("--empresa-id", type=int, help="Empresa activa; por defecto el entorno inicial de migración.")
    parser.add_argument("--rol", choices=["ADMINISTRADOR", "OPERADOR", "ENCARGADO_SUCURSAL", "CAJERO"], default="ADMINISTRADOR")
    parser.add_argument("--sucursal-id", action="append", type=int, default=[], help="Sucursales autorizadas del encargado, cajero u operador; se puede repetir.")
    parser.add_argument("--superadministrador", action="store_true", help="Concede gestión de plataforma; no evita la pertenencia a empresa.")
    args = parser.parse_args(argv)
    if args.empresa_id is not None and args.empresa_id <= 0:
        raise ValueError("El identificador de empresa debe ser positivo.")
    if args.rol == "ADMINISTRADOR" and args.sucursal_id:
        raise ValueError("El administrador de empresa accede a todas sus sucursales activas; no envíes --sucursal-id.")
    if any(branch_id <= 0 for branch_id in args.sucursal_id) or len(set(args.sucursal_id)) != len(args.sucursal_id):
        raise ValueError("Las sucursales deben ser identificadores positivos sin duplicados.")
    settings = Settings.from_env()
    nombre = input("Nombre de la cuenta de personal: ").strip()
    if not 3 <= len(nombre) <= 120:
        raise ValueError("El nombre debe tener entre 3 y 120 caracteres.")
    correo = normalizar_correo(input("Correo de la cuenta de personal: "))
    print(PASSWORD_POLICY_MESSAGE)
    password = getpass("Contraseña nueva (oculta): ")
    confirmacion = getpass("Repite la contraseña (oculta): ")
    if password != confirmacion:
        raise ValueError("Las contraseñas no coinciden.")
    validate_new_password(password)
    engine = build_engine(settings)
    try:
        with build_session_factory(engine)() as db:
            if db.scalar(select(Administrador.id).where(Administrador.correo == correo)) is not None:
                raise ValueError("Ese correo ya existe. No se modificó su cuenta ni contraseña.")
            company = db.get(Empresa, args.empresa_id) if args.empresa_id is not None else db.scalar(select(Empresa).where(Empresa.slug == "vestinova-inicial"))
            if company is None or not company.activo:
                raise ValueError("La empresa indicada no está activa. Aplica las migraciones o indica --empresa-id.")
            if args.sucursal_id:
                branch_ids = set(db.scalars(select(Sucursal.id).where(Sucursal.empresa_id == company.id, Sucursal.activo.is_(True), Sucursal.id.in_(args.sucursal_id))).all())
                if branch_ids != set(args.sucursal_id):
                    raise ValueError("Una sucursal no pertenece a la empresa activa indicada.")
            encoded = hash_password(password)
            if not verify_password(password, encoded):
                raise ValueError("No se pudo comprobar el hash de la contraseña.")
            # La primera cuenta instala la autoridad de plataforma. Las siguientes
            # solo la reciben mediante la opción local explícita, nunca por API de pertenencias.
            first_account = db.scalar(select(Administrador.id).limit(1)) is None
            administrator = Administrador(nombre=nombre, correo=correo, password_hash=encoded, activo=True, es_superadministrador=first_account or args.superadministrador)
            db.add(administrator)
            db.flush()
            db.add(MembresiaEmpresa(administrador_id=administrator.id, empresa_id=company.id, rol=args.rol, activo=True))
            db.flush()
            for branch_id in args.sucursal_id:
                db.add(AccesoSucursal(administrador_id=administrator.id, empresa_id=company.id, sucursal_id=branch_id))
            db.commit()
            print("Administrador creado con hash Argon2 y contraseña verificada." if args.rol == "ADMINISTRADOR" else "Cuenta de personal creada con hash Argon2 y contraseña verificada.")
            print(f"Cuenta ID {administrator.id}; empresa ID {company.id}; rol {args.rol}.")
            if administrator.es_superadministrador:
                print("La cuenta tiene gestión de plataforma; sus accesos comerciales siguen requiriendo pertenencia.")
            print("Acceso: http://127.0.0.1:4201/admin/login")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except ValueError as error:
        print(str(error))
        raise SystemExit(1) from None
    except (Exception, KeyboardInterrupt):
        print("No se completó el alta. Comprueba que .env y las migraciones estén configurados; no se mostraron credenciales.")
        raise SystemExit(1) from None
