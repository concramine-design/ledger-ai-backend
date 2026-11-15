"""Premier lancement et réglages : matières, langues, dates des contrôles, seuils."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..db import get_db, get_settings, set_setting
from ..models import Exam, Subject
from ..services.llm import get_llm
from ..services.views import exam_view, subject_view

router = APIRouter(prefix="/api")

Kind = Literal["sciences", "langue", "philo"]
Lang = Literal["fr", "ar", "en"]
_COLORS = ["#7c9cff", "#4fd1a5", "#f5b84a", "#ff8fa3", "#c79bff", "#5cc8f0", "#8bd450"]
_THRESHOLDS = ("minitest_threshold", "quiz_threshold", "exercise_threshold")


@router.get("/health")
def health() -> dict:
    return {"ok": True, "app": "revision", "version": APP_VERSION}


@router.get("/state")
def state(db: Session = Depends(get_db)) -> dict:
    settings = get_settings(db)
    llm = get_llm()
    return {
        "version": APP_VERSION,
        "onboarded": bool(settings["onboarded"]),
        "settings": {k: settings[k] for k in (*_THRESHOLDS, "exercises_required")},
        "ai": {"configured": llm.configured, "provider": llm.name, "demo": llm.demo},
    }


# -- Matières -----------------------------------------------------------------
class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Kind = "sciences"
    language: Lang = "fr"


class SubjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    language: Optional[Lang] = None
    enabled: Optional[bool] = None


def _subjects(db: Session) -> list[dict]:
    return [subject_view(s) for s in db.query(Subject).order_by(Subject.position, Subject.id)]


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db)) -> list[dict]:
    return _subjects(db)


@router.post("/subjects")
def add_subject(body: SubjectIn, db: Session = Depends(get_db)) -> list[dict]:
    count = db.query(Subject).count()
    db.add(
        Subject(
            name=body.name.strip(),
            kind=body.kind,
            language=body.language,
            color=_COLORS[count % len(_COLORS)],
            position=count,
        )
    )
    db.commit()
    return _subjects(db)


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: int, body: SubjectPatch, db: Session = Depends(get_db)) -> list[dict]:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Matière introuvable.")
    if body.name is not None:
        subject.name = body.name.strip()
    if body.language is not None:
        subject.language = body.language
    if body.enabled is not None:
        subject.enabled = body.enabled
    db.commit()
    return _subjects(db)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> list[dict]:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Matière introuvable.")
    if subject.chapters:
        raise HTTPException(409, "Cette matière contient des leçons. Désactive-la plutôt que de la supprimer.")
    db.delete(subject)
    db.commit()
    return _subjects(db)


# -- Contrôles ----------------------------------------------------------------
class ExamIn(BaseModel):
    subject_id: int
    date: date
    title: str = Field(default="", max_length=120)


def _exams(db: Session) -> list[dict]:
    return [exam_view(e) for e in db.query(Exam).filter(Exam.date >= date.today()).order_by(Exam.date)]


@router.get("/exams")
def list_exams(db: Session = Depends(get_db)) -> list[dict]:
    return _exams(db)


@router.post("/exams")
def add_exam(body: ExamIn, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Subject, body.subject_id) is None:
        raise HTTPException(404, "Matière introuvable.")
    if body.date < date.today():
        raise HTTPException(422, "Cette date est déjà passée.")
    db.add(Exam(subject_id=body.subject_id, date=body.date, title=body.title.strip()))
    db.commit()
    return _exams(db)


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: int, db: Session = Depends(get_db)) -> list[dict]:
    exam = db.get(Exam, exam_id)
    if exam is not None:
        db.delete(exam)
        db.commit()
    return _exams(db)


# -- Fin du premier lancement et seuils ---------------------------------------
@router.post("/onboarding/complete")
def complete_onboarding(db: Session = Depends(get_db)) -> dict:
    if db.query(Subject).filter(Subject.enabled.is_(True)).count() == 0:
        raise HTTPException(422, "Garde au moins une matière.")
    set_setting(db, "onboarded", True)
    db.commit()
    return {"ok": True}


class SettingsPatch(BaseModel):
    minitest_threshold: Optional[int] = Field(default=None, ge=40, le=100)
    quiz_threshold: Optional[int] = Field(default=None, ge=50, le=100)
    exercise_threshold: Optional[int] = Field(default=None, ge=40, le=100)
    exercises_required: Optional[int] = Field(default=None, ge=1, le=3)


@router.patch("/settings")
def update_settings(body: SettingsPatch, db: Session = Depends(get_db)) -> dict:
    for key, value in body.model_dump(exclude_none=True).items():
        set_setting(db, key, value)
    db.commit()
    settings = get_settings(db)
    return {k: settings[k] for k in (*_THRESHOLDS, "exercises_required")}
