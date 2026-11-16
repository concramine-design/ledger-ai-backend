"""Série de jours, minuteur de séance, score de maîtrise et récompenses légères (sans classement)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import ActivityDay, Chapter, Lesson, Mistake, MockExam
from . import parcours, srs


def touch(db: Session, pomodoro_minutes: int = 0, today: Optional[date] = None) -> None:
    """Note qu'elle a travaillé aujourd'hui (une réponse, une étape validée, une séance terminée)."""
    today = today or date.today()
    row = db.get(ActivityDay, today)
    if row is None:
        row = ActivityDay(day=today, actions=0, pomodoros=0, minutes=0)
        db.add(row)
    row.actions += 1
    if pomodoro_minutes:
        row.pomodoros += 1
        row.minutes += pomodoro_minutes


def streak(db: Session, today: Optional[date] = None) -> int:
    """Jours consécutifs travaillés. Une journée pas encore commencée ne casse pas la série."""
    today = today or date.today()
    days = {d for (d,) in db.query(ActivityDay.day).filter(ActivityDay.actions > 0)}
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def history(db: Session, days: int = 14, today: Optional[date] = None) -> list[dict[str, Any]]:
    today = today or date.today()
    rows = {r.day: r for r in db.query(ActivityDay).filter(ActivityDay.day > today - timedelta(days=days))}
    out = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        row = rows.get(day)
        out.append(
            {
                "date": day.isoformat(),
                "actions": row.actions if row else 0,
                "pomodoros": row.pomodoros if row else 0,
                "minutes": row.minutes if row else 0,
            }
        )
    return out


# -- Maîtrise -----------------------------------------------------------------
def lesson_mastery(lesson: Lesson) -> int:
    """Score de 0 à 100 : parcours (70), mémoire dans le temps (20), erreurs retravaillées (10)."""
    done = parcours.done_steps(lesson)
    progress = len([s for s in parcours.ACTIVE_STEPS if s.key in done]) / len(parcours.ACTIVE_STEPS)
    recall = next((r for r in lesson.reviews if r.kind == "lesson"), None)
    memory = 0.0
    if recall is not None:
        memory = 1.0 if recall.state == "done" else min(1.0, recall.stage / len(srs.INTERVALS))
    mistakes = lesson.mistakes
    if not done:
        errors = 0.0
    elif not mistakes:
        errors = 1.0
    else:
        errors = sum(m.resolved_at is not None for m in mistakes) / len(mistakes)
    return round(70 * progress + 20 * memory + 10 * errors)


def color(score: int) -> str:
    return "vert" if score >= 75 else "orange" if score >= 40 else "rouge"


def chapter_mastery(chapter: Chapter) -> Optional[int]:
    if not chapter.lessons:
        return None
    return round(sum(lesson_mastery(x) for x in chapter.lessons) / len(chapter.lessons))


# -- Récompenses --------------------------------------------------------------
def rewards(db: Session) -> list[dict[str, Any]]:
    """Petites étapes franchies. Aucune comparaison avec d'autres élèves."""
    mastered = db.query(Lesson).filter(Lesson.mastered_at.is_not(None)).count()
    lessons = db.query(Lesson).count()
    resolved = db.query(Mistake).filter(Mistake.resolved_at.is_not(None)).count()
    exams = db.query(MockExam).filter(MockExam.status == "graded").count()
    best_streak = _best_streak(db)
    pomodoros = sum(p for (p,) in db.query(ActivityDay.pomodoros))
    table = [
        ("premiere_lecon", "Première leçon importée", "Tu as lancé ta première leçon.", lessons >= 1),
        ("premiere_maitrise", "Première leçon maîtrisée", "Tu es allée jusqu'aux exercices difficiles.", mastered >= 1),
        ("cinq_maitrises", "Cinq leçons maîtrisées", "Cinq leçons menées jusqu'au bout.", mastered >= 5),
        ("serie_3", "Trois jours de suite", "Tu as travaillé trois jours d'affilée.", best_streak >= 3),
        ("serie_7", "Une semaine de suite", "Sept jours d'affilée : la régularité paie.", best_streak >= 7),
        ("erreurs_5", "Cinq erreurs corrigées", "Cinq erreurs du carnet ne te piègent plus.", resolved >= 5),
        ("controle_blanc", "Premier contrôle blanc", "Tu t'es entraînée dans les conditions du contrôle.", exams >= 1),
        ("concentration", "Dix séances de concentration", "Dix séances de 25 minutes terminées.", pomodoros >= 10),
    ]
    return [{"key": k, "label": label, "description": desc, "earned": earned} for k, label, desc, earned in table]


def _best_streak(db: Session) -> int:
    days = sorted(d for (d,) in db.query(ActivityDay.day).filter(ActivityDay.actions > 0))
    best = run = 0
    previous: Optional[date] = None
    for day in days:
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best
