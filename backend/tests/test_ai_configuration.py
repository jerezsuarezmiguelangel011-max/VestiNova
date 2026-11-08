import httpx
import pytest

from app.analitica_ia.provider import AIConfig, available_models
from scripts.configure_ai import probe


@pytest.fixture
def config():
    return AIConfig("https://generativelanguage.googleapis.com/v1beta/openai", "modelo-test", "clave-ficticia-solo-tests")


def install_transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_models_are_discovered_instead_of_assuming_a_retired_name(monkeypatch, config):
    def handler(request):
        assert request.method == "GET" and request.url.path.endswith("/models")
        assert request.headers["Authorization"] == "Bearer " + config.key
        return httpx.Response(200, json={"data": [{"id": "gemini-vigente-flash"}, {"id": "gemini-vigente-flash-lite"}, {"id": "modelo-image"}]})
    install_transport(monkeypatch, handler)
    assert available_models(config) == ["gemini-vigente-flash-lite", "gemini-vigente-flash"]


def test_native_gemini_catalog_fallback_uses_header_and_text_models(monkeypatch, config):
    def handler(request):
        assert config.key not in str(request.url)
        if "/openai/" in request.url.path:
            return httpx.Response(404, json={"error": "ruta no disponible"})
        assert request.headers["x-goog-api-key"] == config.key
        return httpx.Response(200, json={"models": [{"name": "models/gemini-texto-flash", "supportedGenerationMethods": ["generateContent"]}, {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}]})
    install_transport(monkeypatch, handler)
    assert available_models(config) == ["gemini-texto-flash"]


def test_probe_requires_usable_json_not_an_empty_success_response(monkeypatch, config):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}))
    with pytest.raises(ValueError):
        probe(config)
