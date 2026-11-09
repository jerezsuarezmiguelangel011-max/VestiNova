"""La IA solo propone un plan tipado; jamás suministra SQL ejecutable."""
from dataclasses import dataclass
from datetime import date
import json
import os
import re
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import HTTPException
import httpx
from pydantic import ValidationError

from app.config import BACKEND_ROOT


@dataclass(frozen=True)
class AIConfig:
    base_url: str
    model: str
    key: str

    @classmethod
    def load(cls):
        values = {**dotenv_values(BACKEND_ROOT / ".env", interpolate=False), **os.environ}
        base = (values.get("AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
        model = values.get("AI_MODEL") or ""
        key = values.get("AI_API_KEY") or ""
        parts = urlsplit(base)
        local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        valid = parts.scheme == "https" or (parts.scheme == "http" and local)
        if not valid or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("AI_BASE_URL debe usar HTTPS o HTTP local, sin credenciales ni parámetros.")
        if not key and not local:
            raise ValueError("Falta AI_API_KEY. Ejecuta python -m scripts.configure_ai.")
        if not model.strip() or len(model) > 120:
            raise ValueError("Configura un modelo de IA válido.")
        return cls(base, model, key)


def available_models(config: AIConfig) -> list[str]:
    """Descubre modelos sin fijar nombres que pueden ser retirados por el proveedor."""
    with httpx.Client(timeout=httpx.Timeout(15, connect=7), follow_redirects=False) as client:
        response = client.get(config.base_url + "/models", headers={"Authorization": "Bearer " + config.key} if config.key else {})
        native = response.status_code == 404 and urlsplit(config.base_url).hostname == "generativelanguage.googleapis.com"
        if native:
            response = client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": config.key})
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise ValueError("Listado demasiado grande.")
        payload = response.json()
        items = payload.get("models" if native else "data", [])
        names = []
        for item in items[:300]:
            if native and "generateContent" not in item.get("supportedGenerationMethods", []):
                continue
            name = item.get("name" if native else "id", "")
            if urlsplit(config.base_url).hostname == "generativelanguage.googleapis.com":
                name = name.removeprefix("models/")
            if re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", name) and name != "aqa" and not any(part in name.lower() for part in ("image", "audio", "tts", "embedding", "live", "robotic", "research", "computer-use", "transcrib", "banana")):
                names.append(name)
    if not names:
        raise ValueError("El proveedor no devolvió modelos de texto disponibles.")
    # Favorecer variantes de texto ligeras y estables; la cuota se comprueba en la prueba.
    def order(name):
        match = re.search(r"gemini-(\d+)(?:\.(\d+))?", name)
        version = (-int(match[1]), -int(match[2] or 0)) if match else (0, 0)
        return (0 if "flash-lite" in name else 1 if "flash" in name else 2,
                "preview" in name or "exp" in name, *version, name)
    return sorted(set(names), key=order)


def configured() -> bool:
    try:
        AIConfig.load()
        return True
    except ValueError:
        return False


class JSONClient:
    """Transporte común; no conoce tablas, empresas, credenciales de usuarios ni SQL."""
    def complete(self, system: str, prompt: str) -> dict:
        try:
            config = AIConfig.load()
        except ValueError:
            raise HTTPException(503, "La IA no está configurada. Ejecuta python -m scripts.configure_ai en el backend.") from None
        try:
            with httpx.Client(timeout=httpx.Timeout(25, connect=7), follow_redirects=False) as client:
                response = client.post(config.base_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + config.key} if config.key else {},
                    json={"model": config.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                          "response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": 2048})
            response.raise_for_status()
            if len(response.content) > 100_000:
                raise ValueError("Respuesta demasiado grande.")
            parsed = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(parsed, dict):
                raise ValueError("Se requiere un objeto JSON.")
            return parsed
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            raise HTTPException(503, "El proveedor de IA no pudo interpretar la solicitud. Revisa la configuración o inténtalo de nuevo.") from None
