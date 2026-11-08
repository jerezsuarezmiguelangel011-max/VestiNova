"""Prepara una incidencia CU13 ficticia y reversible en vestinova_pruebas.

No crea ventas, cargos, reservas confirmadas, compromisos ni movimientos de stock.
Sirve solo para comprobar la interfaz y la resolución autorizada de CU13.

Uso:
    python -m scripts.seed_cu13_conflict_demo
    python -m scripts.seed_cu13_conflict_demo --cleanup
"""
import argparse
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import Cliente, Empresa, Existencia, Sucursal, VarianteProducto
from app.operacion_sin_conexion.caja.online import SyncIncident
from scripts.demo_environment import use_demo_database


TAG = "DEMO CU13 (PRUEBA SIN COBRO):"
INCIDENT_ID = str(uuid5(NAMESPACE_URL, "vestinova:demo:cu13:reserva-andina-conflicto"))
OPERATION_ID = str(uuid5(NAMESPACE_URL, "vestinova:demo:cu13:reserva-offline-andina"))


def prepare(session, *, cleanup: bool) -> str:
    company = session.scalar(select(Empresa).where(Empresa.slug == "demo-moda-andina"))
    if company is None:
        raise ValueError("Faltan los datos demo. Ejecuta primero scripts.seed_demo.")
    branch = session.scalar(select(Sucursal).where(
        Sucursal.empresa_id == company.id, Sucursal.codigo == "CENTRO"))
    client = session.scalar(select(Cliente).where(
        Cliente.empresa_id == company.id, Cliente.correo == "cliente.andina@vestinova.test"))
    if branch is None or client is None:
        raise ValueError("Faltan Andina Centro o su cliente de demostración.")

    existing = session.get(SyncIncident, INCIDENT_ID)
    if existing is not None:
        if (existing.empresa_id != company.id or
                existing.sucursal_id != branch.id or
                existing.tipo != "RESERVA" or
                existing.operacion_id != OPERATION_ID or
                not existing.motivo.startswith(TAG)):
            raise ValueError("El UUID de prueba coincide con un registro ajeno; no se modifica.")
        if cleanup:
            session.delete(existing)
            return "Incidencia CU13 de demostración eliminada (sin alterar inventario)."
        return ("La incidencia demo ya existe; estado actual: "
                f"{existing.estado}. Para empezar nuevamente, ejecuta primero --cleanup.")
    if cleanup:
        return "No existe una incidencia CU13 de demostración que eliminar."

    # La variante no se modifica. Se pide más de lo disponible para ilustrar
    # una reserva que hubiese sido rechazada al reconectarse.
    selection = session.execute(select(Existencia, VarianteProducto).join(
        VarianteProducto,
        (Existencia.variante_id == VarianteProducto.id) &
        (Existencia.empresa_id == VarianteProducto.empresa_id),
    ).where(
        Existencia.empresa_id == company.id,
        Existencia.sucursal_id == branch.id,
    ).order_by(Existencia.cantidad.asc(), Existencia.variante_id.asc())).first()
    if selection is None:
        raise ValueError("La sucursal demo no tiene existencias preparadas.")
    balance, variant = selection
    requested = balance.cantidad + 1
    original = {
        "id": OPERATION_ID,
        "sucursal_id": branch.id,
        "cliente_id": client.id,
        "lineas": [{"variante_id": variant.id, "cantidad": requested}],
        "origen": "WEB_OFFLINE",
        "escenario": "DEMO: solicitud local ficticia; nunca enviada ni cobrada",
    }
    incident = SyncIncident(
        id=INCIDENT_ID,
        empresa_id=company.id,
        sucursal_id=branch.id,
        usuario_id=None,
        cliente_id=client.id,
        tipo="RESERVA",
        operacion_id=OPERATION_ID,
        huella="demo-cu13-reserva-offline-sin-cobro",
        datos_originales=original,
        motivo=(f"{TAG} Reserva offline solicitó {requested} unidad(es) de variante "
                f"#{variant.id} cuando el stock físico demo era {balance.cantidad}; "
                "pendiente de resolución documentada."),
        estado="CONFLICTO",
    )
    session.add(incident)
    return (
        "Incidencia ficticia creada para Moda Andina Demo / Andina Centro.\n"
        f"  Tipo: RESERVA | Estado: CONFLICTO | ID: {INCIDENT_ID}\n"
        "  No se registró ninguna venta, ningún pago ni cambio en inventario."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Caso CU13 aislado para la base de pruebas.")
    parser.add_argument("--cleanup", action="store_true",
                        help="Elimina solo la incidencia sintética identificada por el script.")
    args = parser.parse_args()

    use_demo_database()  # Valida y fija exclusivamente vestinova_pruebas.
    engine = build_engine(Settings.from_env())
    try:
        with build_session_factory(engine).begin() as session:
            message = prepare(session, cleanup=args.cleanup)
        print("Base de demostración: vestinova_pruebas")
        print(message)
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(f"No se completó la preparación de CU13: {exc}")
        raise SystemExit(1) from None
