"""Contrato de Stripe Checkout: no enviar parámetros de pago obsoletos.

Estas comprobaciones no realizan solicitudes a Stripe ni usan credenciales.
"""
import ast
import inspect
import textwrap

from app.compras_reservas.compras.stripe_checkout import create_checkout


def test_checkout_uses_dynamic_payment_methods_instead_of_removed_argument():
    tree = ast.parse(textwrap.dedent(inspect.getsource(create_checkout)))
    session_creates = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "Session"
    ]
    assert len(session_creates) == 1
    arguments = {kw.arg: kw.value for kw in session_creates[0].keywords}
    assert "payment_method_types" not in arguments
    assert "automatic_payment_methods" not in arguments
    assert {"api_key", "idempotency_key", "mode", "client_reference_id",
            "metadata", "line_items", "success_url", "cancel_url"} <= set(arguments)
    assert isinstance(arguments["mode"], ast.Constant)
    assert arguments["mode"].value == "payment"


def test_checkout_keeps_versioned_idempotency_on_sandbox_retries():
    source = inspect.getsource(create_checkout)
    assert "vestinova-cu09-v2-" in source
    assert "sk_live_" not in source
