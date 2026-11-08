"""Configura solo las variables de IA, con clave oculta y prueba real del proveedor."""
import argparse
import json
from getpass import getpass
import os
from pathlib import Path
import tempfile

from dotenv import dotenv_values, set_key
import httpx

from app.config import BACKEND_ROOT
from app.ia.client import AIConfig, available_models


def probe(config):
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        response = client.post(config.base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + config.key} if config.key else {},
            json={"model": config.model, "messages": [{"role": "user", "content": 'Responde solo JSON: {"estado":"ok"}'}],
                  "response_format": {"type": "json_object"}, "max_tokens": 2048, "temperature": 0})
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    assert json.loads(content).get("estado") == "ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Comprueba la configuración existente sin guardarla de nuevo.")
    args = parser.parse_args()
    if args.check:
        probe(AIConfig.load())
        print("Proveedor de IA accesible con la configuración local; no se modificó .env.")
        return
    env_file = BACKEND_ROOT / ".env"
    if not env_file.is_file():
        raise ValueError("Primero configura PostgreSQL con scripts.configure_local.")
    values = dotenv_values(env_file, interpolate=False)
    print("CU21 - Configuración de la IA de VestiNova.")
    print("1. Abre https://aistudio.google.com/apikey e inicia sesión en tu cuenta Google.")
    print("2. Crea/selecciona una clave de Gemini y revisa el modelo y la cuota de tu proyecto.")
    print("3. Pega la clave solo en esta terminal. No se muestra al escribir.")
    base = input("URL compatible [Enter: Gemini]: ").strip() or values.get("AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai"
    key = getpass("Clave de IA (oculta): ").strip()
    if not key or any(character in key for character in "\r\n\x00"):
        raise ValueError("La clave no es válida.")
    originals = {name: os.environ.get(name) for name in ("AI_BASE_URL", "AI_MODEL", "AI_API_KEY")}
    try:
        os.environ.update(AI_BASE_URL=base, AI_MODEL="descubrimiento", AI_API_KEY=key)
        config = AIConfig.load()
        print("Consultando los modelos de texto disponibles para esta clave...")
        models = available_models(config)
        choices = models[:20]
        for index, model in enumerate(choices, 1):
            print(f"  {index}. {model}")
        selected = input("Modelo [Enter: opción 1; también puedes escribir un nombre del listado]: ").strip()
        if not selected:
            model = choices[0]
        elif selected.isdigit() and 1 <= int(selected) <= len(choices):
            model = choices[int(selected)-1]
        elif selected in models:
            model = selected
        else:
            raise ValueError("Elige un modelo del listado disponible.")
        config = AIConfig(config.base_url, model, config.key)
        print("Modelo elegido:", model)
        print("Comprobando acceso al modelo con una solicitud mínima, sin datos empresariales...")
        probe(config)
    finally:
        for name, value in originals.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    # Conservar formato y variables previas; reemplazo atómico solo tras la prueba.
    descriptor, name = tempfile.mkstemp(prefix=".env.ai-", dir=BACKEND_ROOT)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_bytes(env_file.read_bytes())
        for variable, value in (("AI_BASE_URL", config.base_url), ("AI_MODEL", config.model), ("AI_API_KEY", key)):
            set_key(temporary, variable, value, quote_mode="always")
        after = dotenv_values(temporary, interpolate=False)
        assert all(after.get(name) == value for name, value in values.items() if name not in {"AI_BASE_URL", "AI_MODEL", "AI_API_KEY"})
        os.replace(temporary, env_file)
    finally:
        temporary.unlink(missing_ok=True)
    print("IA configurada y proveedor verificado. PostgreSQL, JWT y cuentas se conservaron.")
    print("Reinicia la API para usar la configuración. La clave permanece solo en backend/.env.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Configuración cancelada; no se guardó una clave nueva.")
        raise SystemExit(130) from None
    except httpx.HTTPStatusError as error:
        messages = {400: "Revisa el modelo y la compatibilidad JSON.", 401: "Revisa la clave.", 403: "Revisa los permisos del proyecto o del modelo.",
                    404: "El modelo o la URL no están disponibles.", 429: "La cuota está agotada o el modelo no dispone de cuota en tu proyecto."}
        print("El proveedor rechazó la prueba. " + messages.get(error.response.status_code, "Revisa el estado del proveedor."))
        print("No se muestran claves ni respuestas privadas. .env no se cambió.")
        raise SystemExit(1) from None
    except Exception:
        print("No se completó la configuración. Revisa conexión, modelo del listado y URL; no se muestran datos privados.")
        raise SystemExit(1) from None
