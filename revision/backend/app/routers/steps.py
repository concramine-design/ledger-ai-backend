"""Le parcours : contenu de chaque étape, réponses, validation."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, get_settings
from ..models import Attempt, Lesson, Question, QuestionSet, utcnow
from ..services import parcours
from ..services.evaluation import grade_mcq, grade_open
from ..services.generation.generators import build_ctx, get_artifact
from ..services.generation.worker import enqueue
from ..services.views import (
    exercise_succeeded,
    exercise_view,
    generation_status,
    lesson_view,
    set_view,
    step_ready,
    test_question_view,
)
from .lessons import get_lesson

router = APIRouter(prefix="/api")

MAX_ANSWER_CHARS = 6000


def _sets(lesson: Lesson, kind: str, level: Optional[int] = None) -> list[QuestionSet]:
    return sorted((s for s in lesson.sets if s.kind == kind and s.level == level), key=lambda s: s.version)


def _step_key(qset: QuestionSet) -> str:
    return f"ex{qset.level}" if qset.kind == "exercises" else qset.kind


def _exercise_progress(qset: QuestionSet, settings: dict[str, Any]) -> dict[str, int]:
    threshold = settings["exercise_threshold"]
    return {
        "succeeded": sum(exercise_succeeded(q, threshold) for q in qset.questions),
        "required": settings["exercises_required"],
    }


@router.get("/lessons/{lesson_id}/steps/{key}")
def get_step(lesson_id: int, key: str, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    step = parcours.get_step(key)
    status = parcours.require_open(lesson, key)  # 403 si l'étape est verrouillée
    settings = get_settings(db)
    out: dict[str, Any] = {
        "lesson": lesson_view(db, lesson),
        "step": {"key": step.key, "label": step.label, "description": step.description, "minutes": step.minutes},
        "status": status,
        "language": lesson.subject.language,
        "generation": generation_status(lesson),
        "ready": step_ready(lesson, step),
    }

    if step.job_kind in ("explanation", "summary"):
        art = get_artifact(lesson, step.job_kind)
        out["content"] = art.content if art else None

    elif step.job_kind in ("minitest", "quiz"):
        sets = _sets(lesson, step.job_kind)
        current: Optional[QuestionSet] = None
        previous: Optional[QuestionSet] = None
        if status == "done":
            passed = [s for s in sets if s.state == "passed"]
            current = passed[-1] if passed else None
        elif sets:
            if sets[-1].state == "active":
                current = sets[-1]
                previous = sets[-2] if len(sets) > 1 else None
            else:  # test raté : la nouvelle version est en préparation
                previous = sets[-1]
        out["threshold"] = settings[f"{step.job_kind}_threshold"]
        out["set"] = set_view(current) if current else None
        out["previous"] = None
        if previous is not None:
            art = get_artifact(lesson, "reexplain", previous.id)
            out["previous"] = {**set_view(previous), "reexplain": art.content if art else None}
        out["ready"] = current is not None

    else:  # exercices
        sets = _sets(lesson, "exercises", step.level)
        qset = sets[0] if sets else None
        threshold = settings["exercise_threshold"]
        out["threshold"] = threshold
        out["exercises"] = [exercise_view(q, threshold) for q in qset.questions] if qset else []
        out["progress"] = _exercise_progress(qset, settings) if qset else {"succeeded": 0, "required": settings["exercises_required"]}
        ids = {q.id for q in qset.questions} if qset else set()
        out["variant_pending"] = any(
            j.kind == "exercise_variant" and j.status != "done" and (j.params or {}).get("question_id") in ids
            for j in lesson.jobs
        )
    return out


@router.post("/lessons/{lesson_id}/steps/{key}/validate")
def validate_step(lesson_id: int, key: str, db: Session = Depends(get_db)) -> dict:
    """Valide une étape de lecture (Comprendre, Résumé)."""
    lesson = get_lesson(db, lesson_id)
    step = parcours.get_step(key)
    status = parcours.require_open(lesson, key)
    if step.job_kind not in ("explanation", "summary"):
        raise HTTPException(409, "Cette étape se valide en réussissant ses questions.")
    if not step_ready(lesson, step):
        raise HTTPException(409, "Cette étape n'est pas encore prête.")
    if status == "current":
        parcours.mark_done(db, lesson, key)
        db.commit()
    nxt = parcours.current_step(lesson)
    return {"ok": True, "next": nxt.key if nxt else None}


class AnswerIn(BaseModel):
    answer_text: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    choice_index: Optional[int] = None


def _finish_test(db: Session, lesson: Lesson, qset: QuestionSet, settings: dict[str, Any]) -> Optional[dict]:
    """Quand toutes les questions sont corrigées : calcule le score et décide de la suite."""
    scores = []
    for q in qset.questions:
        graded = [a for a in q.attempts if a.status == "graded"]
        if not graded:
            return None
        scores.append(graded[-1].score or 0.0)
    score = round(100 * sum(scores) / len(scores))
    threshold = settings[f"{qset.kind}_threshold"]
    passed = score >= threshold
    qset.score = score
    qset.state = "passed" if passed else "failed"
    qset.finished_at = utcnow()
    mastered = False
    if passed:
        mastered = parcours.mark_done(db, lesson, qset.kind, score)
    else:
        # Échec : on réexplique autrement les points ratés et on prépare un nouveau test.
        weak = list(dict.fromkeys(q.notion for q, s in zip(qset.questions, scores) if s < 0.999 and q.notion))
        enqueue(db, lesson, "reexplain", {"set_id": qset.id}, priority=5)
        enqueue(db, lesson, qset.kind, {"version": qset.version + 1, "focus": weak}, priority=6)
    return {"state": qset.state, "score": score, "threshold": threshold, "passed": passed, "mastered": mastered}


@router.post("/questions/{question_id}/answer")
def answer(question_id: int, body: AnswerIn, db: Session = Depends(get_db)) -> dict:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(404, "Question introuvable.")
    qset = question.qset
    lesson = qset.lesson
    key = _step_key(qset)
    status = parcours.require_open(lesson, key)
    settings = get_settings(db)
    is_test = qset.kind in ("minitest", "quiz")
    text = body.answer_text.strip()

    if is_test:
        if status != "current" or qset.state != "active":
            raise HTTPException(409, "Ce test est terminé.")
        if any(a.status == "graded" for a in question.attempts):
            raise HTTPException(409, "Tu as déjà répondu à cette question.")
    elif not text:
        raise HTTPException(422, "Écris d'abord ta réponse.")
    if question.qtype == "qcm":
        choices = question.data.get("choix", [])
        if body.choice_index is None or not 0 <= body.choice_index < len(choices):
            raise HTTPException(422, "Choisis une réponse.")

    # La réponse est enregistrée avant l'appel à l'IA : rien n'est perdu si la correction échoue.
    attempt = next((a for a in question.attempts if a.status == "pending"), None)
    if attempt is None:
        attempt = Attempt()
        question.attempts.append(attempt)
    attempt.answer_text = text
    attempt.choice_index = body.choice_index
    attempt.after_reveal = question.revealed_at is not None
    db.commit()

    if question.qtype == "qcm":
        score, feedback = grade_mcq(question.data, body.choice_index or 0)
    else:
        score, feedback = grade_open(build_ctx(lesson), question.data, text, spoiler_allowed=is_test)

    attempt.status = "graded"
    attempt.score = score
    attempt.feedback = feedback
    lesson.last_activity_at = utcnow()
    db.flush()

    result: dict[str, Any] = {"set": None, "progress": None, "step_done": False, "mastered": False}
    if is_test:
        finished = _finish_test(db, lesson, qset, settings)
        result["set"] = finished
        if finished:
            result["step_done"] = finished["passed"]
            result["mastered"] = finished["mastered"]
    else:
        progress = _exercise_progress(qset, settings)
        result["progress"] = progress
        if progress["succeeded"] >= progress["required"] and status == "current":
            result["mastered"] = parcours.mark_done(db, lesson, key, round(score * 100))
            result["step_done"] = True
    db.commit()

    if is_test:
        result["question"] = test_question_view(question)
    else:
        result["question"] = exercise_view(question, settings["exercise_threshold"])
    return result


@router.post("/questions/{question_id}/reveal")
def reveal(question_id: int, db: Session = Depends(get_db)) -> dict:
    """Correction détaillée, en dernier recours. L'exercice ne compte plus : un autre du même type est préparé."""
    question = db.get(Question, question_id)
    if question is None or question.qtype != "exercice":
        raise HTTPException(404, "Exercice introuvable.")
    qset = question.qset
    lesson = qset.lesson
    parcours.require_open(lesson, _step_key(qset))
    settings = get_settings(db)
    threshold = settings["exercise_threshold"]
    if not any(a.status == "graded" for a in question.attempts):
        raise HTTPException(409, "Essaie d'abord de répondre : la correction vient après ta tentative.")
    if question.revealed_at is None and not exercise_succeeded(question, threshold):
        question.revealed_at = utcnow()
        already = any(
            j.kind == "exercise_variant" and (j.params or {}).get("question_id") == question.id for j in lesson.jobs
        )
        if not already:
            enqueue(db, lesson, "exercise_variant", {"question_id": question.id}, priority=6)
        db.commit()
    return {"question": exercise_view(question, threshold), "variant_pending": True}

