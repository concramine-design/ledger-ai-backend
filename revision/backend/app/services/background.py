"""Tâches de fond au niveau d'une matière (ancien devoir, contrôle blanc).

Elles ne passent pas par la file des leçons. Panne passagère : on réessaie quelques fois,
puis l'erreur est enregistrée avec un message clair et un bouton « Réessayer ».
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ..config import get_config
from .llm import LLMError

log = logging.getLogger("revision.background")

_DELAYS = [5, 15, 45, 120]  # secondes entre deux tentatives


def launch(work: Callable[[], None], on_error: Callable[[LLMError], None]) -> None:
    """Exécute `work` en arrière-plan. Dans les tests (sans fil d'exécution), l'exécute tout de suite, une fois."""

    def run(retries: bool) -> None:
        attempt = 0
        while True:
            try:
                work()
                return
            except LLMError as exc:
                if retries and exc.transient and attempt < len(_DELAYS):
                    time.sleep(_DELAYS[attempt])
                    attempt += 1
                    continue
                on_error(exc)
                return
            except Exception as exc:  # noqa: BLE001
                log.exception("tâche de fond : erreur inattendue")
                on_error(LLMError("internal", repr(exc)))
                return

    if get_config().run_worker:
        threading.Thread(target=run, args=(True,), daemon=True, name="fond").start()
    else:
        run(False)
