"""Diagnóstico local de Stripe CU09 sin mostrar ni transmitir credenciales.

Uso: python -m scripts.check_stripe_demo
No conecta con Stripe, no genera pagos ni altera bases de datos.
"""
import os

from dotenv import dotenv_values
from app.config import BACKEND_ROOT


def status(value: str, *, prefix: str, minimum: int) -> str:
    if not value:
        return "FALTA"
    if not value.startswith(prefix) or len(value) <= minimum:
        return "FORMATO NO VÁLIDO PARA PRUEBAS"
    return "FORMATO DE PRUEBA PRESENTE"


def main() -> None:
    values = dotenv_values(BACKEND_ROOT / ".env", interpolate=False)
    secret = (os.environ.get("STRIPE_SECRET_KEY") or values.get("STRIPE_SECRET_KEY") or "").strip()
    webhook = (os.environ.get("STRIPE_WEBHOOK_SECRET") or values.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    secret_ok = status(secret, prefix="sk_test_", minimum=12)
    webhook_ok = status(webhook, prefix="whsec_", minimum=8)
    print("CU09 - Revisión local de configuración Stripe TEST")
    print("Clave de prueba:", secret_ok)
    print("Firma del webhook:", webhook_ok)
    if secret_ok == webhook_ok == "FORMATO DE PRUEBA PRESENTE":
        print("Configuración de formato lista. Aún se requiere verificar conexión real con Stripe,")
        print("eventos firmados y estado del pago; esta revisión NO realiza transacciones.")
    else:
        print("Checkout deshabilitado por seguridad: revisa backend/.env.")
        print("Ambas variables deben estar presentes. No compartas sus valores ni los subas a Git.")
    print("API de prueba: http://127.0.0.1:8001/api/tiendas/demo-moda-andina/compras/capacidades")


if __name__ == "__main__":
    main()
