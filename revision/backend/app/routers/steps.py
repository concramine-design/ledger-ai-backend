"""Le parcours : contenu de chaque étape, réponses, indices, validation."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, get_settings
from ..models import Attempt, Lesson, Question, QuestionSet, ReviewItem, utcnow
from ..services import activity, followup, parcours, srs
from ..services.evaluation import grade_mcq, grade_open, grade_schema, grade_writing
from ..services.generation import prompts
from ..services.generation.content import ExpliqueEval, FeuilleResult, validate
from ..services.generation.generators import build_ctx, get_artifact, save_artifact
from ..services.generation.worker import enqueue
from ..services.llm import LLMRequest, get_llm
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

MAX_ANSWER_CHARS = 8000


def _sets(lesson: Lesson, kind: str, level: Optional[int] = None) -> list[QuestionSet]:
    return sorted((s for s in lesson.sets if s.kind == kind and s.level == level), key=lambda s: s.version)


def _step_key(qset: QuestionSet) -> str:
    return f"ex{qset.level}" if qset.kind == "exercises" else qset.kind


def _required(qset: QuestionSet, settings: dict[str, Any]) -> int:
    """Nombre d'exercices à réussir. Une seule rédaction réussie suffit pour un niveau de rédaction."""
    if qset.questions and all(q.data.get("mode") == "redaction" for q in qset.questions if q.parent_id is None):
        return 1
    return settings["exercises_required"]


def _exercise_progress(qset: QuestionSet, settings: dict[str, Any]) -> dict[str, int]:
    threshold = settings["exercise_threshold"]
    return {
        "succeeded": sum(exercise_succeeded(q, threshold) for q in qset.questions),
        "required": _required(qset, settings),
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
        "kind": lesson.subject.kind,
        "generation": generation_status(lesson),
        "ready": step_ready(lesson, step),
    }

    if key == "feuille":
        art = get_artifact(lesson, "feuille")
        out["threshold"] = settings["feuille_threshold"]
        out["feuille"] = art.content if art else {"submissions": []}

    elif key == "explique":
        art = get_artifact(lesson, "explique")
        out["threshold"] = settings["explique_threshold"]
        out["explique"] = art.content if art else _new_talk(0)

    elif step.job_kind in ("explanation", "summary"):
        art = get_artifact(lesson, step.job_kind)
        out["content"] = art.content if art else None
        if step.job_kind == "explanation":
            videos = get_artifact(lesson, "videos")
            out["videos"] = videos.content if videos else None
            mindmap = get_artifact(lesson, "mindmap")
            out["mindmap"] = mindmap.content if mindmap else None
        else:
            out["cards"] = sum(r.kind == "card" for r in lesson.reviews)

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
        out["has_methods"] = get_artifact(lesson, "methods") is not None
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
        if step.job_kind == "summary":
            followup.on_summary_read(db, lesson)
        activity.touch(db)
        db.commit()
    nxt = parcours.current_step(lesson)
    return {"ok": True, "next": nxt.key if nxt else None}


# -- Étape 3 : feuille blanche -------------------------------------------------
MIN_FEUILLE_WORDS = 15


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


@router.post("/lessons/{lesson_id}/steps/feuille/submit")
def submit_feuille(lesson_id: int, body: TextIn, db: Session = Depends(get_db)) -> dict:
    """Elle écrit de mémoire tout ce qu'elle a retenu ; l'IA compare avec la leçon et signale oublis et erreurs."""
    lesson = get_lesson(db, lesson_id)
    status = parcours.require_open(lesson, "feuille")
    text = body.text.strip()
    if len(text.split()) < MIN_FEUILLE_WORDS:
        raise HTTPException(422, "Écris au moins quelques phrases : tout ce dont tu te souviens, même en désordre.")
    settings = get_settings(db)
    ctx = build_ctx(lesson)
    req = LLMRequest(
        task="feuille_compare",
        system=prompts.system(ctx),
        messages=[{"role": "user", "content": prompts.feuille_compare(ctx, text)}],
        temperature=0.1,
        payload={"text": ctx.text, "answer": text},
    )
    result = validate(FeuilleResult, get_llm().generate_json(req))  # en cas de panne : erreur 503, elle garde son texte
    coverage = result.coverage
    threshold = settings["feuille_threshold"]
    passed = coverage >= threshold
    art = get_artifact(lesson, "feuille")
    submissions = list(art.content.get("submissions", [])) if art else []
    submissions.append({"text": text, "coverage": coverage, "passed": passed, "result": result.model_dump()})
    save_artifact(db, lesson, "feuille", {"submissions": submissions[-5:]})
    if passed and status == "current":
        parcours.mark_done(db, lesson, "feuille", coverage)
    lesson.last_activity_at = utcnow()
    activity.touch(db)
    db.commit()
    return {"coverage": coverage, "threshold": threshold, "passed": passed, "result": result.model_dump(), "step_done": passed}


# -- Étape 6 : explique-moi ----------------------------------------------------
STUDENT_QUESTIONS = 2  # le camarade pose deux questions, puis l'explication est évaluée
MIN_EXPLAIN_WORDS = 12


def _new_talk(attempt: int) -> dict[str, Any]:
    return {"attempt": attempt, "messages": [], "evaluation": None, "score": None, "passed": None}


@router.post("/lessons/{lesson_id}/steps/explique/message")
def explique_message(lesson_id: int, body: TextIn, db: Session = Depends(get_db)) -> dict:
    """Elle explique la leçon ; l'IA joue un élève qui pose des questions, puis évalue la clarté."""
    lesson = get_lesson(db, lesson_id)
    status = parcours.require_open(lesson, "explique")
    settings = get_settings(db)
    art = get_artifact(lesson, "explique")
    talk = dict(art.content) if art else _new_talk(0)
    if talk.get("evaluation"):
        raise HTTPException(409, "Cette explication est terminée. Recommence pour réessayer.")
    text = body.text.strip()
    messages = list(talk["messages"])
    said = sum(m["role"] == "eleve" for m in messages)
    if said == 0 and len(text.split()) < MIN_EXPLAIN_WORDS:
        raise HTTPException(422, "Explique la leçon en quelques phrases, comme à un camarade qui ne la connaît pas.")
    messages.append({"role": "eleve", "content": text})
    ctx = build_ctx(lesson)
    llm = get_llm()

    if said < STUDENT_QUESTIONS:  # le camarade pose une question
        history = [{"role": "user" if m["role"] == "eleve" else "assistant", "content": m["content"]} for m in messages]
        req = LLMRequest(
            task="explique_question",
            system=prompts.explique_system(ctx),
            messages=history,
            json_mode=False,
            temperature=0.6,
            payload={"round": said + 1},
        )
        question = llm.generate(req).strip()
        messages.append({"role": "camarade", "content": question})
        talk["messages"] = messages
    else:  # fin de l'échange : évaluation
        req = LLMRequest(
            task="explique_eval",
            system=prompts.system(ctx),
            messages=[{"role": "user", "content": prompts.explique_eval(ctx, messages)}],
            temperature=0.1,
            payload={"messages": messages},
        )
        evaluation = validate(ExpliqueEval, llm.generate_json(req))
        talk.update(
            messages=messages,
            evaluation=evaluation.model_dump(),
            score=evaluation.score,
            passed=evaluation.score >= settings["explique_threshold"],
        )
        if talk["passed"] and status == "current":
            parcours.mark_done(db, lesson, "explique", evaluation.score)
    save_artifact(db, lesson, "explique", talk)
    lesson.last_activity_at = utcnow()
    activity.touch(db)
    db.commit()
    return {"explique": talk, "threshold": settings["explique_threshold"], "step_done": bool(talk.get("passed"))}


@router.post("/lessons/{lesson_id}/steps/explique/restart")
def explique_restart(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    parcours.require_open(lesson, "explique")
    art = get_artifact(lesson, "explique")
    talk = _new_talk((art.content.get("attempt", 0) + 1) if art else 0)
    save_artifact(db, lesson, "explique", talk)
    db.commit()
    return {"explique": talk}


class AnswerIn(BaseModel):
    answer_text: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    choice_index: Optional[int] = None
    labels: Optional[list[str]] = None  # schéma à légender : le nom choisi pour chaque case


def _all_scores(qset: QuestionSet) -> Optional[list[float]]:
    scores = []
    for q in qset.questions:
        graded = [a for a in q.attempts if a.status == "graded"]
        if not graded:
            return None
        scores.append(graded[-1].score or 0.0)
    return scores


def _finish_test(db: Session, lesson: Lesson, qset: QuestionSet, settings: dict[str, Any]) -> Optional[dict]:
    """Quand toutes les questions sont corrigées : calcule le score et décide de la suite."""
    scores = _all_scores(qset)
    if scores is None:
        return None
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


def _finish_review(db: Session, lesson: Lesson, qset: QuestionSet, item: ReviewItem) -> Optional[dict]:
    """Rappel terminé : on reprogramme selon le résultat et on prépare le suivant."""
    scores = _all_scores(qset)
    if scores is None:
        return None
    mean = sum(scores) / len(scores)
    qset.score = round(100 * mean)
    qset.finished_at = utcnow()
    result = srs.finish_questions(db, item, mean)
    qset.state = "passed" if result["passed"] else "failed"
    followup.on_review_finished(db, lesson, item)
    return result


@router.post("/questions/{question_id}/answer")
def answer(question_id: int, body: AnswerIn, db: Session = Depends(get_db)) -> dict:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(404, "Question introuvable.")
    qset = question.qset
    lesson = qset.lesson
    settings = get_settings(db)
    is_review = qset.kind == "review"
    is_test = qset.kind in ("minitest", "quiz")
    text = body.answer_text.strip()
    item: Optional[ReviewItem] = None
    status = "current"

    if is_review:
        item = db.query(ReviewItem).filter(ReviewItem.set_id == qset.id, ReviewItem.state == "active").first()
        if item is None or qset.state != "active":
            raise HTTPException(409, "Ce rappel est terminé.")
    else:
        status = parcours.require_open(lesson, _step_key(qset))  # 403 si l'étape est verrouillée

    if is_test and (status != "current" or qset.state != "active"):
        raise HTTPException(409, "Ce test est terminé.")
    if (is_test or is_review) and any(a.status == "graded" for a in question.attempts):
        raise HTTPException(409, "Tu as déjà répondu à cette question.")
    if question.qtype == "exercice" and not text:
        raise HTTPException(422, "Écris d'abord ta réponse.")
    if question.qtype == "qcm":
        choices = question.data.get("choix", [])
        if body.choice_index is None or not 0 <= body.choice_index < len(choices):
            raise HTTPException(422, "Choisis une réponse.")
    if question.qtype == "schema":
        if not body.labels or len(body.labels) != len(question.data.get("elements", [])):
            raise HTTPException(422, "Complète toutes les cases du schéma.")
        text = " ; ".join(body.labels)

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
    elif question.qtype == "schema":
        score, feedback = grade_schema(question.data, body.labels or [])
    elif question.data.get("mode") == "redaction":
        score, feedback = grade_writing(build_ctx(lesson), question.data, text)
    else:
        score, feedback = grade_open(build_ctx(lesson), question.data, text, spoiler_allowed=is_test or is_review)

    attempt.status = "graded"
    attempt.score = score
    attempt.feedback = feedback
    lesson.last_activity_at = utcnow()
    db.flush()

    result: dict[str, Any] = {"set": None, "progress": None, "review": None, "step_done": False, "mastered": False}
    if is_test:
        if score < 0.999:
            followup.on_mistake(db, lesson, question, attempt, qset.kind)
        finished = _finish_test(db, lesson, qset, settings)
        result["set"] = finished
        if finished:
            result["step_done"] = finished["passed"]
            result["mastered"] = finished["mastered"]
    elif is_review:
        assert item is not None
        if score < 0.999 and item.kind == "lesson":
            followup.on_mistake(db, lesson, question, attempt, "rappel")
        result["review"] = _finish_review(db, lesson, qset, item)
    else:
        progress = _exercise_progress(qset, settings)
        result["progress"] = progress
        if progress["succeeded"] >= progress["required"] and status == "current":
            result["mastered"] = parcours.mark_done(db, lesson, _step_key(qset), round(score * 100))
            result["step_done"] = True
    if result["mastered"]:
        followup.on_mastered(db, lesson)
    activity.touch(db)
    db.commit()

    if question.qtype == "exercice":
        result["question"] = exercise_view(question, settings["exercise_threshold"])
    else:
        result["question"] = test_question_view(question)
    return result


def _exercise(db: Session, question_id: int) -> tuple[Question, Lesson, dict[str, Any]]:
    question = db.get(Question, question_id)
    if question is None or question.qtype != "exercice":
        raise HTTPException(404, "Exercice introuvable.")
    lesson = question.qset.lesson
    parcours.require_open(lesson, _step_key(question.qset))
    return question, lesson, get_settings(db)


@router.post("/questions/{question_id}/hint")
def hint(question_id: int, db: Session = Depends(get_db)) -> dict:
    """Indice suivant : une piste, puis la méthode, puis le début de la solution."""
    question, _lesson, settings = _exercise(db, question_id)
    total = len(question.data.get("indices", []))
    used = question.hints_used or 0
    if used < total:
        question.hints_used = used + 1
        db.commit()
    return {"question": exercise_view(question, settings["exercise_threshold"])}


@router.post("/questions/{question_id}/reveal")
def reveal(question_id: int, db: Session = Depends(get_db)) -> dict:
    """Correction détaillée, en dernier recours. L'exercice ne compte plus : un autre du même type est préparé."""
    question, lesson, settings = _exercise(db, question_id)
    threshold = settings["exercise_threshold"]
    graded = [a for a in question.attempts if a.status == "graded"]
    if not graded:
        raise HTTPException(409, "Essaie d'abord de répondre : la correction vient après ta tentative.")
    if question.revealed_at is None and not exercise_succeeded(question, threshold):
        question.revealed_at = utcnow()
        followup.on_mistake(db, lesson, question, graded[-1], "exercice")
        already = any(
            j.kind == "exercise_variant" and (j.params or {}).get("question_id") == question.id for j in lesson.jobs
        )
        if not already:
            enqueue(db, lesson, "exercise_variant", {"question_id": question.id}, priority=6)
        db.commit()
    return {"question": exercise_view(question, threshold), "variant_pending": True}
