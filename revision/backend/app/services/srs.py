"""Répétition espacée, carnet d'erreurs et planning « à revoir aujourd'hui ».

Trois sortes d'éléments à revoir :
- « lesson » : après une leçon maîtrisée, un rappel de 3 questions à J+1, J+3, J+7, J+14, J+30 ;
- « error »  : chaque erreur est reposée plus tard sous une autre forme, jusqu'à deux réussites ;
- « card »   : les cartes mémoire de la fiche (définitions, vocabulaire, auteurs).
À l'approche d'un contrôle, les rappels de la matière sont resserrés.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import Exam, Lesson, Mistake, Question, QuestionSet, ReviewItem, utcnow

INTERVALS = [1, 3, 7, 14, 30]  # jours entre deux rappels réussis
PASS_LESSON = 0.6  # score moyen pour qu'un rappel de leçon soit réussi
PASS_ERROR = 0.7
RESOLVED_AFTER = 2  # réussites pour qu'une erreur sorte du carnet
MAX_QUESTION_ITEMS = 8  # par séance
MAX_CARDS = 12


def _next_exam(db: Session, subject_id: int, today: date) -> Optional[Exam]:
    return db.query(Exam).filter(Exam.subject_id == subject_id, Exam.date >= today).order_by(Exam.date).first()


def effective_due(item: ReviewItem, exam_date: Optional[date], today: date) -> date:
    """Date de rappel, avancée si un contrôle de la matière approche."""
    due = item.due
    if exam_date is None or exam_date < today:
        return due
    eve = exam_date - timedelta(days=1)
    last = item.last_reviewed
    # Dans la dernière semaine : jamais plus de deux jours sans rappel.
    if (exam_date - today).days <= 7 and last is not None:
        due = min(due, last + timedelta(days=2))
    # La veille du contrôle : tout est revu une dernière fois.
    if due > eve and eve >= today and (last is None or last < eve):
        due = eve
    return due


# -- Création -----------------------------------------------------------------
def schedule_lesson(db: Session, lesson: Lesson, today: Optional[date] = None) -> Optional[ReviewItem]:
    """Leçon maîtrisée : premier rappel le lendemain."""
    if any(r.kind == "lesson" for r in lesson.reviews):
        return None
    today = today or date.today()
    item = ReviewItem(kind="lesson", due=today + timedelta(days=INTERVALS[0]))
    lesson.reviews.append(item)
    db.flush()
    return item


def schedule_cards(db: Session, lesson: Lesson, cards: list[dict[str, str]], today: Optional[date] = None) -> int:
    """Fiche lue : ses cartes mémoire entrent dans les révisions."""
    if any(r.kind == "card" for r in lesson.reviews):
        return 0
    today = today or date.today()
    for card in cards:
        lesson.reviews.append(ReviewItem(kind="card", data=card, due=today + timedelta(days=INTERVALS[0])))
    db.flush()
    return len(cards)


def record_mistake(
    db: Session, lesson: Lesson, question: Question, given: str, expected: str, source: str, today: Optional[date] = None
) -> Optional[ReviewItem]:
    """Enregistre une erreur dans le carnet et programme sa reprise. Une seule fois par question."""
    if any(m.question_id == question.id for m in lesson.mistakes):
        return None
    today = today or date.today()
    mistake = Mistake(
        question_id=question.id,
        source=source,
        notion=question.notion,
        enonce=question.data.get("enonce", ""),
        given=given,
        expected=expected,
    )
    lesson.mistakes.append(mistake)
    db.flush()
    item = ReviewItem(kind="error", ref_id=mistake.id, due=today + timedelta(days=INTERVALS[0]))
    lesson.reviews.append(item)
    db.flush()
    return item


# -- Résultat d'un rappel -----------------------------------------------------
def _advance(item: ReviewItem, today: date) -> None:
    item.stage += 1
    if item.stage >= len(INTERVALS):
        item.state = "done"
    else:
        item.due = today + timedelta(days=INTERVALS[item.stage])


def finish_questions(db: Session, item: ReviewItem, score: float, today: Optional[date] = None) -> dict[str, Any]:
    """Toutes les questions d'un rappel (leçon ou erreur) sont corrigées : on reprogramme."""
    today = today or date.today()
    item.last_reviewed = today
    item.set_id = None  # les prochaines questions seront nouvelles
    if item.kind == "error":
        mistake = db.get(Mistake, item.ref_id) if item.ref_id else None
        passed = score >= PASS_ERROR
        if passed:
            if mistake is not None:
                mistake.successes += 1
            if mistake is None or mistake.successes >= RESOLVED_AFTER:
                item.state = "done"
                if mistake is not None:
                    mistake.resolved_at = utcnow()
            else:
                _advance(item, today)
        else:
            if mistake is not None:
                mistake.successes = 0
            item.stage = 0
            item.due = today + timedelta(days=INTERVALS[0])
    else:
        passed = score >= PASS_LESSON
        if passed:
            _advance(item, today)
        else:
            item.stage = max(0, item.stage - 1)
            item.due = today + timedelta(days=INTERVALS[0])
    db.flush()
    return {"passed": passed, "done": item.state == "done", "next_due": item.due.isoformat() if item.state == "active" else None}


def answer_card(db: Session, item: ReviewItem, knew: bool, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    item.last_reviewed = today
    if knew:
        _advance(item, today)
    else:
        item.stage = 0
        item.due = today + timedelta(days=INTERVALS[0])
    db.flush()
    return {"passed": knew, "done": item.state == "done", "next_due": item.due.isoformat() if item.state == "active" else None}


# -- Planning -----------------------------------------------------------------
def _ready(db: Session, item: ReviewItem) -> bool:
    """Un rappel à questions n'est proposé que si ses questions sont déjà générées."""
    if item.kind == "card":
        return bool(item.data)
    if item.set_id is None:
        return False
    qset = db.get(QuestionSet, item.set_id)
    return qset is not None and bool(qset.questions)


def _interleave(items: list[tuple[tuple, ReviewItem]]) -> list[ReviewItem]:
    """Mélange les leçons : deux éléments qui se suivent viennent de leçons différentes quand c'est possible."""
    groups: dict[int, list[ReviewItem]] = defaultdict(list)
    for _, item in sorted(items, key=lambda pair: pair[0]):
        groups[item.lesson_id].append(item)
    queues = list(groups.values())
    out: list[ReviewItem] = []
    while queues:
        for queue in list(queues):
            out.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return out


def due_today(db: Session, today: Optional[date] = None) -> dict[str, Any]:
    """Séance du jour : éléments dus, mélangés entre leçons et matières, plafonnés."""
    today = today or date.today()
    exam_cache: dict[int, Optional[date]] = {}
    ranked: list[tuple[tuple, ReviewItem]] = []
    waiting = 0
    for item in db.query(ReviewItem).filter(ReviewItem.state == "active"):
        subject = item.lesson.subject
        if not subject.enabled:
            continue
        if subject.id not in exam_cache:
            exam = _next_exam(db, subject.id, today)
            exam_cache[subject.id] = exam.date if exam else None
        exam_date = exam_cache[subject.id]
        due = effective_due(item, exam_date, today)
        if due > today:
            continue
        if not _ready(db, item):
            waiting += 1
            continue
        days_to_exam = (exam_date - today).days if exam_date else 10**6
        ranked.append(((days_to_exam, due, item.id), item))

    questions = [(k, i) for k, i in ranked if i.kind != "card"]
    cards = [(k, i) for k, i in ranked if i.kind == "card"]
    session = _interleave(questions[:MAX_QUESTION_ITEMS] + cards[:MAX_CARDS])
    return {
        "items": session,
        "remaining": max(0, len(questions) - MAX_QUESTION_ITEMS) + max(0, len(cards) - MAX_CARDS),
        "waiting": waiting,
        "total_due": len(ranked),
    }


def upcoming(db: Session, days: int = 14, today: Optional[date] = None) -> list[dict[str, Any]]:
    """Nombre d'éléments à revoir pour chacun des prochains jours."""
    today = today or date.today()
    counts: dict[date, int] = defaultdict(int)
    exam_cache: dict[int, Optional[date]] = {}
    for item in db.query(ReviewItem).filter(ReviewItem.state == "active"):
        subject = item.lesson.subject
        if not subject.enabled:
            continue
        if subject.id not in exam_cache:
            exam = _next_exam(db, subject.id, today)
            exam_cache[subject.id] = exam.date if exam else None
        due = max(today, effective_due(item, exam_cache[subject.id], today))
        counts[due] += 1
    return [{"date": (today + timedelta(days=i)).isoformat(), "count": counts.get(today + timedelta(days=i), 0)} for i in range(days)]
