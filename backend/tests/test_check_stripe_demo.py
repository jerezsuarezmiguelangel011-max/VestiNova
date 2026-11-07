from scripts.check_stripe_demo import status


def test_stripe_demo_diagnostic_does_not_echo_secrets():
    assert status("", prefix="sk_test_", minimum=12) == "FALTA"
    assert status("sk_live_not_allowed_here", prefix="sk_test_", minimum=12) == "FORMATO NO VÁLIDO PARA PRUEBAS"
    assert status("whsec_short", prefix="whsec_", minimum=8) == "FORMATO DE PRUEBA PRESENTE"
    assert status("sk_test_illustrative_secret_only", prefix="sk_test_", minimum=12) == "FORMATO DE PRUEBA PRESENTE"
