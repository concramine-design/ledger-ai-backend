"""Fournisseur Groq (API compatible OpenAI)."""
from __future__ import annotations

import base64
import re
from typing import Any, Optional

import httpx

from .base import LLMError, LLMRequest, Provider

API_ROOT = "https://api.groq.com/openai/v1"

_NOT_CHAT = re.compile(r"whisper|guard|tts|compound|playai|orpheus|distil|safeguard", re.I)
_TEXT_PREFERENCES = [r"llama-3\.3-70b-versatile", r"gpt-oss-120b", r"kimi", r"qwen", r"70b", r"gpt-oss"]
_VISION_PREFERENCES = [r"llama-4-scout", r"llama-4-maverick", r"vision", r"qwen/qwen3"]


def pick_model(ids: list[str], preferences: list[str], allow_any: bool) -> Optional[str]:
    usable = [i for i in ids if not _NOT_CHAT.search(i)]
    for pattern in preferences:
        for model_id in usable:
            if re.search(pattern, model_id, re.I):
                return model_id
    return usable[0] if (usable and allow_any) else None


class GroqProvider(Provider):
    name = "groq"
    supports_vision = True  # sous réserve qu'un modèle vision existe (vérifié à l'appel)

    def __init__(self, api_key: str, model: str, vision_model: str, timeout: float = 120.0):
        self.api_key = api_key
        self.model = "" if model in ("", "auto") else model
        self.vision_model = "" if vision_model in ("", "auto") else vision_model
        self.timeout = timeout
        self._ids: list[str] | None = None

    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            return httpx.request(method, API_ROOT + path, headers=headers, timeout=self.timeout, **kw)
        except httpx.TimeoutException as exc:
            raise LLMError("network", f"délai dépassé : {exc}") from exc
        except httpx.TransportError as exc:
            raise LLMError("network", str(exc)) from exc

    def _model_ids(self) -> list[str]:
        if self._ids is None:
            resp = self._request("GET", "/models")
            if resp.status_code != 200:
                raise self._error(resp)
            self._ids = [
                str(m.get("id")) for m in resp.json().get("data", []) if m.get("active", True) and m.get("id")
            ]
        return self._ids

    @staticmethod
    def _error(resp: httpx.Response) -> LLMError:
        try:
            err = resp.json().get("error", {})
        except (ValueError, AttributeError):
            err = {}
        msg = str(err.get("message") or resp.text[:300])
        code = str(err.get("code") or "")
        status = resp.status_code
        if status in (401, 403):
            return LLMError("auth", msg)
        if status == 429:
            retry = resp.headers.get("retry-after")
            try:
                return LLMError("rate_limit", msg, float(retry) if retry else None)
            except ValueError:
                return LLMError("rate_limit", msg)
        if status == 413:
            return LLMError("rate_limit", msg, 60)
        if status >= 500:
            return LLMError("server", msg)
        if status == 404 or code == "model_not_found" or "decommissioned" in msg:
            return LLMError("model", msg)
        if code == "json_validate_failed":
            failed = str(err.get("failed_generation") or "")
            e = LLMError("json_failed", msg)
            e.failed_generation = failed  # type: ignore[attr-defined]
            return e
        return LLMError("bad_request", msg)

    def _messages(self, req: LLMRequest) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        last = len(req.messages) - 1
        for i, m in enumerate(req.messages):
            if i == last and req.images:
                content: list[dict[str, Any]] = [{"type": "text", "text": m["content"]}]
                for data, mime in req.images:
                    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
                    content.append({"type": "image_url", "image_url": {"url": url}})
                msgs.append({"role": m["role"], "content": content})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        return msgs

    def generate(self, req: LLMRequest) -> str:
        vision = bool(req.images)
        if vision and not self.vision_model:
            found = pick_model(self._model_ids(), _VISION_PREFERENCES, allow_any=False)
            if not found:
                raise LLMError("no_vision", "aucun modèle Groq ne lit les images")
            self.vision_model = found
        if not vision and not self.model:
            found = pick_model(self._model_ids(), _TEXT_PREFERENCES, allow_any=True)
            if not found:
                raise LLMError("config", "aucun modèle Groq utilisable trouvé")
            self.model = found

        json_mode = req.json_mode and not vision
        rediscovered = False
        for _ in range(3):
            body: dict[str, Any] = {
                "model": self.vision_model if vision else self.model,
                "messages": self._messages(req),
                "temperature": req.temperature,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            resp = self._request("POST", "/chat/completions", json=body)
            if resp.status_code == 200:
                choices = resp.json().get("choices") or []
                text = (choices[0].get("message") or {}).get("content") if choices else ""
                if not (text or "").strip():
                    raise LLMError("bad_output", "réponse vide")
                return text
            err = self._error(resp)
            if err.kind == "json_failed":
                failed = getattr(err, "failed_generation", "")
                if failed:
                    return failed  # sera réparé par la lecture tolérante du JSON
                raise LLMError("bad_output", err.detail)
            if err.kind == "model" and not rediscovered:
                rediscovered = True
                self._ids = None
                prefs = _VISION_PREFERENCES if vision else _TEXT_PREFERENCES
                found = pick_model(self._model_ids(), prefs, allow_any=not vision)
                if not found:
                    raise LLMError("no_vision" if vision else "config", err.detail)
                if vision:
                    self.vision_model = found
                else:
                    self.model = found
                continue
            if err.kind == "bad_request" and json_mode:
                json_mode = False
                continue
            if err.kind in ("model", "bad_request"):
                raise LLMError("server", err.detail)
            raise err
        raise LLMError("server", "échec répété de l'appel Groq")
