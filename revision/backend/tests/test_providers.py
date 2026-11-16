"""Fournisseurs Gemini et Groq, sans réseau : on remplace httpx.request par un faux serveur."""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import Config
from app.services.llm import LLMError, LLMRequest, build_llm
from app.services.llm import gemini as gemini_mod
from app.services.llm import groq as groq_mod
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqProvider


class FakeServer:
    def __init__(self, monkeypatch, responder):
        self.calls: list[dict] = []
        self.responder = responder
        monkeypatch.setattr(httpx, "request", self._request)

    def _request(self, method, url, headers=None, timeout=None, json=None, params=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "json": json})
        result = self.responder(method, url, json)
        if isinstance(result, Exception):
            raise result
        status, body = result[0], result[1]
        extra = result[2] if len(result) > 2 else {}
        return httpx.Response(status, json=body, headers=extra, request=httpx.Request(method, url))


def _req(**kw) -> LLMRequest:
    base = dict(task="t", system="Tu es professeur.", messages=[{"role": "user", "content": "Bonjour"}])
    return LLMRequest(**{**base, **kw})


GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "réflexion", "thought": True}, {"text": '{"a": 1}'}]}, "finishReason": "STOP"}]}


def test_gemini_request_shape_and_answer(monkeypatch):
    server = FakeServer(monkeypatch, lambda *_: (200, GEMINI_OK))
    provider = GeminiProvider("CLE", "gemini-3.6-flash")
    messages = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q2"},
    ]
    assert provider.generate(_req(messages=messages, images=[(b"img", "image/jpeg")])) == '{"a": 1}'
    call = server.calls[0]
    assert call["url"].endswith("/v1beta/models/gemini-3.6-flash:generateContent")
    assert call["headers"]["x-goog-api-key"] == "CLE" and "CLE" not in call["url"]
    body = call["json"]
    assert body["systemInstruction"] == {"parts": [{"text": "Tu es professeur."}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["contents"][2]["parts"][1]["inlineData"]["mimeType"] == "image/jpeg"
    assert len(body["contents"][0]["parts"]) == 1, "les images accompagnent le dernier message"
    assert body["generationConfig"] == {"responseMimeType": "application/json"}


@pytest.mark.parametrize(
    "status, body, kind",
    [
        (400, {"error": {"message": "bad key", "details": [{"reason": "API_KEY_INVALID"}]}}, "auth"),
        (403, {"error": {"message": "forbidden"}}, "auth"),
        (429, {"error": {"message": "quota"}}, "rate_limit"),
        (503, {"error": {"message": "overloaded"}}, "server"),
        (200, {"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"),
        (200, {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}, "bad_output"),
    ],
)
def test_gemini_errors(monkeypatch, status, body, kind):
    FakeServer(monkeypatch, lambda *_: (status, body))
    with pytest.raises(LLMError) as err:
        GeminiProvider("CLE", "gemini-3.6-flash").generate(_req())
    assert err.value.kind == kind


def test_gemini_network_error(monkeypatch):
    FakeServer(monkeypatch, lambda *_: httpx.ConnectError("pas de réseau"))
    with pytest.raises(LLMError) as err:
        GeminiProvider("CLE", "gemini-3.6-flash").generate(_req())
    assert err.value.kind == "network" and err.value.transient


def test_gemini_replaces_a_retired_model(monkeypatch):
    models = {
        "models": [
            {"name": "models/gemini-3.6-flash-lite", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-4.0-flash-preview", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]},
        ]
    }

    def responder(method, url, body):
        if method == "GET":
            return 200, models
        if "gemini-old" in url:
            return 404, {"error": {"message": "model not found"}}
        return 200, GEMINI_OK

    server = FakeServer(monkeypatch, responder)
    provider = GeminiProvider("CLE", "gemini-old")
    assert provider.generate(_req()) == '{"a": 1}'
    assert provider.model == "gemini-3.8-flash", "le flash stable le plus récent"
    assert [c["method"] for c in server.calls] == ["POST", "GET", "POST"]


def test_gemini_retries_without_json_option_when_rejected(monkeypatch):
    def responder(method, url, body):
        if "generationConfig" in body:
            return 400, {"error": {"message": "Unknown field responseMimeType"}}
        return 200, GEMINI_OK

    server = FakeServer(monkeypatch, responder)
    assert GeminiProvider("CLE", "gemini-3.6-flash").generate(_req()) == '{"a": 1}'
    assert len(server.calls) == 2


GROQ_MODELS = {"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.1-8b-instant"}, {"id": "llama-3.3-70b-versatile"}, {"id": "meta-llama/llama-4-scout-17b-16e-instruct"}]}


def _groq_ok(text: str):
    return 200, {"choices": [{"message": {"content": text}}]}


def test_groq_auto_model_and_request_shape(monkeypatch):
    def responder(method, url, body):
        return (200, GROQ_MODELS) if method == "GET" else _groq_ok('{"a": 1}')

    server = FakeServer(monkeypatch, responder)
    provider = GroqProvider("CLE", "auto", "auto")
    assert provider.generate(_req()) == '{"a": 1}'
    post = server.calls[-1]
    assert post["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert post["headers"]["Authorization"] == "Bearer CLE"
    assert post["json"]["model"] == "llama-3.3-70b-versatile"
    assert post["json"]["messages"][0] == {"role": "system", "content": "Tu es professeur."}
    assert post["json"]["response_format"] == {"type": "json_object"}

    # Avec une image : modèle vision, pas de mode JSON.
    provider.generate(_req(images=[(b"img", "image/jpeg")], json_mode=False))
    post = server.calls[-1]
    assert post["json"]["model"] == "meta-llama/llama-4-scout-17b-16e-instruct"
    assert post["json"]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "response_format" not in post["json"]


def test_groq_recovers_malformed_json(monkeypatch):
    failed = r'{"f": "$\frac{1}{2}$"}'

    def responder(method, url, body):
        return 400, {"error": {"message": "invalid json", "code": "json_validate_failed", "failed_generation": failed}}

    FakeServer(monkeypatch, responder)
    assert GroqProvider("CLE", "llama-3.3-70b-versatile", "").generate(_req()) == failed


def test_groq_errors(monkeypatch):
    FakeServer(monkeypatch, lambda *_: (429, {"error": {"message": "rate"}}, {"retry-after": "7"}))
    with pytest.raises(LLMError) as err:
        GroqProvider("CLE", "llama-3.3-70b-versatile", "").generate(_req())
    assert err.value.kind == "rate_limit" and err.value.retry_after == 7

    FakeServer(monkeypatch, lambda *_: (401, {"error": {"message": "invalid api key"}}))
    with pytest.raises(LLMError) as err:
        GroqProvider("CLE", "llama-3.3-70b-versatile", "").generate(_req())
    assert err.value.kind == "auth"


def test_groq_without_vision_model(monkeypatch):
    FakeServer(monkeypatch, lambda *_: (200, {"data": [{"id": "llama-3.1-8b-instant"}]}))
    with pytest.raises(LLMError) as err:
        GroqProvider("CLE", "auto", "auto").generate(_req(images=[(b"img", "image/jpeg")], json_mode=False))
    assert err.value.kind == "no_vision"


def _config(**kw) -> Config:
    base = dict(
        data_dir=None, llm_provider="auto", gemini_api_key="", gemini_model="gemini-3.6-flash", groq_api_key="",
        groq_model="auto", groq_vision_model="auto", youtube_api_key="", port=8765, run_worker=False, lesson_max_chars=30000,
    )
    return Config(**{**base, **kw})


def test_provider_order_and_fallback(monkeypatch):
    assert build_llm(_config()).configured is False
    assert [p.name for p in build_llm(_config(gemini_api_key="g", groq_api_key="q")).providers] == ["gemini", "groq"]
    assert [p.name for p in build_llm(_config(gemini_api_key="g", groq_api_key="q", llm_provider="groq")).providers] == ["groq", "gemini"]
    assert build_llm(_config(groq_api_key="q")).name == "groq"

    # Gemini saturé : la demande part chez Groq.
    def responder(method, url, body):
        if "googleapis" in url:
            return 429, {"error": {"message": "quota"}}
        return (200, GROQ_MODELS) if method == "GET" else _groq_ok('{"ok": true}')

    FakeServer(monkeypatch, responder)
    llm = build_llm(_config(gemini_api_key="g", groq_api_key="q"))
    assert llm.generate_json(_req()) == {"ok": True}


def test_no_api_key_ever_appears_in_source():
    import pathlib

    root = pathlib.Path(gemini_mod.__file__).parents[2]
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "AIza" not in text and "gsk_" not in text, path
    assert json.dumps({"k": groq_mod.API_ROOT})  # modules importables


def test_gemini_falls_back_to_another_model_when_overloaded(monkeypatch):
    models = {"models": [
        {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
    ]}

    def responder(method, url, body):
        if method == "GET":
            return 200, models
        if "gemini-3.6-flash" in url:
            return 503, {"error": {"message": "This model is currently experiencing high demand."}}
        return 200, GEMINI_OK

    server = FakeServer(monkeypatch, responder)
    provider = GeminiProvider("CLE", "gemini-3.6-flash")
    assert provider.generate(_req()) == '{"a": 1}'
    assert server.calls[-1]["url"].endswith("gemini-2.5-flash:generateContent")
    assert provider.model == "gemini-3.6-flash", "le modèle principal reste le même pour les appels suivants"


def test_gemini_overload_without_alternative_is_transient(monkeypatch):
    def responder(method, url, body):
        if method == "GET":
            return 200, {"models": [{"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]}]}
        return 503, {"error": {"message": "high demand"}}

    FakeServer(monkeypatch, responder)
    with pytest.raises(LLMError) as err:
        GeminiProvider("CLE", "gemini-3.6-flash").generate(_req())
    assert err.value.kind == "server" and err.value.transient
