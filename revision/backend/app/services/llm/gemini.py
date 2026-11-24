"""Fournisseur Google Gemini (API REST generateContent)."""
from __future__ import annotations

import base64
import re
from typing import Any, Optional

import httpx

from .base import LLMError, LLMRequest, Provider

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_EXCLUDED = ("lite", "image", "tts", "live", "audio", "embedding", "robotics", "computer")


def pick_model(models: list[dict[str, Any]], exclude: tuple[str, ...] = ()) -> Optional[str]:
    """Choisit le modèle « flash » stable le plus récent dans la liste renvoyée par l'API."""
    best: tuple[tuple[int, float], str] | None = None
    for m in models:
        name = str(m.get("name", "")).removeprefix("models/")
        if name in exclude:
            continue
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        match = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-[a-z0-9-]+)?", name)
        if not match or any(x in name for x in _EXCLUDED):
            continue
        stable = 0 if (match.group(2) or "") else 1  # sans suffixe = version stable
        rank = (stable, float(match.group(1)))
        if best is None or rank > best[0]:
            best = (rank, name)
    return best[1] if best else None


class GeminiProvider(Provider):
    name = "gemini"
    supports_vision = True

    def __init__(self, api_key: str, model: str, timeout: float = 120.0):
        self.api_key = api_key
        self.model = "" if model in ("", "auto") else model
        self.timeout = timeout
        self._discovered = False
        self._models: list[dict[str, Any]] | None = None

    # -- HTTP ---------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        try:
            return httpx.request(method, url, headers=self._headers(), timeout=self.timeout, **kw)
        except httpx.TimeoutException as exc:
            raise LLMError("network", f"délai dépassé : {exc}") from exc
        except httpx.TransportError as exc:
            raise LLMError("network", str(exc)) from exc

    def _list_models(self) -> list[dict[str, Any]]:
        if self._models is None:
            resp = self._request("GET", f"{API_ROOT}/models", params={"pageSize": 200})
            if resp.status_code != 200:
                raise self._error(resp)
            self._models = resp.json().get("models", [])
        return self._models

    def _fallback(self, current: str) -> Optional[str]:
        """Un autre modèle flash, pour contourner une surcharge passagère du modèle principal."""
        try:
            return pick_model(self._list_models(), exclude=(current,))
        except LLMError:
            return None

    def _discover(self) -> None:
        model = pick_model(self._list_models())
        if not model:
            raise LLMError("config", "aucun modèle Gemini utilisable trouvé")
        self.model = model
        self._discovered = True

    @staticmethod
    def _error(resp: httpx.Response) -> LLMError:
        try:
            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            err = data.get("error", {}) if isinstance(data, dict) else {}
        except ValueError:
            err = {}
        msg = str(err.get("message") or resp.text[:300])
        reasons = {d.get("reason") for d in err.get("details", []) if isinstance(d, dict)}
        status = resp.status_code
        if "API_KEY_INVALID" in reasons or status in (401, 403):
            return LLMError("auth", msg)
        if status == 429:
            retry = resp.headers.get("retry-after")
            return LLMError("rate_limit", msg, float(retry) if retry and retry.isdigit() else None)
        if status >= 500:
            return LLMError("server", msg)
        if status == 404:
            return LLMError("model", msg)
        return LLMError("bad_request", msg)

    # -- Génération ---------------------------------------------------------
    def _body(self, req: LLMRequest, with_config: bool) -> dict[str, Any]:
        contents = []
        last = len(req.messages) - 1
        for i, m in enumerate(req.messages):
            parts: list[dict[str, Any]] = [{"text": m["content"]}]
            if i == last:
                for data, mime in req.images:
                    parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}})
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
        body: dict[str, Any] = {"contents": contents}
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if with_config and req.json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        return body

    def generate(self, req: LLMRequest) -> str:
        if not self.model:
            self._discover()
        with_config = True
        model = self.model
        fell_back = False
        for _ in range(4):
            url = f"{API_ROOT}/models/{model}:generateContent"
            resp = self._request("POST", url, json=self._body(req, with_config))
            if resp.status_code == 200:
                return self._text(resp.json())
            err = self._error(resp)
            if err.kind in ("server", "rate_limit") and not fell_back:
                # Modèle surchargé (« high demand ») ou limite gratuite atteinte : chaque modèle Gemini a son
                # propre quota, on essaie donc tout de suite un autre modèle.
                fell_back = True
                alternative = self._fallback(model)
                if alternative:
                    model = alternative
                    continue
                raise err
            if err.kind == "model" and not self._discovered:
                self._discover()  # le modèle du .env n'existe plus : on en choisit un autre
                model = self.model
                continue
            if err.kind == "bad_request" and with_config:
                with_config = False  # option refusée par ce modèle : on demande le JSON par le prompt
                continue
            if err.kind in ("model", "bad_request"):
                raise LLMError("server", err.detail)
            raise err
        raise LLMError("server", "échec répété de l'appel Gemini")

    @staticmethod
    def _text(data: dict[str, Any]) -> str:
        if isinstance(data, list):
            data = data[0] if data else {}
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "")
            raise LLMError("blocked" if reason else "bad_output", f"aucune réponse ({reason})")
        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            finish = cand.get("finishReason", "")
            kind = "blocked" if finish in ("SAFETY", "PROHIBITED_CONTENT", "RECITATION") else "bad_output"
            raise LLMError(kind, f"réponse vide ({finish})")
        return text
