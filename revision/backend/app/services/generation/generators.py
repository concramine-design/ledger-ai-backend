"""Un générateur par type de contenu. Chacun appelle l'IA, valide la réponse et l'enregistre."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from ...config import get_config
from ...models import Artifact, Job, Lesson, Question, QuestionSet
from .. import ingestion
from ..llm import LLMError, LLMRequest, get_llm
from . import prompts
from .content import (
    ExerciseOut,
    Explanation,
    QuestionOut,
    Reexplain,
    Summary,
    shuffle_choices,
    validate,
    validate_items,
)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".heif"}


# -- Outils -------------------------------------------------------------------
def get_artifact(lesson: Lesson, kind: str, ref_id: Optional[int] = None) -> Optional[Artifact]:
    found = [a for a in lesson.artifacts if a.kind == kind and a.ref_id == ref_id]
    return found[-1] if found else None


def save_artifact(db: Session, lesson: Lesson, kind: str, content: dict, ref_id: Optional[int] = None) -> None:
    for old in [a for a in lesson.artifacts if a.kind == kind and a.ref_id == ref_id]:
        lesson.artifacts.remove(old)
    lesson.artifacts.append(Artifact(kind=kind, ref_id=ref_id, content=content))
    db.flush()


def lesson_notions(lesson: Lesson) -> list[str]:
    art = get_artifact(lesson, "explanation")
    return list(art.content.get("notions", [])) if art else []


def build_ctx(lesson: Lesson, with_notions: bool = True) -> prompts.Ctx:
    subject = lesson.subject
    text = (lesson.raw_text or "")[: get_config().lesson_max_chars]
    return prompts.Ctx(
        subject=subject.name,
        language=subject.language,
        chapter=lesson.chapter.title,
        title=lesson.title,
        text=text,
        notions=lesson_notions(lesson) if with_notions else [],
    )


def _ask_json(task: str, ctx: prompts.Ctx, user: str, payload: dict[str, Any], temperature: float = 0.4) -> Any:
    req = LLMRequest(
        task=task,
        system=prompts.system(ctx),
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
        payload={"text": ctx.text, "title": ctx.title, "notions": ctx.notions, **payload},
    )
    return get_llm().generate_json(req)


def _items(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        return data.get(key) or next((v for v in data.values() if isinstance(v, list)), [])
    return data


def _sets(lesson: Lesson, kind: str, level: Optional[int] = None) -> list[QuestionSet]:
    return sorted(
        (s for s in lesson.sets if s.kind == kind and s.level == level), key=lambda s: s.version
    )


# -- Générateurs --------------------------------------------------------------
def gen_extract(db: Session, lesson: Lesson, job: Job) -> None:
    """Lit les fichiers importés (PDF, photos) et en tire le texte de la leçon."""
    subject = lesson.subject
    parts: list[str] = []
    pasted = (job.params or {}).get("pasted_text", "")
    if pasted.strip():
        parts.append(pasted.strip())
    images: list[tuple[bytes, str]] = []
    for f in lesson.files:
        path = Path(f.path)
        if not path.exists():
            raise LLMError("input", f"fichier introuvable : {f.filename}")
        if path.suffix.lower() == ".pdf":
            text, pdf_images = ingestion.read_pdf(path)
            if pdf_images:
                images += pdf_images
            elif text:
                parts.append(text)
        elif path.suffix.lower() in IMAGE_EXT:
            images.append(ingestion.prepare_image(path.read_bytes()))
        else:
            raise LLMError("input", f"format non pris en charge : {f.filename}")
    if images:
        parts.append(ingestion.ocr(get_llm(), images, subject.name, subject.language))
    text = "\n\n".join(p for p in parts if p.strip()).strip()
    if len(text) < 40:
        raise LLMError("input", "texte extrait trop court")
    lesson.raw_text = text
    lesson.truncated = len(text) > get_config().lesson_max_chars


def gen_explanation(db: Session, lesson: Lesson, job: Job) -> None:
    ctx = build_ctx(lesson, with_notions=False)
    data = _ask_json("explanation", ctx, prompts.explanation(ctx), {})
    exp = validate(Explanation, data)
    if not exp.titre:
        exp.titre = lesson.title
    save_artifact(db, lesson, "explanation", exp.model_dump())


def gen_summary(db: Session, lesson: Lesson, job: Job) -> None:
    ctx = build_ctx(lesson)
    data = _ask_json("summary", ctx, prompts.summary(ctx), {})
    summary = validate(Summary, data)
    if not summary.titre:
        summary.titre = lesson.title
    save_artifact(db, lesson, "summary", summary.model_dump())


def _gen_test(db: Session, lesson: Lesson, job: Job, kind: str, minimum: int, maximum: int) -> None:
    params = job.params or {}
    version = int(params.get("version", 1))
    existing = _sets(lesson, kind)
    if any(s.version == version for s in existing):
        return  # déjà généré (reprise après un arrêt)
    avoid = [q.data.get("enonce", "") for s in existing for q in s.questions]
    focus = list(params.get("focus", []))
    ctx = build_ctx(lesson)
    prompt = prompts.minitest(ctx, avoid, focus) if kind == "minitest" else prompts.quiz(ctx, avoid, focus)
    data = _ask_json(kind, ctx, prompt, {"version": version})
    questions = validate_items(QuestionOut, _items(data, "questions"), minimum)[:maximum]
    if kind == "quiz" and sum(q.type == "ouverte" for q in questions) * 2 < len(questions):
        raise LLMError("bad_output", "le quiz doit contenir une majorité de questions ouvertes")
    qset = QuestionSet(kind=kind, version=version)
    for i, q in enumerate(questions):
        shuffle_choices(q, seed=lesson.id * 1000 + version * 31 + i)
        qset.questions.append(Question(position=i, qtype=q.type, notion=q.notion, data=q.model_dump()))
    lesson.sets.append(qset)


def gen_minitest(db: Session, lesson: Lesson, job: Job) -> None:
    _gen_test(db, lesson, job, "minitest", minimum=3, maximum=5)


def gen_quiz(db: Session, lesson: Lesson, job: Job) -> None:
    _gen_test(db, lesson, job, "quiz", minimum=5, maximum=10)


def gen_exercises(db: Session, lesson: Lesson, job: Job) -> None:
    level = int((job.params or {}).get("level", 1))
    if _sets(lesson, "exercises", level):
        return
    ctx = build_ctx(lesson)
    data = _ask_json("exercises", ctx, prompts.exercises(ctx, level), {"level": level})
    exercises = validate_items(ExerciseOut, _items(data, "exercices"), minimum=2)[:4]
    qset = QuestionSet(kind="exercises", level=level)
    for i, ex in enumerate(exercises):
        qset.questions.append(Question(position=i, qtype="exercice", notion=ex.notion, data=ex.model_dump()))
    lesson.sets.append(qset)


def gen_exercise_variant(db: Session, lesson: Lesson, job: Job) -> None:
    """Après lecture d'une correction : un nouvel exercice du même type pour réessayer."""
    original = db.get(Question, int((job.params or {}).get("question_id", 0)))
    if original is None:
        return
    qset = original.qset
    if any(q.parent_id == original.id for q in qset.questions):
        return
    level = qset.level or 1
    ctx = build_ctx(lesson)
    data = _ask_json(
        "exercise_variant",
        ctx,
        prompts.exercise_variant(ctx, level, original.data),
        {"level": level, "index": len(qset.questions), "notion": original.notion},
    )
    if isinstance(data, dict) and isinstance(data.get("exercices"), list) and data["exercices"]:
        data = data["exercices"][0]
    ex = validate(ExerciseOut, data)
    position = max((q.position for q in qset.questions), default=-1) + 1
    qset.questions.append(
        Question(position=position, qtype="exercice", notion=ex.notion or original.notion, data=ex.model_dump(), parent_id=original.id)
    )


def failed_items(qset: QuestionSet) -> list[dict[str, str]]:
    """Les questions ratées d'un test, avec la réponse de l'élève et la réponse attendue."""
    items = []
    for q in qset.questions:
        graded = [a for a in q.attempts if a.status == "graded"]
        if not graded or (graded[-1].score or 0) >= 0.999:
            continue
        att = graded[-1]
        d = q.data
        if q.qtype == "qcm":
            choices = d.get("choix", [])
            given = choices[att.choice_index] if att.choice_index is not None and att.choice_index < len(choices) else ""
            expected = choices[d.get("bonne_reponse", 0)] if choices else ""
        else:
            given, expected = att.answer_text, d.get("reponse_modele", "")
        items.append({"notion": q.notion, "enonce": d.get("enonce", ""), "reponse": given, "attendu": expected})
    return items


def gen_reexplain(db: Session, lesson: Lesson, job: Job) -> None:
    """Après un test raté : réexplique autrement les points ratés."""
    set_id = int((job.params or {}).get("set_id", 0))
    qset = db.get(QuestionSet, set_id)
    if qset is None:
        return
    failed = failed_items(qset)
    if not failed:
        return
    ctx = build_ctx(lesson)
    test_name = "mini-test" if qset.kind == "minitest" else "quiz"
    data = _ask_json("reexplain", ctx, prompts.reexplain(ctx, failed, test_name), {"failed": failed})
    content = validate(Reexplain, data)
    save_artifact(db, lesson, "reexplain", content.model_dump(), ref_id=set_id)


HANDLERS: dict[str, Callable[[Session, Lesson, Job], None]] = {
    "extract": gen_extract,
    "explanation": gen_explanation,
    "summary": gen_summary,
    "minitest": gen_minitest,
    "quiz": gen_quiz,
    "exercises": gen_exercises,
    "exercise_variant": gen_exercise_variant,
    "reexplain": gen_reexplain,
}
