"""Fournisseur Claude (API Anthropic, SDK officiel Python)."""
from __future__ import annotations

import base64
from typing import Any

import anthropic

from .base import LLMError, LLMRequest, Provider

# Repli automatique côté serveur si le modèle décline une demande (filtres de sécurité).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

# Échanges courts où la rapidité compte plus que la réflexion : effort réduit.
QUICK_TASKS = {"chat", "explique_question", "ocr"}


class ClaudeProvider(Provider):
    name = "claude"
    supports_vision = True

    def __init__(self, api_key: str, model: str, effort: str = "medium", timeout: float = 300.0):
        self.model = model or "claude-opus-5-5"
        self.effort = effort or "medium"
        # Les nouvelles tentatives sont gérées par la file de génération : une seule ici.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)

    def _messages(self, req: LLMRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        last = len(req.messages) - 1
        for i, m in enumerate(req.messages):
            if i == last and req.images:
                content: list[dict[str, Any]] = [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": base64.standard_b64encode(data).decode()},
                    }
                    for data, mime in req.images
                ]
                content.append({"type": "text", "text": m["content"]})
                messages.append({"role": m["role"], "content": content})
            else:
                messages.append({"role": m["role"], "content": m["content"]})
        return messages

    def generate(self, req: LLMRequest) -> str:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16000,
            "messages": self._messages(req),
            "output_config": {"effort": "low" if req.task in QUICK_TASKS else self.effort},
        }
        if req.system:
            params["system"] = req.system
        if self.model in FALLBACK_MODELS:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        try:
            if "betas" in params:
                response = self.client.beta.messages.create(**params)
            else:
                response = self.client.messages.create(**params)
        except anthropic.AuthenticationError as exc:
            raise LLMError("auth", exc.message) from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("auth", exc.message) from exc
        except anthropic.NotFoundError as exc:
            raise LLMError("bad_model", exc.message) from exc
        except anthropic.RateLimitError as exc:
            retry = exc.response.headers.get("retry-after")
            raise LLMError("rate_limit", exc.message, float(retry) if retry and retry.isdigit() else None) from exc
        except anthropic.BadRequestError as exc:
            if "credit" in exc.message.lower() or "billing" in exc.message.lower():
                raise LLMError("billing", exc.message) from exc
            raise LLMError("internal", exc.message) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 402 or getattr(exc, "type", "") == "billing_error":
                raise LLMError("billing", exc.message) from exc
            if exc.status_code >= 500:
                raise LLMError("server", exc.message) from exc  # surcharge (529) ou panne passagère
            raise LLMError("internal", exc.message) from exc
        except anthropic.APIConnectionError as exc:  # comprend les délais dépassés
            raise LLMError("network", str(exc)) from exc

        if response.stop_reason == "refusal":
            raise LLMError("blocked", "demande déclinée")
        text = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens" or not text.strip():
            raise LLMError("bad_output", f"réponse incomplète ({response.stop_reason})")
        return text
