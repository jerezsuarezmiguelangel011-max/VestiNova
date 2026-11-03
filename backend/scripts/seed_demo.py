"""Carga de datos repetible, exclusiva para la base local vestinova_pruebas.

No utiliza vestinova_mvp, no sobrescribe contraseñas ni borra registros.
Las compras y reservas se crean desde los flujos reales durante la prueba.
"""
from datetime import timedelta
from decimal import Decimal
from getpass import getpass
from uuid import uuid4

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
from sqlalchemy import func, select

from app.autenticacion_usuarios.permissions import ensure_company_roles
from app.config import BACKEND_ROOT, Settings
from app.db import build_engine, build_session_factory
from app.models import (
    AccesoSucursal, Administrador, CategoriaProducto, Cliente, Empresa,
    Existencia, LineaAbastecimiento, MembresiaEmpresa, MovimientoInventario,
    OrdenAbastecimiento, PlanSaaS, Producto, Promocion, PromocionProducto,
    Proveedor, Sucursal, SuscripcionEmpresa, VarianteProducto, utc_now,
)
from app.password_policy import PASSWORD_POLICY_MESSAGE, validate_new_password
from app.security import hash_password
from scripts.demo_environment import use_demo_database


DEMO_COMPANIES = (
    {
        "slug": "demo-moda-andina", "nombre": "Moda Andina Demo",
        "plan": "BASICO", "codigo": "ANDINA",
        "sucursales": (
            ("CENTRO", "Andina Centro", "Santa Cruz de la Sierra"),
            ("NORTE", "Andina Norte", "Santa Cruz de la Sierra"),
        ),
        "productos": (
            ("polera-clasica", "Polera clásica", "Poleras", "89.00", "M", "Blanco", 12),
            ("jean-recto", "Jean recto", "Jeans", "189.00", "L", "Azul", 4),
            ("chaqueta-corta", "Chaqueta corta", "Chaquetas", "249.00", "M", "Negro", 0),
        ),
    },
    {
        "slug": "demo-moda-urbana", "nombre": "Moda Urbana Demo",
        "plan": "PROFESIONAL", "codigo": "URBANA",
        "sucursales": (
            ("CENTRO", "Urbana Centro", "Santa Cruz de la Sierra"),
            ("NORTE", "Urbana Norte", "Santa Cruz de la Sierra"),
            ("SUR", "Urbana Sur", "Santa Cruz de la Sierra"),
        ),
        "productos": (
            ("polera-oversize", "Polera oversize", "Poleras", "119.00", "L", "Gris", 16),
            ("jean-slim", "Jean slim", "Jeans", "209.00", "M", "Negro", 5),
            ("chaqueta-denim", "Chaqueta denim", "Chaquetas", "289.00", "L", "Azul", 0),
        ),
    },
)


def _find_or_create(db, model, lookup: dict, defaults: dict):
    statement = select(model).filter_by(**lookup)
    existing = db.scalar(statement)
    if existing is not None:
        return existing
    record = model(**lookup, **defaults)
    db.add(record)
    db.flush()
    return record


def _user(db, email: str, name: str, password: str, *, saas: bool = False):
    existing = db.scalar(select(Administrador).where(Administrador.correo == email))
    if existing is not None:
        if existing.es_superadministrador != saas:
            raise ValueError("Conflicto de privilegios en una cuenta demo preexistente.")
        return existing
    user = Administrador(
        nombre=name, correo=email, password_hash=hash_password(password),
        activo=True, es_superadministrador=saas,
    )
    db.add(user)
    db.flush()
    return user


def _customer(db, company: Empresa, email: str, name: str, password: str):
    return _find_or_create(db, Cliente,
        {"empresa_id": company.id, "correo": email},
        {"nombre": name, "password_hash": hash_password(password), "activo": True},
    )


def _membership(db, company: Empresa, user: Administrador, roles: dict, role: str, branches):
    membership = _find_or_create(
        db, MembresiaEmpresa,
        {"administrador_id": user.id, "empresa_id": company.id},
        {"nombre": user.nombre, "rol": role, "rol_empresa_id": roles[role].id, "activo": True},
    )
    if membership.rol != role or membership.rol_empresa_id != roles[role].id:
        raise ValueError("Una cuenta de prueba ya tiene otro rol; no se sobrescribirá.")
    if role != "ADMINISTRADOR":
        for branch in branches:
            _find_or_create(db, AccesoSucursal,
                {"administrador_id": user.id, "empresa_id": company.id, "sucursal_id": branch.id}, {})
    return membership


def seed_data(db, password: str):
    """Solo altas ausentes por claves estables; no altera registros existentes."""
    validate_new_password(password)
    summaries = []
    saas_user = None
    for spec in DEMO_COMPANIES:
        plan = db.scalar(select(PlanSaaS).where(PlanSaaS.codigo == spec["plan"], PlanSaaS.activo.is_(True)))
        if plan is None:
            raise ValueError("Falta un plan SaaS activo. Ejecuta primero las migraciones.")
        company = _find_or_create(db, Empresa,
            {"slug": spec["slug"]},
            {"nombre": spec["nombre"], "activo": True},
        )
        subscription = _find_or_create(db, SuscripcionEmpresa,
            {"empresa_id": company.id},
            {"plan_id": plan.id, "estado": "ACTIVA", "inicia_en": utc_now(),
             "renueva_en": None, "actualizado_en": utc_now()},
        )
        if subscription.plan_id != plan.id:
            raise ValueError("El plan existente de una empresa demo no coincide; no se modificará.")
        roles = ensure_company_roles(db, company.id)
        branches = []
        for code, name, city in spec["sucursales"]:
            branch = _find_or_create(db, Sucursal,
                {"empresa_id": company.id, "codigo": code},
                {"nombre": name, "ciudad": city, "ubicacion": "Zona de demostración",
                 "contacto": "Solo pruebas", "activo": True},
            )
            branches.append(branch)
        if len(branches) > plan.max_sucursales:
            raise ValueError("El conjunto demo supera el límite del plan SaaS.")

        tag = "andina" if spec["codigo"] == "ANDINA" else "urbana"
        accounts = [
            ("admin", "Administrador", "ADMINISTRADOR"),
            ("encargado", "Encargado", "ENCARGADO_SUCURSAL"),
            ("cajero", "Cajero", "CAJERO"),
        ]
        admin_user = None
        for prefix, title, role in accounts:
            user = _user(db, f"{prefix}.{tag}@vestinova.test",
                         f"{title} Demo {tag.title()}", password)
            assigned = () if role == "ADMINISTRADOR" else branches[:1]
            _membership(db, company, user, roles, role, assigned)
            if role == "ADMINISTRADOR":
                admin_user = user
        if saas_user is None:
            saas_user = _user(db, "saas.demo@vestinova.test", "Superadmin Demo",
                              password, saas=True)
            _membership(db, company, saas_user, roles, "ADMINISTRADOR", ())
        _customer(db, company, f"cliente.{tag}@vestinova.test",
                  f"Cliente Demo {tag.title()}", password)

        categories = {}
        for name in ("Poleras", "Jeans", "Chaquetas"):
            categories[name] = _find_or_create(db, CategoriaProducto,
                {"empresa_id": company.id, "nombre_clave": name.casefold()},
                {"nombre": name, "descripcion": "Categoría de prueba", "activo": True},
            )
        first_variant = None
        first_product = None
        for slug, name, category, price, size, color, qty in spec["productos"]:
            product = _find_or_create(db, Producto,
                {"slug": f"demo-{tag}-{slug}"},
                {"empresa_id": company.id, "categoria_id": categories[category].id,
                 "nombre": name, "descripcion": "Prenda para demostraciones VestiNova.",
                 "precio": Decimal(price), "moneda": "BOB", "activo": True},
            )
            if product.empresa_id != company.id:
                raise ValueError("Producto demo asociado a una empresa inesperada.")
            variant = _find_or_create(db, VarianteProducto,
                {"empresa_id": company.id, "producto_id": product.id,
                 "talla": size, "color": color}, {"activo": True},
            )
            if first_variant is None:
                first_variant, first_product = variant, product
            for branch_index, branch in enumerate(branches):
                stock = max(qty - branch_index * 2, 0) if qty else 0
                existing = db.get(Existencia, (company.id, branch.id, variant.id))
                if existing is None:
                    db.add(Existencia(empresa_id=company.id, sucursal_id=branch.id,
                                     variante_id=variant.id, cantidad=stock))
                    if stock > 0:
                        db.add(MovimientoInventario(
                            id=str(uuid4()), empresa_id=company.id,
                            sucursal_id=branch.id, variante_id=variant.id,
                            usuario_id=admin_user.id, tipo="ENTRADA",
                            motivo="Carga inicial de demostración", delta=stock,
                            saldo_resultante=stock,
                        ))

        vendor = _find_or_create(db, Proveedor,
            {"empresa_id": company.id, "codigo": "PROV-DEMO"},
            {"nombre": f"Proveedor Demo {tag.title()}",
             "contacto": "Área comercial", "correo": f"proveedor.{tag}@vestinova.test",
             "telefono": "", "activo": True},
        )
        order = db.scalar(select(OrdenAbastecimiento).where(
            OrdenAbastecimiento.empresa_id == company.id,
            OrdenAbastecimiento.observaciones == "DEMO - orden pendiente",
        ))
        if order is None:
            order = OrdenAbastecimiento(
                empresa_id=company.id, sucursal_id=branches[0].id,
                proveedor_id=vendor.id, usuario_id=admin_user.id,
                estado="PENDIENTE", observaciones="DEMO - orden pendiente",
            )
            db.add(order)
            db.flush()
            db.add(LineaAbastecimiento(
                empresa_id=company.id, orden_id=order.id,
                variante_id=first_variant.id, cantidad_solicitada=8,
                cantidad_recibida=0, costo_unitario=Decimal("50.00"),
            ))

        promo = db.scalar(select(Promocion).where(
            Promocion.empresa_id == company.id,
            Promocion.nombre == "DEMO - descuento de temporada",
        ))
        if promo is None:
            now = utc_now()
            promo = Promocion(
                empresa_id=company.id, nombre="DEMO - descuento de temporada",
                tipo="PORCENTAJE", valor=Decimal("10.00"),
                inicio=now - timedelta(days=1), fin=now + timedelta(days=30),
                activo=True,
            )
            db.add(promo)
            db.flush()
            db.add(PromocionProducto(
                empresa_id=company.id, promocion_id=promo.id,
                producto_id=first_product.id,
            ))
        summaries.append((company.slug, spec["plan"], len(branches)))

    db.flush()
    return summaries


def prepare_demo_database(demo_url):
    with psycopg.connect(
        host=demo_url.host, port=demo_url.port or 5432,
        user=demo_url.username, password=demo_url.password,
        dbname="postgres", autocommit=True,
    ) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", ("vestinova_pruebas",)
        ).fetchone()
        if row is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier("vestinova_pruebas")))
            print("Creada la base aislada vestinova_pruebas.")
        else:
            print("Se conserva la base de demostración existente.")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")


def main():
    demo_url = use_demo_database()
    print("Destino de demostración: vestinova_pruebas (PostgreSQL local).")
    print("La base vestinova_mvp no se modificará.")
    prepare_demo_database(demo_url)
    print(PASSWORD_POLICY_MESSAGE)
    password = getpass("Contraseña para las cuentas de demostración (oculta): ")
    confirmation = getpass("Repite la contraseña (oculta): ")
    if password != confirmation:
        raise ValueError("Las contraseñas no coinciden.")
    validate_new_password(password)
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine).begin() as db:
            summaries = seed_data(db, password)
        print("DATOS DEMO PREPARADOS")
        for slug, plan, branches in summaries:
            print(f"  {slug}: {plan}; {branches} sucursales.")
        print("Cuentas de personal: saas.demo, admin, encargado y cajero por tienda.")
        print("Clientes: cliente.andina y cliente.urbana.")
        print("Dominio de correos: @vestinova.test")
        print("Se mantiene la contraseña original al ejecutar el script nuevamente.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        # Evitar imprimir URLs de PostgreSQL, credenciales o excepciones con parámetros.
        print("No se completó el poblado. No se modifica vestinova_mvp. "
              "Revisa PostgreSQL local, .env y las migraciones de demo.")
        raise SystemExit(1) from None
