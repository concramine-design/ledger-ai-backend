"""Interface commune aux fournisseurs d'IA et erreurs normalisées."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Messages affichés à l'élève, par type d'erreur.
ERROR_MESSAGES = {
    "network": "Pas de connexion internet. Vérifie ta connexion : je réessaie automatiquement.",
    "rate_limit": "L'IA est très sollicitée pour le moment (limite gratuite atteinte). Je réessaie dans un instant.",
    "server": "Le service d'IA a un souci passager. Je réessaie automatiquement.",
    "auth": "La clé d'IA est refusée. Demande à ton frère ou à tes parents de vérifier le fichier .env.",
    "config": "Aucune clé d'IA n'est configurée. Demande à ton frère ou à tes parents de remplir le fichier .env.",
    "bad_output": "L'IA a répondu de travers. Je réessaie.",
    "blocked": "L'IA a refusé de traiter ce contenu. Réessaie, ou reformule.",
    "no_vision": "La lecture des photos demande une clé Gemini (ou un modèle Groq capable de lire les images).",
    "input": "Je n'ai pas réussi à lire ce document. Essaie avec une photo plus nette, ou colle le texte de la leçon.",
    "internal": "Une erreur inattendue est survenue. Réessaie ; si ça continue, préviens ton frère ou tes parents.",
}

# Erreurs passagères : on réessaie indéfiniment, la progression est conservée.
TRANSIENT = {"network", "rate_limit", "server"}


class LLMError(Exception):
    def __init__(self, kind: str, detail: str = "", retry_after: Optional[float] = None):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail
        self.retry_after = retry_after

    @property
    def message(self) -> str:
        return ERROR_MESSAGES.get(self.kind, "Une erreur est survenue. Je réessaie.")

    @property
    def transient(self) -> bool:
        return self.kind in TRANSIENT


@dataclass
class LLMRequest:
    task: str  # nom de la tâche (utile aux journaux et à l'IA simulée)
    system: str
    messages: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]
    json_mode: bool = True
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (octets, type MIME)
    temperature: float = 0.4
    max_tokens: int = 8000
    payload: dict[str, Any] = field(default_factory=dict)  # données brutes (IA simulée)


class Provider:
    name = "base"
    supports_vision = False

    def generate(self, req: LLMRequest) -> str:  # pragma: no cover - interface
        raise NotImplementedError
