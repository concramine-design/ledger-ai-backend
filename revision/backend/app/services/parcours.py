"""Le parcours guidé : étapes verrouillées, validées dans l'ordre.

Le verrouillage est décidé ici, côté serveur : l'interface ne peut pas le contourner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Lesson, StepProgress, utcnow


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    description: str
    minutes: int
    active: bool  # False : étape prévue dans une prochaine version
    job_kind: Optional[str] = None
    level: Optional[int] = None


STEPS: list[Step] = [
    Step("comprendre", "Comprendre", "Lis l'explication pas à pas, avec des exemples.", 15, True, "explanation"),
    Step("minitest", "Mini-test", "Quelques questions pour vérifier que tu as compris.", 5, True, "minitest"),
    Step("feuille", "Feuille blanche", "Écris de mémoire tout ce que tu as retenu.", 10, False),
    Step("resume", "Résumé", "Ta fiche de référence : définitions, formules, méthodes, pièges.", 5, True, "summary"),
    Step("quiz", "Quiz complet", "Des questions où tu écris tes réponses.", 15, True, "quiz"),
    Step("explique", "Explique-moi", "Explique la leçon avec tes mots.", 10, False),
    Step("ex1", "Exercices niveau 1", "Application directe du cours.", 20, True, "exercises", 1),
    Step("ex2", "Exercices niveau 2", "Exercices typiques de contrôle.", 25, True, "exercises", 2),
    Step("ex3", "Exercices niveau 3", "Exercices difficiles, pour viser haut.", 30, True, "exercises", 3),
]
STEP_BY_KEY = {s.key: s for s in STEPS}
ACTIVE_STEPS = [s for s in STEPS if s.active]


def get_step(key: str) -> Step:
    step = STEP_BY_KEY.get(key)
    if step is None:
        raise HTTPException(404, "Étape inconnue.")
    return step


def done_steps(lesson: Lesson) -> dict[str, StepProgress]:
    return {p.step: p for p in lesson.progress}


def current_step(lesson: Lesson) -> Optional[Step]:
    """La première étape active non validée (None si la leçon est maîtrisée)."""
    done = done_steps(lesson)
    for step in ACTIVE_STEPS:
        if step.key not in done:
            return step
    return None


def step_status(lesson: Lesson, key: str) -> str:
    step = get_step(key)
    if not step.active:
        return "soon"
    if key in done_steps(lesson):
        return "done"
    cur = current_step(lesson)
    return "current" if cur is not None and cur.key == key else "locked"


def path(lesson: Lesson) -> list[dict[str, Any]]:
    done = done_steps(lesson)
    cur = current_step(lesson)
    out = []
    for step in STEPS:
        if not step.active:
            status = "soon"
        elif step.key in done:
            status = "done"
        elif cur is not None and cur.key == step.key:
            status = "current"
        else:
            status = "locked"
        out.append(
            {
                "key": step.key,
                "label": step.label,
                "description": step.description,
                "minutes": step.minutes,
                "status": status,
                "score": done[step.key].score if step.key in done else None,
            }
        )
    return out


def require_open(lesson: Lesson, key: str) -> str:
    """Refuse l'accès à une étape verrouillée. Renvoie « current » ou « done »."""
    status = step_status(lesson, key)
    if status == "soon":
        raise HTTPException(403, "Cette étape arrive dans une prochaine version.")
    if status == "locked":
        cur = current_step(lesson)
        raise HTTPException(403, f"Étape verrouillée : termine d'abord « {cur.label if cur else ''} ».")
    return status


def mark_done(db: Session, lesson: Lesson, key: str, score: Optional[int] = None) -> bool:
    """Valide une étape. Renvoie True si la leçon vient d'être maîtrisée."""
    if step_status(lesson, key) != "current":
        return False
    lesson.progress.append(StepProgress(step=key, score=score))
    lesson.last_activity_at = utcnow()
    db.flush()
    if current_step(lesson) is None and lesson.mastered_at is None:
        lesson.mastered_at = utcnow()
        return True
    return False


def progress_percent(lesson: Lesson) -> int:
    return round(100 * len([s for s in ACTIVE_STEPS if s.key in done_steps(lesson)]) / len(ACTIVE_STEPS))
