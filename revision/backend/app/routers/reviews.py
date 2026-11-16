"""Révision du jour, planning, carnet d'erreurs et méthodes types."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Chapter, Exam, Mistake, QuestionSet, ReviewItem
from ..services import activity, srs
from ..services.generation.generators import get_artifact
from ..services.views import exam_view, subject_view, test_question_view

router = APIRouter(prefix="/api")


def _lesson_brief(item: ReviewItem) -> dict[str, Any]:
    lesson = item.lesson
    return {
        "id": lesson.id,
        "title": lesson.title,
        "chapter": lesson.chapter.title,
        "subject": subject_view(lesson.subject),
        "language": lesson.subject.language,
    }


def item_view(db: Session, item: ReviewItem) -> dict[str, Any]:
    out: dict[str, Any] = {"id": item.id, "kind": item.kind, "stage": item.stage, "lesson": _lesson_brief(item)}
    if item.kind == "card":
        out["card"] = item.data
    else:
        qset = db.get(QuestionSet, item.set_id) if item.set_id else None
        out["questions"] = [test_question_view(q) for q in qset.questions] if qset else []
        if item.kind == "error" and item.ref_id:
            mistake = db.get(Mistake, item.ref_id)
            if mistake is not None:
                out["mistake"] = {"enonce": mistake.enonce, "created_at": mistake.created_at.date().isoformat()}
    return out


def session_size(items: list[dict[str, Any]]) -> dict[str, int]:
    questions = sum(len(i.get("questions", [])) for i in items)
    cards = sum(i["kind"] == "card" for i in items)
    return {"questions": questions, "cards": cards, "minutes": max(1, round(questions * 1.5 + cards * 0.3))}


@router.get("/reviews/today")
def today(db: Session = Depends(get_db)) -> dict:
    """« À revoir aujourd'hui » : la séance du jour, qui mélange leçons et matières."""
    plan = srs.due_today(db)
    items = [item_view(db, i) for i in plan["items"]]
    return {
        "items": items,
        "size": session_size(items),
        "remaining": plan["remaining"],
        "waiting": plan["waiting"],
        "total_due": plan["total_due"],
    }


class CardIn(BaseModel):
    knew: bool


@router.post("/reviews/{item_id}/card")
def answer_card(item_id: int, body: CardIn, db: Session = Depends(get_db)) -> dict:
    item = db.get(ReviewItem, item_id)
    if item is None or item.kind != "card" or item.state != "active":
        raise HTTPException(404, "Carte introuvable.")
    result = srs.answer_card(db, item, body.knew)
    activity.touch(db)
    db.commit()
    return result


@router.get("/reviews/plan")
def plan(db: Session = Depends(get_db)) -> dict:
    """Planning : ce qui est dû aujourd'hui, les prochains jours, et les contrôles à venir."""
    due = srs.due_today(db)
    items = [item_view(db, i) for i in due["items"]]
    by_subject: dict[str, dict[str, Any]] = {}
    for i in items:
        subject = i["lesson"]["subject"]
        entry = by_subject.setdefault(subject["name"], {"subject": subject, "lessons": set(), "count": 0})
        entry["lessons"].add(i["lesson"]["title"])
        entry["count"] += 1
    exams = db.query(Exam).filter(Exam.date >= date.today()).order_by(Exam.date).all()
    return {
        "today": {
            "size": session_size(items),
            "total_due": due["total_due"],
            "remaining": due["remaining"],
            "waiting": due["waiting"],
            "subjects": [{"subject": e["subject"], "lessons": sorted(e["lessons"]), "count": e["count"]} for e in by_subject.values()],
        },
        "upcoming": srs.upcoming(db),
        "exams": [exam_view(e) for e in exams if e.subject.enabled],
        "open_mistakes": db.query(Mistake).filter(Mistake.resolved_at.is_(None)).count(),
    }


@router.get("/mistakes")
def mistakes(db: Session = Depends(get_db)) -> list[dict]:
    """Carnet d'erreurs : chaque erreur, sa correction, et quand elle sera reposée."""
    items = {r.ref_id: r for r in db.query(ReviewItem).filter(ReviewItem.kind == "error")}
    out = []
    for m in db.query(Mistake).order_by(Mistake.resolved_at.is_not(None), Mistake.created_at.desc()):
        lesson = m.lesson
        if not lesson.subject.enabled:
            continue
        item = items.get(m.id)
        out.append(
            {
                "id": m.id,
                "lesson": {"id": lesson.id, "title": lesson.title, "subject": subject_view(lesson.subject), "language": lesson.subject.language},
                "source": m.source,
                "notion": m.notion,
                "enonce": m.enonce,
                "given": m.given,
                "expected": m.expected,
                "created_at": m.created_at.date().isoformat(),
                "resolved": m.resolved_at is not None,
                "successes": m.successes,
                "next_due": item.due.isoformat() if item is not None and item.state == "active" else None,
            }
        )
    return out


@router.get("/chapters/{chapter_id}/methods")
def chapter_methods(chapter_id: int, db: Session = Depends(get_db)) -> dict:
    """Fiche « méthodes types » du chapitre : reconnaître et résoudre chaque type d'exercice."""
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404, "Chapitre introuvable.")
    lessons = []
    for lesson in sorted(chapter.lessons, key=lambda x: x.id):
        art = get_artifact(lesson, "methods")
        if art is not None:
            lessons.append({"id": lesson.id, "title": lesson.title, "types": art.content.get("types", [])})
    return {
        "chapter": {"id": chapter.id, "title": chapter.title},
        "subject": subject_view(chapter.subject),
        "language": chapter.subject.language,
        "lessons": lessons,
    }
