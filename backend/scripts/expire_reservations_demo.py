"""Vence reservas CU10 únicamente en vestinova_pruebas.

Uso: python -m scripts.expire_reservations_demo
No se conecta a produccion ni a vestinova_mvp.
Para operar sin visitas web, planificar su ejecución desde un programador externo.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import build_engine
from app.config import Settings
from scripts.demo_environment import use_demo_database


def main() -> None:
    use_demo_database()
    # La importación de online registra el modelo y hace disponibles sus reglas.
    from app.compras_reservas.reservas.online import ReservationRecord, expire_due

    engine = build_engine(Settings.from_env())
    total = 0
    try:
        with Session(engine) as db:
            companies = db.scalars(
                select(ReservationRecord.empresa_id)
                .where(ReservationRecord.estado == "CONFIRMADA")
                .distinct()
            ).all()
            for company_id in companies:
                try:
                    total += expire_due(db, company_id)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
    finally:
        engine.dispose()
    print(f"CU10 demo: {total} reserva(s) vencida(s) y compromiso(s) liberado(s).")


if __name__ == "__main__":
    main()
