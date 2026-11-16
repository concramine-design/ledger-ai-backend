"""Espace parent / frère, protégé par un code : progression de l'élève, seuils, signalements."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, get_settings, set_setting
from ..models import Lesson, Mistake, MockExam, Report, Subject
from ..services import activity, parcours
from ..services.views import next_exam, subject_view

router = APIRouter(prefix="/api")

SESSION_SECONDS = 2 * 3600
_sessions: dict[str, float] = {}  # jeton -> heure d'expiration (en mémoire : se vide au redémarrage)
_failures: list[float] = []

SETTING_KEYS = ("minitest_threshold", "quiz_threshold", "exercise_threshold", "exercises_required", "feuille_threshold", "explique_threshold")


def _hash(code: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${digest}"


def _check(code: str, stored: str) -> bool:
    salt, _, _digest = stored.partition("$")
    return hmac.compare_digest(_hash(code, salt), stored)


def _new_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_SECONDS
    return token


def require_parent(x_parent_token: Optional[str] = Header(default=None)) -> None:
    """Refuse l'accès sans un jeton obtenu avec le code."""
    expiry = _sessions.get(x_parent_token or "")
    if expiry is None or expiry < time.time():
        _sessions.pop(x_parent_token or "", None)
        raise HTTPException(401, "Code de l'espace parent requis.")


class CodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=32)


@router.get("/parent/status")
def status(db: Session = Depends(get_db)) -> dict:
    return {"code_set": bool(get_settings(db).get("parent_code"))}


@router.post("/parent/setup")
def setup(body: CodeIn, db: Session = Depends(get_db)) -> dict:
    """Premier accès : choisir le code."""
    if get_settings(db).get("parent_code"):
        raise HTTPException(409, "Un code existe déjà.")
    set_setting(db, "parent_code", _hash(body.code))
    db.commit()
    return {"token": _new_session()}


@router.post("/parent/login")
def login(body: CodeIn, db: Session = Depends(get_db)) -> dict:
    stored = get_settings(db).get("parent_code")
    if not stored:
        raise HTTPException(409, "Aucun code n'est défini.")
    now = time.time()
    _failures[:] = [t for t in _failures if now - t < 60]
    if len(_failures) >= 5:
        raise HTTPException(429, "Trop d'essais. Attends une minute.")
    if not _check(body.code, stored):
        _failures.append(now)
        raise HTTPException(401, "Code incorrect.")
    return {"token": _new_session()}


class ChangeIn(BaseModel):
    new_code: str = Field(min_length=4, max_length=32)


@router.post("/parent/code", dependencies=[Depends(require_parent)])
def change_code(body: ChangeIn, db: Session = Depends(get_db)) -> dict:
    set_setting(db, "parent_code", _hash(body.new_code))
    db.commit()
    return {"ok": True}


class SettingsPatch(BaseModel):
    minitest_threshold: Optional[int] = Field(default=None, ge=40, le=100)
    quiz_threshold: Optional[int] = Field(default=None, ge=50, le=100)
    exercise_threshold: Optional[int] = Field(default=None, ge=40, le=100)
    exercises_required: Optional[int] = Field(default=None, ge=1, le=3)
    feuille_threshold: Optional[int] = Field(default=None, ge=20, le=100)
    explique_threshold: Optional[int] = Field(default=None, ge=40, le=100)


@router.patch("/settings", dependencies=[Depends(require_parent)])
def update_settings(body: SettingsPatch, db: Session = Depends(get_db)) -> dict:
    """Les seuils de réussite ne se règlent que depuis l'espace parent."""
    for key, value in body.model_dump(exclude_none=True).items():
        set_setting(db, key, value)
    db.commit()
    settings = get_settings(db)
    return {k: settings[k] for k in SETTING_KEYS}


@router.get("/parent/overview", dependencies=[Depends(require_parent)])
def overview(db: Session = Depends(get_db)) -> dict:
    """Tout ce qu'un parent ou un frère veut voir : où elle en est, sa régularité, ses points faibles."""
    settings = get_settings(db)
    subjects: list[dict[str, Any]] = []
    for subject in db.query(Subject).filter(Subject.enabled.is_(True)).order_by(Subject.position, Subject.id):
        lessons = []
        for chapter in subject.chapters:
            for lesson in chapter.lessons:
                cur = parcours.current_step(lesson)
                done = parcours.done_steps(lesson)
                lessons.append(
                    {
                        "id": lesson.id,
                        "title": lesson.title,
                        "chapter": chapter.title,
                        "mastery": activity.lesson_mastery(lesson),
                        "color": activity.color(activity.lesson_mastery(lesson)),
                        "mastered": lesson.mastered_at is not None,
                        "step": cur.label if cur else "Maîtrisée",
                        "scores": {k: done[k].score for k in ("minitest", "feuille", "quiz", "explique") if k in done and done[k].score is not None},
                        "open_mistakes": sum(m.resolved_at is None for m in lesson.mistakes),
                        "last_activity": lesson.last_activity_at.date().isoformat() if lesson.last_activity_at else None,
                    }
                )
        if not lessons:
            continue
        exam = next_exam(db, subject.id)
        subjects.append(
            {
                "subject": subject_view(subject),
                "exam": {"date": exam.date.isoformat(), "title": exam.title} if exam else None,
                "mastery": round(sum(x["mastery"] for x in lessons) / len(lessons)),
                "lessons": lessons,
            }
        )
    mocks = [
        {"id": m.id, "subject": db.get(Subject, m.subject_id).name, "note": (m.result or {}).get("note"), "date": (m.finished_at or m.created_at).date().isoformat()}
        for m in db.query(MockExam).filter(MockExam.status == "graded").order_by(MockExam.id.desc()).limit(10)
    ]
    reports = [
        {"id": r.id, "lesson": db.get(Lesson, r.lesson_id).title, "target": r.target, "comment": r.comment, "excerpt": r.excerpt[:300], "date": r.created_at.date().isoformat()}
        for r in db.query(Report).order_by(Report.id.desc()).limit(50)
    ]
    return {
        "streak": activity.streak(db),
        "history": activity.history(db, days=14),
        "subjects": subjects,
        "open_mistakes": db.query(Mistake).filter(Mistake.resolved_at.is_(None)).count(),
        "mock_exams": mocks,
        "reports": reports,
        "settings": {k: settings[k] for k in SETTING_KEYS},
    }


# -- Série de jours, minuteur, récompenses (visibles par l'élève) --------------
class PomodoroIn(BaseModel):
    minutes: int = Field(default=25, ge=1, le=120)


@router.get("/activity")
def get_activity(db: Session = Depends(get_db)) -> dict:
    return {"streak": activity.streak(db), "history": activity.history(db, days=14), "rewards": activity.rewards(db)}


@router.post("/activity/pomodoro")
def pomodoro(body: PomodoroIn, db: Session = Depends(get_db)) -> dict:
    """Une séance de concentration vient de se terminer."""
    activity.touch(db, pomodoro_minutes=body.minutes)
    db.commit()
    return {"streak": activity.streak(db), "rewards": activity.rewards(db)}
