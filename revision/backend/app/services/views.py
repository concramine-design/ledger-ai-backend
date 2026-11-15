"""Mise en forme des données envoyées à l'interface."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import Attempt, Exam, Job, Lesson, Question, QuestionSet, Subject, utcnow
from . import parcours
from .generation.worker import job_label

# Matières dont le parcours est disponible dans cette version.
AVAILABLE_CODES = {"maths", "pc"}


def subject_available(subject: Subject) -> bool:
    if subject.code is not None:
        return subject.code in AVAILABLE_CODES
    return subject.kind == "sciences"


def subject_view(subject: Subject) -> dict[str, Any]:
    return {
        "id": subject.id,
        "code": subject.code,
        "name": subject.name,
        "kind": subject.kind,
        "language": subject.language,
        "color": subject.color,
        "enabled": subject.enabled,
        "available": subject_available(subject),
    }


def next_exam(db: Session, subject_id: int) -> Optional[Exam]:
    return (
        db.query(Exam)
        .filter(Exam.subject_id == subject_id, Exam.date >= date.today())
        .order_by(Exam.date)
        .first()
    )


def exam_view(exam: Exam) -> dict[str, Any]:
    return {
        "id": exam.id,
        "subject_id": exam.subject_id,
        "subject_name": exam.subject.name,
        "date": exam.date.isoformat(),
        "title": exam.title,
        "days_left": (exam.date - date.today()).days,
    }


# -- Génération ---------------------------------------------------------------
def _problem(job: Job) -> dict[str, Any]:
    retry_in = None
    if job.status == "pending" and job.next_try_at:
        retry_in = max(0, int((job.next_try_at - utcnow()).total_seconds()))
    return {
        "kind": job.error_kind,
        "message": job.last_error,
        "label": job_label(job),
        "fatal": job.status == "failed",
        "retry_in": retry_in,
    }


def generation_status(lesson: Lesson) -> dict[str, Any]:
    jobs = lesson.jobs
    done = sum(j.status == "done" for j in jobs)
    failed = [j for j in jobs if j.status == "failed"]
    retrying = sorted((j for j in jobs if j.status == "pending" and j.last_error), key=lambda j: j.priority)
    running = next((j for j in jobs if j.status == "running"), None)
    waiting = sorted((j for j in jobs if j.status == "pending"), key=lambda j: (j.priority, j.id))
    current = running or (waiting[0] if waiting else None)
    problem = _problem(failed[0]) if failed else _problem(retrying[0]) if retrying else None
    return {
        "total": len(jobs),
        "done": done,
        "active": done < len(jobs),
        "current": job_label(current) if current else None,
        "problem": problem,
    }


def _sets(lesson: Lesson, kind: str, level: Optional[int] = None) -> list[QuestionSet]:
    return sorted((s for s in lesson.sets if s.kind == kind and s.level == level), key=lambda s: s.version)


def step_ready(lesson: Lesson, step: parcours.Step) -> bool:
    """Le contenu de l'étape est-il généré ?"""
    if step.job_kind in ("explanation", "summary"):
        return any(a.kind == step.job_kind for a in lesson.artifacts)
    if step.job_kind in ("minitest", "quiz"):
        sets = _sets(lesson, step.job_kind)
        return bool(sets) and sets[-1].state != "failed"
    if step.job_kind == "exercises":
        return bool(_sets(lesson, "exercises", step.level))
    return False


# -- Leçons -------------------------------------------------------------------
def lesson_view(db: Session, lesson: Lesson, detailed: bool = False) -> dict[str, Any]:
    subject = lesson.subject
    cur = parcours.current_step(lesson)
    out: dict[str, Any] = {
        "id": lesson.id,
        "title": lesson.title,
        "chapter": {"id": lesson.chapter.id, "title": lesson.chapter.title},
        "subject": subject_view(subject),
        "source_type": lesson.source_type,
        "progress": parcours.progress_percent(lesson),
        "mastered": lesson.mastered_at is not None,
        "current_step": {"key": cur.key, "label": cur.label} if cur else None,
        "generation": generation_status(lesson),
        "has_text": bool(lesson.raw_text),
        "truncated": lesson.truncated,
    }
    if detailed:
        out["path"] = parcours.path(lesson)
        exam = next_exam(db, subject.id)
        out["exam"] = exam_view(exam) if exam else None
        if cur:
            out["current_ready"] = step_ready(lesson, cur)
    return out


# -- Questions ----------------------------------------------------------------
def _latest(question: Question) -> Optional[Attempt]:
    return question.attempts[-1] if question.attempts else None


def test_question_view(question: Question) -> dict[str, Any]:
    """Question de mini-test ou de quiz. La correction n'apparaît qu'après la réponse."""
    d = question.data
    out: dict[str, Any] = {
        "id": question.id,
        "type": question.qtype,
        "enonce": d.get("enonce", ""),
        "choix": d.get("choix", []),
        "notion": question.notion,
        "attempt": None,
        "correction": None,
    }
    att = _latest(question)
    if att is not None:
        out["attempt"] = {
            "status": att.status,
            "answer_text": att.answer_text,
            "choice_index": att.choice_index,
            "score": att.score,
            "feedback": att.feedback if att.status == "graded" else None,
        }
        if att.status == "graded":
            out["correction"] = {
                "bonne_reponse": d.get("bonne_reponse"),
                "reponse_modele": d.get("reponse_modele", ""),
                "explication": d.get("explication", ""),
            }
    return out


def set_view(qset: QuestionSet) -> dict[str, Any]:
    return {
        "id": qset.id,
        "version": qset.version,
        "state": qset.state,
        "score": qset.score,
        "questions": [test_question_view(q) for q in qset.questions],
    }


def exercise_succeeded(question: Question, threshold: int) -> bool:
    return any(
        a.status == "graded" and not a.after_reveal and (a.score or 0) * 100 >= threshold
        for a in question.attempts
    )


def _hide_expected(feedback: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Tant qu'elle peut réessayer, on ne montre pas le texte des éléments attendus."""
    if not feedback:
        return feedback
    out = dict(feedback)
    out["elements"] = [{"etat": e.get("etat"), "commentaire": e.get("commentaire", "")} for e in feedback.get("elements", [])]
    return out


def exercise_view(question: Question, threshold: int) -> dict[str, Any]:
    d = question.data
    graded = [a for a in question.attempts if a.status == "graded"]
    pending = next((a for a in question.attempts if a.status == "pending"), None)
    succeeded = exercise_succeeded(question, threshold)
    revealed = question.revealed_at is not None
    solved = succeeded or revealed
    state = "succeeded" if succeeded else "revealed" if revealed else "tried" if graded else "todo"
    return {
        "id": question.id,
        "titre": d.get("titre", ""),
        "enonce": d.get("enonce", ""),
        "type_exercice": d.get("type_exercice", ""),
        "notion": question.notion,
        "state": state,
        "is_variant": question.parent_id is not None,
        "draft": pending.answer_text if pending else "",
        "can_reveal": bool(graded) and not solved,
        "attempts": [
            {
                "answer_text": a.answer_text,
                "score": a.score,
                "feedback": a.feedback if solved else _hide_expected(a.feedback),
                "after_reveal": a.after_reveal,
            }
            for a in graded
        ],
        "correction": {"etapes": d.get("correction_etapes", []), "reponse_finale": d.get("reponse_finale", "")}
        if solved
        else None,
    }
