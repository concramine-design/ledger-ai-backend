"""Anciens devoirs surveillés et contrôle blanc."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_config
from ..db import get_db
from ..models import Lesson, MockExam, PastExam, Subject, utcnow
from ..services import activity, exams
from ..services.generation.generators import IMAGE_EXT
from ..services.views import subject_view

router = APIRouter(prefix="/api")

MAX_FILES = 10
MAX_FILE_BYTES = 25 * 1024 * 1024


# -- Anciens devoirs ----------------------------------------------------------
def _past_view(exam: PastExam) -> dict[str, Any]:
    return {
        "id": exam.id,
        "subject_id": exam.subject_id,
        "title": exam.title,
        "status": exam.status,
        "error": exam.error,
        "analysis": exam.analysis,
        "created_at": exam.created_at.date().isoformat(),
    }


def _past_dir(exam_id: int) -> Path:
    return get_config().upload_dir / f"devoir_{exam_id}"


@router.get("/past-exams")
def list_past_exams(db: Session = Depends(get_db)) -> list[dict]:
    """Par matière : les anciens devoirs importés et les types de questions qui reviennent."""
    out = []
    for subject in db.query(Subject).filter(Subject.enabled.is_(True)).order_by(Subject.position, Subject.id):
        items = db.query(PastExam).filter(PastExam.subject_id == subject.id).order_by(PastExam.id.desc()).all()
        out.append(
            {
                "subject": subject_view(subject),
                "exams": [_past_view(e) for e in items],
                "recurring": exams.recurring_types(db, subject.id),
            }
        )
    return out


@router.post("/past-exams")
def import_past_exam(
    subject_id: int = Form(...),
    title: str = Form(""),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.enabled:
        raise HTTPException(404, "Matière introuvable.")
    files = [f for f in files if f.filename]
    text = text.strip()
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Pas plus de {MAX_FILES} fichiers à la fois.")
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext != ".pdf" and ext not in IMAGE_EXT:
            raise HTTPException(422, f"Format non pris en charge : {f.filename}. Utilise un PDF ou des photos.")
    if not files and len(text) < 50:
        raise HTTPException(422, "Colle le texte du devoir, ou ajoute un PDF ou des photos.")
    exam = PastExam(subject_id=subject.id, title=title.strip() or "Devoir surveillé", raw_text=text or None, files=[])
    db.add(exam)
    db.flush()
    saved = []
    if files:
        folder = _past_dir(exam.id)
        folder.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files):
            data = f.file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(422, f"{f.filename} est trop lourd (25 Mo au maximum).")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename or "fichier").name)[-80:]
            path = folder / f"{i:02d}_{safe}"
            path.write_bytes(data)
            saved.append({"name": f.filename, "path": str(path)})
        exam.files = saved
        exam.raw_text = None if not text else text
    db.commit()
    exams.start_analysis(exam.id)
    db.refresh(exam)
    return _past_view(exam)


def _past(db: Session, exam_id: int) -> PastExam:
    exam = db.get(PastExam, exam_id)
    if exam is None:
        raise HTTPException(404, "Devoir introuvable.")
    return exam


@router.post("/past-exams/{exam_id}/retry")
def retry_past_exam(exam_id: int, db: Session = Depends(get_db)) -> dict:
    exam = _past(db, exam_id)
    if exam.status != "ready":
        exam.status = "pending"
        exam.error = None
        db.commit()
        exams.start_analysis(exam.id)
        db.refresh(exam)
    return _past_view(exam)


@router.delete("/past-exams/{exam_id}")
def delete_past_exam(exam_id: int, db: Session = Depends(get_db)) -> dict:
    exam = _past(db, exam_id)
    db.delete(exam)
    db.commit()
    shutil.rmtree(_past_dir(exam_id), ignore_errors=True)
    return {"ok": True}


# -- Contrôle blanc -----------------------------------------------------------
def _paper_view(content: dict[str, Any], with_answers: bool) -> dict[str, Any]:
    """Le sujet tel que l'élève le voit : sans corrigé tant que la copie n'est pas rendue."""
    exercises = []
    for ex in content.get("exercices", []):
        questions = []
        for q in ex["questions"]:
            item = {"numero": q["numero"], "enonce": q["enonce"], "points": q["points"]}
            if with_answers:
                item["correction"] = q.get("correction", "")
            questions.append(item)
        exercises.append({"titre": ex.get("titre", ""), "contexte": ex.get("contexte", ""), "questions": questions})
    return {"titre": content.get("titre", ""), "exercices": exercises}


def _mock_view(db: Session, mock: MockExam) -> dict[str, Any]:
    subject = db.get(Subject, mock.subject_id)
    assert subject is not None
    graded = mock.status == "graded"
    remaining = None
    if mock.status == "started" and mock.started_at:
        remaining = max(0, mock.duration_min * 60 - int((utcnow() - mock.started_at).total_seconds()))
    return {
        "id": mock.id,
        "subject": subject_view(subject),
        "language": subject.language,
        "status": mock.status,
        "error": mock.error,
        "duration_min": mock.duration_min,
        "remaining_seconds": remaining,
        "lessons": [x.title for x in (db.get(Lesson, i) for i in mock.lesson_ids) if x is not None],
        "paper": _paper_view(mock.content, graded) if mock.content and mock.status != "ready" else None,
        "summary": {"exercices": len(mock.content["exercices"]), "questions": sum(len(e["questions"]) for e in mock.content["exercices"])} if mock.content else None,
        "answers": mock.answers or {},
        "result": mock.result if graded else None,
        "created_at": mock.created_at.date().isoformat(),
    }


class MockIn(BaseModel):
    subject_id: int
    lesson_ids: list[int] = Field(default_factory=list)
    duration_min: int = Field(default=60, ge=10, le=180)


@router.get("/mock-exams")
def list_mock_exams(db: Session = Depends(get_db)) -> list[dict]:
    return [_mock_view(db, m) for m in db.query(MockExam).order_by(MockExam.id.desc()).limit(30)]


@router.post("/mock-exams")
def create_mock_exam(body: MockIn, db: Session = Depends(get_db)) -> dict:
    """Prépare un contrôle blanc sur les leçons choisies (par défaut : toutes celles de la matière)."""
    subject = db.get(Subject, body.subject_id)
    if subject is None or not subject.enabled:
        raise HTTPException(404, "Matière introuvable.")
    available = [x for c in subject.chapters for x in c.lessons if x.raw_text]
    chosen = [x for x in available if x.id in body.lesson_ids] if body.lesson_ids else available
    if not chosen:
        raise HTTPException(422, "Importe d'abord au moins une leçon dans cette matière.")
    mock = MockExam(subject_id=subject.id, lesson_ids=[x.id for x in chosen[:8]], duration_min=body.duration_min, answers={})
    db.add(mock)
    db.commit()
    exams.start_generation(mock.id)
    db.refresh(mock)
    return _mock_view(db, mock)


def _mock(db: Session, mock_id: int) -> MockExam:
    mock = db.get(MockExam, mock_id)
    if mock is None:
        raise HTTPException(404, "Contrôle blanc introuvable.")
    return mock


@router.get("/mock-exams/{mock_id}")
def get_mock_exam(mock_id: int, db: Session = Depends(get_db)) -> dict:
    return _mock_view(db, _mock(db, mock_id))


@router.post("/mock-exams/{mock_id}/retry")
def retry_mock_exam(mock_id: int, db: Session = Depends(get_db)) -> dict:
    mock = _mock(db, mock_id)
    if mock.status in ("error", "pending") and not mock.content:
        mock.status = "pending"
        mock.error = None
        db.commit()
        exams.start_generation(mock.id)
        db.refresh(mock)
    return _mock_view(db, mock)


@router.post("/mock-exams/{mock_id}/start")
def start_mock_exam(mock_id: int, db: Session = Depends(get_db)) -> dict:
    """Le chronomètre démarre : le sujet devient visible."""
    mock = _mock(db, mock_id)
    if mock.status == "ready":
        mock.status = "started"
        mock.started_at = utcnow()
        db.commit()
    elif mock.status not in ("started", "graded"):
        raise HTTPException(409, "Ce contrôle blanc n'est pas encore prêt.")
    return _mock_view(db, mock)


class AnswersIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


def _save_answers(mock: MockExam, answers: dict[str, str]) -> None:
    known = {q["numero"] for ex in (mock.content or {}).get("exercices", []) for q in ex["questions"]}
    merged = dict(mock.answers or {})
    merged.update({k: v[:6000] for k, v in answers.items() if k in known})
    mock.answers = merged


@router.put("/mock-exams/{mock_id}/answers")
def save_answers(mock_id: int, body: AnswersIn, db: Session = Depends(get_db)) -> dict:
    """Sauvegarde de la copie en cours d'épreuve (rien n'est perdu si la page est fermée)."""
    mock = _mock(db, mock_id)
    if mock.status != "started":
        raise HTTPException(409, "Ce contrôle blanc n'est pas en cours.")
    _save_answers(mock, body.answers)
    db.commit()
    return {"ok": True}


@router.post("/mock-exams/{mock_id}/submit")
def submit_mock_exam(mock_id: int, body: AnswersIn, db: Session = Depends(get_db)) -> dict:
    """Rend la copie : correction, note sur 20 et bilan des points à retravailler."""
    mock = _mock(db, mock_id)
    if mock.status == "graded":
        return _mock_view(db, mock)
    if mock.status != "started":
        raise HTTPException(409, "Ce contrôle blanc n'est pas en cours.")
    _save_answers(mock, body.answers)
    db.commit()  # la copie est enregistrée avant la correction : en cas de panne de l'IA, on réessaie sans rien perdre
    exams.finish(db, mock)
    activity.touch(db)
    db.commit()
    return _mock_view(db, mock)


@router.delete("/mock-exams/{mock_id}")
def delete_mock_exam(mock_id: int, db: Session = Depends(get_db)) -> dict:
    mock = _mock(db, mock_id)
    db.delete(mock)
    db.commit()
    return {"ok": True}


def resume_pending(db: Session) -> None:
    """Au démarrage : relance ce qui était en cours de préparation."""
    for exam in db.query(PastExam).filter(PastExam.status == "pending").all():
        exams.start_analysis(exam.id)
    for mock in db.query(MockExam).filter(MockExam.status == "pending").all():
        exams.start_generation(mock.id)



