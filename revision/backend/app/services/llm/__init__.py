"""Point d'entrée de l'IA : choisit le fournisseur et bascule sur l'autre en cas de panne."""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from ...config import Config, get_config
from .base import LLMError, LLMRequest, Provider
from .claude import ClaudeProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .jsonfix import parse_json
from .mock import MockProvider

log = logging.getLogger("revision.llm")

__all__ = ["LLM", "LLMError", "LLMRequest", "get_llm", "reset_llm", "parse_json", "use_llm"]

_override: contextvars.ContextVar[Optional["LLM"]] = contextvars.ContextVar("llm_override", default=None)


class LLM:
    def __init__(self, providers: list[Provider]):
        self.providers = providers

    @property
    def configured(self) -> bool:
        return bool(self.providers)

    @property
    def name(self) -> Optional[str]:
        return self.providers[0].name if self.providers else None

    @property
    def demo(self) -> bool:
        return self.name == "mock"

    def generate(self, req: LLMRequest) -> str:
        if not self.providers:
            raise LLMError("config", "aucune clé configurée")
        candidates = [p for p in self.providers if p.supports_vision] if req.images else self.providers
        if not candidates:
            raise LLMError("no_vision")
        first_error: LLMError | None = None
        for provider in candidates:
            try:
                return provider.generate(req)
            except LLMError as exc:
                log.warning("IA %s, tâche %s : %s (%s)", provider.name, req.task, exc.kind, exc.detail[:200])
                first_error = first_error or exc
                # Une réponse mal formée ne s'arrange pas en changeant de fournisseur tout de suite.
                if exc.kind in ("bad_output", "blocked"):
                    break
        assert first_error is not None
        raise first_error

    def generate_json(self, req: LLMRequest) -> Any:
        req.json_mode = True
        text = self.generate(req)
        try:
            return parse_json(text)
        except ValueError as exc:
            raise LLMError("bad_output", str(exc)) from exc


def build_llm(cfg: Config) -> LLM:
    choice = cfg.llm_provider
    if choice == "mock":
        return LLM([MockProvider()])
    claude = ClaudeProvider(cfg.anthropic_api_key, cfg.claude_model, cfg.claude_effort) if cfg.anthropic_api_key else None
    gemini = GeminiProvider(cfg.gemini_api_key, cfg.gemini_model) if cfg.gemini_api_key else None
    groq = GroqProvider(cfg.groq_api_key, cfg.groq_model, cfg.groq_vision_model) if cfg.groq_api_key else None
    # Claude d'abord ; les autres servent de secours si leur clé est présente.
    order = {"gemini": [gemini, claude, groq], "groq": [groq, claude, gemini]}.get(choice, [claude, gemini, groq])
    return LLM([p for p in order if p is not None])


_llm: LLM | None = None


@contextmanager
def use_llm(llm: "LLM") -> Iterator[None]:
    """Remplace l'IA le temps d'un bloc (préparation par Claude via MCP)."""
    token = _override.set(llm)
    try:
        yield
    finally:
        _override.reset(token)


def get_llm() -> LLM:
    global _llm
    override = _override.get()
    if override is not None:
        return override
    if _llm is None:
        _llm = build_llm(get_config())
    return _llm


def reset_llm() -> None:
    global _llm
    _llm = None
