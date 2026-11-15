"""Import des leçons, liste, et écran « Ta prochaine étape »."""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_config
from ..db import get_db
from ..models import Chapter, Lesson, LessonFile, Subject
from ..services import parcours, srs
from ..services.generation.generators import IMAGE_EXT
from ..services.generation.worker import enqueue_initial, retry_lesson
from ..services.views import exam_view, generation_status, lesson_view, next_exam, step_ready, subject_available, subject_view

router = APIRouter(prefix="/api")

MAX_FILES = 15
MAX_FILE_BYTES = 25 * 1024 * 1024
MIN_TEXT_CHARS = 50


def get_lesson(db: Session, lesson_id: int) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "Leçon introuvable.")
    return lesson


def _lesson_dir(lesson_id: int) -> Path:
    return get_config().upload_dir / f"lecon_{lesson_id}"


@router.get("/chapters")
def list_chapters(subject_id: int, db: Session = Depends(get_db)) -> list[dict]:
    chapters = db.query(Chapter).filter(Chapter.subject_id == subject_id).order_by(Chapter.position, Chapter.id)
    return [{"id": c.id, "title": c.title} for c in chapters]


@router.post("/lessons")
def import_lesson(
    subject_id: int = Form(...),
    chapter_title: str = Form(...),
    title: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    """Enregistre la leçon et lance toute la génération en arrière-plan."""
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.enabled:
        raise HTTPException(404, "Matière introuvable.")
    if not subject_available(subject):
        raise HTTPException(422, f"Le parcours de {subject.name} arrive dans la prochaine version.")
    chapter_title, title, text = chapter_title.strip(), title.strip(), text.strip()
    if not chapter_title or not title:
        raise HTTPException(422, "Indique le chapitre et le titre de la leçon.")
    files = [f for f in files if f.filename]
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Pas plus de {MAX_FILES} fichiers à la fois.")
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext != ".pdf" and ext not in IMAGE_EXT:
            raise HTTPException(422, f"Format non pris en charge : {f.filename}. Utilise un PDF ou des photos.")
    if not files and len(text) < MIN_TEXT_CHARS:
        raise HTTPException(422, "Le texte de la leçon est trop court. Colle la leçon entière.")

    chapter = (
        db.query(Chapter)
        .filter(Chapter.subject_id == subject.id)
        .all()
    )
    match = next((c for c in chapter if c.title.strip().lower() == chapter_title.lower()), None)
    if match is None:
        match = Chapter(subject_id=subject.id, title=chapter_title, position=len(chapter))
        db.add(match)
        db.flush()

    has_pdf = any(Path(f.filename or "").suffix.lower() == ".pdf" for f in files)
    lesson = Lesson(
        chapter_id=match.id,
        title=title,
        source_type="text" if not files else "pdf" if has_pdf else "photo",
        raw_text=text if not files else None,
    )
    db.add(lesson)
    db.flush()
    if lesson.raw_text:
        lesson.truncated = len(lesson.raw_text) > get_config().lesson_max_chars

    if files:
        folder = _lesson_dir(lesson.id)
        folder.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files):
            data = f.file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(422, f"{f.filename} est trop lourd (25 Mo au maximum).")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename or "fichier").name)[-80:]
            path = folder / f"{i:02d}_{safe}"
            path.write_bytes(data)
            lesson.files.append(LessonFile(filename=f.filename or safe, path=str(path), mime=f.content_type or "", position=i))

    enqueue_initial(db, lesson, pasted_text=text if files else "")
    db.commit()
    return lesson_view(db, lesson, detailed=True)


@router.get("/lessons")
def list_lessons(db: Session = Depends(get_db)) -> list[dict]:
    """Les leçons, rangées par matière puis par chapitre."""
    out = []
    for subject in db.query(Subject).filter(Subject.enabled.is_(True)).order_by(Subject.position, Subject.id):
        chapters = []
        for chapter in sorted(subject.chapters, key=lambda c: (c.position, c.id)):
            lessons = [lesson_view(db, lesson) for lesson in sorted(chapter.lessons, key=lambda x: x.id)]
            if lessons:
                chapters.append({"id": chapter.id, "title": chapter.title, "lessons": lessons})
        exam = next_exam(db, subject.id)
        out.append({"subject": subject_view(subject), "exam": exam_view(exam) if exam else None, "chapters": chapters})
    return out


@router.get("/lessons/{lesson_id}")
def lesson_detail(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    return lesson_view(db, get_lesson(db, lesson_id), detailed=True)


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    chapter = lesson.chapter
    db.delete(lesson)
    db.flush()
    db.refresh(chapter)
    if not chapter.lessons:
        db.delete(chapter)
    db.commit()
    shutil.rmtree(_lesson_dir(lesson_id), ignore_errors=True)
    return {"ok": True}


@router.post("/lessons/{lesson_id}/retry")
def retry(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    retry_lesson(db, lesson)
    db.commit()
    return lesson_view(db, lesson, detailed=True)


@router.get("/lessons/{lesson_id}/source")
def lesson_source(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    return {"text": lesson.raw_text or "", "language": lesson.subject.language, "truncated": lesson.truncated}


class SourceIn(BaseModel):
    text: str = Field(min_length=MIN_TEXT_CHARS)


@router.put("/lessons/{lesson_id}/source")
def replace_source(lesson_id: int, body: SourceIn, db: Session = Depends(get_db)) -> dict:
    """Corrige le texte lu (par exemple après une photo mal lue) : tout est régénéré."""
    lesson = get_lesson(db, lesson_id)
    for collection in (lesson.jobs, lesson.artifacts, lesson.sets, lesson.progress, lesson.messages, lesson.mistakes, lesson.reviews):
        collection.clear()
    db.flush()
    lesson.raw_text = body.text.strip()
    lesson.truncated = len(lesson.raw_text) > get_config().lesson_max_chars
    lesson.mastered_at = None
    lesson.files.clear()
    db.flush()
    enqueue_initial(db, lesson)
    db.commit()
    shutil.rmtree(_lesson_dir(lesson_id), ignore_errors=True)
    return lesson_view(db, lesson, detailed=True)


@router.get("/next")
def next_step(db: Session = Depends(get_db)) -> dict:
    """« Ta prochaine étape » : la leçon la plus urgente et son étape en cours."""
    lessons = [
        lesson
        for lesson in db.query(Lesson).all()
        if lesson.subject.enabled
    ]
    if not lessons:
        return {"kind": "import"}

    # D'abord ce qui est à revoir aujourd'hui : c'est court, et c'est ce qui fixe la mémoire.
    plan = srs.due_today(db)
    if plan["items"]:
        from .reviews import item_view, session_size

        items = [item_view(db, i) for i in plan["items"]]
        subjects = list(dict.fromkeys(i["lesson"]["subject"]["name"] for i in items))
        return {"kind": "review", "size": session_size(items), "subjects": subjects, "lessons": len({i["lesson"]["id"] for i in items})}

    todo = [lesson for lesson in lessons if lesson.mastered_at is None]
    if not todo:
        upcoming = next((d for d in srs.upcoming(db, days=60) if d["count"]), None)
        return {"kind": "done", "mastered": len(lessons), "next_review": upcoming["date"] if upcoming else None}

    def urgency(lesson: Lesson) -> tuple:
        exam = next_exam(db, lesson.subject.id)
        days = (exam.date - date.today()).days if exam else 10**6
        started = 0 if lesson.progress else 1
        return (days, started, lesson.id)

    lesson = min(todo, key=urgency)
    step = parcours.current_step(lesson)
    assert step is not None
    exam: Optional[object] = next_exam(db, lesson.subject.id)
    return {
        "kind": "step",
        "lesson": lesson_view(db, lesson),
        "step": {"key": step.key, "label": step.label, "description": step.description, "minutes": step.minutes},
        "ready": step_ready(lesson, step),
        "generation": generation_status(lesson),
        "exam": exam_view(exam) if exam else None,  # type: ignore[arg-type]
        "mastered": len(lessons) - len(todo),
        "total": len(lessons),
    }
