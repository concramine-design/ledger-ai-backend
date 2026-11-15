"""Ce qui se déclenche tout seul après une action de l'élève : rappels, cartes mémoire, carnet d'erreurs."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Attempt, Lesson, Question, ReviewItem
from . import srs
from .generation.content import Summary
from .generation.generators import get_artifact, given_and_expected
from .generation.worker import enqueue


def on_mastered(db: Session, lesson: Lesson) -> None:
    """Leçon maîtrisée : les rappels espacés commencent, et leurs questions se préparent."""
    item = srs.schedule_lesson(db, lesson)
    if item is not None:
        enqueue(db, lesson, "review_set", {"item_id": item.id}, priority=8)


def on_summary_read(db: Session, lesson: Lesson) -> None:
    """Fiche lue : ses définitions, son vocabulaire et ses auteurs deviennent des cartes mémoire."""
    art = get_artifact(lesson, "summary")
    if art is None:
        return
    try:
        cards = Summary.model_validate(art.content).cards()
    except Exception:  # noqa: BLE001 - une fiche ancienne ne doit pas bloquer la validation
        return
    srs.schedule_cards(db, lesson, cards)


def on_mistake(db: Session, lesson: Lesson, question: Question, attempt: Attempt, source: str) -> None:
    """Erreur : inscrite au carnet, puis reposée plus tard sous une autre forme."""
    given, expected = given_and_expected(question, attempt)
    item = srs.record_mistake(db, lesson, question, given, expected, source)
    if item is not None:
        enqueue(db, lesson, "error_variant", {"item_id": item.id}, priority=9)


def on_review_finished(db: Session, lesson: Lesson, item: ReviewItem) -> None:
    """Un rappel vient d'être fait : on prépare déjà les questions du suivant."""
    if item.state != "active":
        return
    kind = "error_variant" if item.kind == "error" else "review_set"
    enqueue(db, lesson, kind, {"item_id": item.id}, priority=8)


def review_item_view(item: ReviewItem) -> dict[str, Any]:
    return {"id": item.id, "kind": item.kind, "stage": item.stage, "due": item.due.isoformat(), "state": item.state}
