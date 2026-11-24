"""File de tâches de génération, stockée en SQLite.

- L'import d'une leçon crée toutes les tâches ; un fil d'exécution les traite en arrière-plan.
- Panne passagère (internet, quota) : la tâche reste en file et repart toute seule.
- Rien n'est perdu à l'arrêt : au redémarrage, les tâches en cours reprennent.
"""
from __future__ import annotations

import logging
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ...db import new_session
from ...models import Job, Lesson, utcnow
from ..llm import LLMError
from .generators import HANDLERS

log = logging.getLogger("revision.worker")

JOB_LABELS = {
    "extract": "Lecture du document",
    "explanation": "Explication",
    "minitest": "Mini-test",
    "summary": "Résumé",
    "quiz": "Quiz",
    "exercises": "Exercices",
    "exercise_variant": "Nouvel exercice",
    "reexplain": "Nouvelle explication",
    "videos": "Sélection de vidéos",
    "mindmap": "Carte mentale",
    "methods": "Méthodes types",
    "review_set": "Prochain rappel",
    "error_variant": "Reprise d'une erreur",
}

# Tâches prévisibles, que Claude peut préparer la nuit (mode PREPARATION_PAR=claude).
# Les réactions immédiates (nouveau test après un échec, ré-explication, nouvel exercice) restent automatiques.
CLAUDE_KINDS = {"extract", "explanation", "minitest", "mindmap", "summary", "quiz", "exercises", "methods", "review_set", "error_variant"}

_BACKOFF = [10, 20, 45, 90, 180, 300]  # secondes
_MAX_BAD_OUTPUT = 3


def job_label(job: Job) -> str:
    label = JOB_LABELS.get(job.kind, job.kind)
    if job.kind == "exercises":
        label += f" niveau {(job.params or {}).get('level', '')}"
    return label


def _executor(kind: str, params: dict[str, Any]) -> str:
    from ...config import get_config

    if get_config().preparation_par != "claude" or kind not in CLAUDE_KINDS:
        return "auto"
    if kind in ("minitest", "quiz") and int(params.get("version", 1)) > 1:
        return "auto"  # nouveau test après un échec : elle ne doit pas attendre le lendemain
    return "claude"


def _limit_time() -> tuple[int, int]:
    from ...config import get_config

    try:
        hour, minute = (int(x) for x in get_config().heure_limite_claude.strip().split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except ValueError:
        pass
    return 7, 0


def claude_deadline(job: Job) -> datetime:
    """Heure (UTC) à partir de laquelle la file prend le relais si Claude n'est pas passé :
    la prochaine HEURE_LIMITE_CLAUDE (heure locale du PC) après la création de la tâche."""
    hour, minute = _limit_time()
    created = job.created_at.replace(tzinfo=timezone.utc).astimezone()  # heure locale du PC
    target = created.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= created:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc).replace(tzinfo=None)


def waiting_for_claude(job: Job, now=None) -> bool:
    return job.status == "pending" and job.executor == "claude" and claude_deadline(job) > (now or utcnow())


def enqueue(
    db: Session,
    lesson: Lesson,
    kind: str,
    params: Optional[dict[str, Any]] = None,
    priority: int = 50,
    depends_on: Optional[str] = None,
) -> Job:
    job = Job(kind=kind, params=params or {}, priority=priority, depends_on=depends_on, executor=_executor(kind, params or {}))
    lesson.jobs.append(job)
    db.flush()
    return job


def enqueue_initial(db: Session, lesson: Lesson, pasted_text: str = "") -> None:
    """Tout ce qui est généré automatiquement dès l'import. L'explication passe en premier."""
    if lesson.files:
        enqueue(db, lesson, "extract", {"pasted_text": pasted_text}, priority=0)
    enqueue(db, lesson, "explanation", priority=10, depends_on="extract")
    enqueue(db, lesson, "minitest", {"version": 1}, priority=20, depends_on="explanation")
    enqueue(db, lesson, "mindmap", priority=22, depends_on="explanation")
    enqueue(db, lesson, "videos", priority=25, depends_on="explanation")
    enqueue(db, lesson, "summary", priority=30, depends_on="explanation")
    enqueue(db, lesson, "quiz", {"version": 1}, priority=40, depends_on="explanation")
    for level in (1, 2, 3):
        enqueue(db, lesson, "exercises", {"level": level}, priority=50 + level, depends_on="explanation")
    if lesson.subject.kind == "sciences":
        enqueue(db, lesson, "methods", priority=58, depends_on="exercises")


def backfill(db: Session) -> None:
    """Au démarrage : ajoute aux leçons existantes ce qu'une version plus récente sait générer."""
    from ...config import get_config

    from .. import parcours

    has_key = bool(get_config().youtube_api_key)
    for lesson in db.query(Lesson).all():
        kinds = {j.kind for j in lesson.jobs}
        if "explanation" not in kinds:
            continue
        parcours.adopt_new_steps(lesson)
        if "mindmap" not in kinds:
            enqueue(db, lesson, "mindmap", priority=22, depends_on="explanation")
        videos = next((a for a in lesson.artifacts if a.kind == "videos"), None)
        pending = any(j.kind == "videos" and j.status != "done" for j in lesson.jobs)
        retry = videos is not None and videos.content.get("status") in ("no_key", "key", "quota") and has_key
        if not pending and ("videos" not in kinds or retry):
            enqueue(db, lesson, "videos", priority=25, depends_on="explanation")
        if "methods" not in kinds and lesson.subject.kind == "sciences":
            enqueue(db, lesson, "methods", priority=58, depends_on="exercises")


def _runnable(db: Session, job: Job) -> bool:
    if not job.depends_on:
        return True
    blockers = (
        db.query(Job)
        .filter(Job.lesson_id == job.lesson_id, Job.kind == job.depends_on, Job.status != "done")
        .count()
    )
    return blockers == 0


def claim_next(db: Session, ignore_backoff: bool = False) -> Optional[int]:
    now = utcnow()
    for job in db.query(Job).filter(Job.status == "pending").order_by(Job.priority, Job.id):
        if not ignore_backoff and job.next_try_at and job.next_try_at > now:
            continue
        if waiting_for_claude(job, now):
            continue  # réservée à Claude jusqu'au délai de repli
        if not _runnable(db, job):
            continue
        job.status = "running"
        db.commit()
        return job.id
    return None


def _record_failure(job_id: int, exc: LLMError) -> None:
    with closing(new_session()) as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.attempts += 1
        job.error_kind = exc.kind
        job.last_error = exc.message
        if exc.transient:
            delay = _BACKOFF[min(job.attempts - 1, len(_BACKOFF) - 1)]
            if exc.retry_after:
                delay = int(min(max(delay, exc.retry_after), 900))
            job.status = "pending"
            job.next_try_at = utcnow() + timedelta(seconds=delay)
        elif exc.kind in ("bad_output", "internal") and job.attempts < _MAX_BAD_OUTPUT:
            job.status = "pending"
            job.next_try_at = utcnow() + timedelta(seconds=3)
        else:
            job.status = "failed"
            job.next_try_at = None
        db.commit()


def process(job_id: int) -> None:
    with closing(new_session()) as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        try:
            lesson = db.get(Lesson, job.lesson_id)
            if lesson is None:
                return
            HANDLERS[job.kind](db, lesson, job)
            if db.query(Job.id).filter(Job.id == job_id).scalar() is None:
                db.rollback()  # la leçon a été supprimée ou régénérée pendant l'appel à l'IA
                return
            job.status = "done"
            job.error_kind = None
            job.last_error = None
            job.next_try_at = None
            db.commit()
        except LLMError as exc:
            db.rollback()
            log.warning("tâche %s (%s) : %s — %s", job_id, job.kind, exc.kind, exc.detail[:300])
            _record_failure(job_id, exc)
        except Exception as exc:  # noqa: BLE001 - une tâche ne doit jamais arrêter la file
            db.rollback()
            log.exception("tâche %s : erreur inattendue", job_id)
            _record_failure(job_id, LLMError("internal", repr(exc)))


def run_pending(ignore_backoff: bool = True, limit: int = 200) -> int:
    """Traite la file jusqu'au bout, dans le fil courant (tests)."""
    count = 0
    while count < limit:
        with closing(new_session()) as db:
            job_id = claim_next(db, ignore_backoff=ignore_backoff)
        if job_id is None:
            break
        process(job_id)
        count += 1
    return count


def recover_on_startup() -> None:
    """Au démarrage : reprend les tâches interrompues et retente celles qui avaient échoué."""
    with closing(new_session()) as db:
        for job in db.query(Job).filter(Job.status.in_(["running", "failed"])):
            job.status = "pending"
            job.attempts = 0
            job.next_try_at = None
        backfill(db)
        db.commit()


def hand_over_to_gemini(db: Session, lesson: Lesson) -> int:
    """Bouton « Préparer maintenant » : la file prépare tout de suite ce qui attendait Claude."""
    count = 0
    for job in lesson.jobs:
        if waiting_for_claude(job):
            job.executor = "auto"
            job.next_try_at = None
            count += 1
    return count


def retry_lesson(db: Session, lesson: Lesson) -> None:
    """Bouton « Réessayer » : relance tout de suite ce qui attend ou a échoué."""
    for job in lesson.jobs:
        if job.status == "failed":
            job.status = "pending"
            job.attempts = 0
        if job.status == "pending":
            job.next_try_at = None


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="generation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with closing(new_session()) as db:
                    job_id = claim_next(db)
                if job_id is None:
                    self._stop.wait(1.0)
                    continue
                process(job_id)
            except Exception:  # noqa: BLE001
                log.exception("erreur dans la file de génération")
                self._stop.wait(2.0)


worker = Worker()
