"""Un générateur par type de contenu. Chacun appelle l'IA, valide la réponse et l'enregistre."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from ...config import get_config
from ...models import Artifact, Job, Lesson, Mistake, Question, QuestionSet, ReviewItem
from .. import ingestion, youtube
from ..llm import LLMError, LLMRequest, get_llm
from . import prompts
from .content import (
    ExerciseOut,
    Explanation,
    Methods,
    MindMap,
    QuestionOut,
    Reexplain,
    Summary,
    VideoQueries,
    VideoRank,
    shuffle_choices,
    validate,
    validate_items,
)

DEFAULT_CRITERIA = ["Respect de la consigne", "Organisation des idées", "Correction de la langue", "Richesse du contenu"]

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
        kind=subject.kind,
        code=subject.code or "",
    )


def _ask_json(task: str, ctx: prompts.Ctx, user: str, payload: dict[str, Any], temperature: float = 0.4) -> Any:
    req = LLMRequest(
        task=task,
        system=prompts.system(ctx),
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
        payload={"text": ctx.text, "title": ctx.title, "notions": ctx.notions, "kind": ctx.kind, "code": ctx.code, **payload},
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
    questions = validate_items(QuestionOut, _items(data, "questions"), minimum)[: maximum + 1]
    if ctx.code != "svt":
        questions = [q for q in questions if q.type != "schema"]
    classic = [q for q in questions if q.type != "schema"]
    if len(classic) < minimum:
        raise LLMError("bad_output", "pas assez de questions")
    if kind == "quiz" and sum(q.type == "ouverte" for q in classic) * 2 < len(classic):
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


def _set_mode(ex: ExerciseOut, redaction: bool) -> None:
    """Le mode de correction dépend du niveau et de la matière, pas de ce que l'IA a écrit."""
    ex.mode = "redaction" if redaction else "elements"
    if redaction and not ex.criteres:
        ex.criteres = list(DEFAULT_CRITERIA)
    if not redaction:
        ex.criteres = []


def gen_exercises(db: Session, lesson: Lesson, job: Job) -> None:
    level = int((job.params or {}).get("level", 1))
    if _sets(lesson, "exercises", level):
        return
    ctx = build_ctx(lesson)
    redaction = prompts.is_redaction(ctx, level)
    style = ""
    if level >= 2:  # les exercices « typiques de contrôle » imitent les anciens devoirs de son professeur
        from ..exams import style_hint

        style = style_hint(db, lesson.subject.id)
    data = _ask_json("exercises", ctx, prompts.exercises(ctx, level, style), {"level": level, "redaction": redaction, "style": style})
    exercises = validate_items(ExerciseOut, _items(data, "exercices"), minimum=1 if redaction else 2)[:4]
    qset = QuestionSet(kind="exercises", level=level)
    for i, ex in enumerate(exercises):
        _set_mode(ex, redaction)
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
    _set_mode(ex, original.data.get("mode") == "redaction")
    position = max((q.position for q in qset.questions), default=-1) + 1
    qset.questions.append(
        Question(position=position, qtype="exercice", notion=ex.notion or original.notion, data=ex.model_dump(), parent_id=original.id)
    )


def given_and_expected(question: Question, attempt: Any) -> tuple[str, str]:
    """Sa réponse et la réponse attendue, en texte, quel que soit le type de question."""
    d = question.data
    if question.qtype == "qcm":
        choices = d.get("choix", [])
        index = attempt.choice_index
        given = choices[index] if index is not None and 0 <= index < len(choices) else ""
        return given, (choices[d.get("bonne_reponse", 0)] if choices else "")
    if question.qtype == "schema":
        return attempt.answer_text, " ; ".join(e.get("nom", "") for e in d.get("elements", []))
    if question.qtype == "exercice":
        return attempt.answer_text, d.get("reponse_finale") or " ; ".join(d.get("elements_attendus", []))
    return attempt.answer_text, d.get("reponse_modele", "")


def failed_items(qset: QuestionSet) -> list[dict[str, str]]:
    """Les questions ratées d'un test, avec la réponse de l'élève et la réponse attendue."""
    items = []
    for q in qset.questions:
        graded = [a for a in q.attempts if a.status == "graded"]
        if not graded or (graded[-1].score or 0) >= 0.999:
            continue
        att = graded[-1]
        d = q.data
        given, expected = given_and_expected(q, att)
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


def gen_mindmap(db: Session, lesson: Lesson, job: Job) -> None:
    """Carte mentale de la leçon : un centre, des branches, des feuilles."""
    ctx = build_ctx(lesson)
    data = _ask_json("mindmap", ctx, prompts.mindmap(ctx), {})
    mind = validate(MindMap, data)
    mind.branches = mind.branches[:7]
    for branch in mind.branches:
        branch.feuilles = [f for f in branch.feuilles if f.strip()][:5]
    save_artifact(db, lesson, "mindmap", mind.model_dump())


def gen_methods(db: Session, lesson: Lesson, job: Job) -> None:
    """Fiche « méthodes types » : reconnaître et résoudre chaque type d'exercice."""
    types = list(
        dict.fromkeys(
            q.data.get("type_exercice", "") for s in lesson.sets if s.kind == "exercises" for q in s.questions
        )
    )
    ctx = build_ctx(lesson)
    data = _ask_json("methods", ctx, prompts.methods(ctx, types), {"types": types})
    save_artifact(db, lesson, "methods", validate(Methods, data).model_dump())


def gen_videos(db: Session, lesson: Lesson, job: Job) -> None:
    """Cherche sur YouTube, compare les résultats et garde les 3 meilleures vidéos, avec la raison du choix."""
    key = get_config().youtube_api_key
    if not key:
        save_artifact(db, lesson, "videos", {"status": "no_key", "videos": []})
        return
    ctx = build_ctx(lesson)
    llm = get_llm()
    try:
        data = _ask_json("video_queries", ctx, prompts.video_queries(ctx), {})
        queries = [q for q in validate(VideoQueries, data).requetes if q.strip()][:2]
    except LLMError as exc:
        if exc.kind != "bad_output":
            raise
        queries = []
    if not queries:
        queries = [f"{lesson.title} {lesson.chapter.title} tronc commun"]

    try:
        ids: list[str] = []
        for query in queries:
            for vid in youtube.search(query, ctx.language, key):
                if vid not in ids:
                    ids.append(vid)
        candidates = youtube.details(ids[:20], key)
    except youtube.YouTubeUnavailable as exc:
        # Clé refusée ou quota du jour épuisé : on n'empêche pas l'élève d'avancer, on réessaiera au prochain démarrage.
        save_artifact(db, lesson, "videos", {"status": exc.reason, "videos": []})
        return

    fitting = [c for c in candidates if youtube.MIN_SECONDS <= c["duration_s"] <= youtube.MAX_SECONDS] or candidates
    fitting.sort(key=lambda c: youtube.heuristic_score(c, ctx.language), reverse=True)
    shortlist = fitting[:8]
    if not shortlist:
        save_artifact(db, lesson, "videos", {"status": "none", "videos": []})
        return
    for cand in shortlist[:5]:
        cand["transcript"] = youtube.transcript_excerpt(cand["id"], [ctx.language, "fr", "ar", "en"])

    by_id = {c["id"]: c for c in shortlist}
    chosen: list[tuple[dict, str]] = []
    try:
        req = LLMRequest(
            task="video_rank",
            system=prompts.system(ctx),
            messages=[{"role": "user", "content": prompts.video_rank(ctx, shortlist)}],
            temperature=0.1,
            payload={"candidates": [c["id"] for c in shortlist]},
        )
        ranking = validate(VideoRank, llm.generate_json(req))
        for choice in ranking.selection:
            if choice.id in by_id and all(choice.id != c["id"] for c, _ in chosen):
                chosen.append((by_id[choice.id], choice.raison))
    except LLMError as exc:
        if exc.kind != "bad_output":
            raise
    if not chosen:  # l'IA n'a rien rendu d'exploitable : on garde le premier tri
        chosen = [(c, "Choisie pour son titre, sa durée et son niveau.") for c in shortlist[:3]]

    videos = [
        {
            "id": c["id"],
            "title": c["title"],
            "channel": c["channel"],
            "duration_s": c["duration_s"],
            "raison": reason,
            "subtitles_used": bool(c.get("transcript")),
        }
        for c, reason in chosen[:3]
    ]
    save_artifact(db, lesson, "videos", {"status": "ok", "videos": videos, "queries": queries})


def _asked(lesson: Lesson) -> list[str]:
    """Énoncés déjà posés sur la leçon (tests et rappels), pour ne pas les répéter."""
    sets = sorted((s for s in lesson.sets if s.kind in ("minitest", "quiz", "review")), key=lambda s: s.id)
    return [q.data.get("enonce", "") for s in sets for q in s.questions][-20:]


def _new_review_set(lesson: Lesson, questions: list[QuestionOut]) -> QuestionSet:
    version = sum(s.kind == "review" for s in lesson.sets) + 1
    qset = QuestionSet(kind="review", version=version)
    for i, q in enumerate(questions):
        shuffle_choices(q, seed=lesson.id * 977 + version * 13 + i)
        qset.questions.append(Question(position=i, qtype=q.type, notion=q.notion, data=q.model_dump()))
    lesson.sets.append(qset)
    return qset


def gen_review_set(db: Session, lesson: Lesson, job: Job) -> None:
    """Prépare les 3 questions du prochain rappel d'une leçon maîtrisée."""
    item = db.get(ReviewItem, int((job.params or {}).get("item_id", 0)))
    if item is None or item.state != "active" or item.set_id is not None:
        return
    ctx = build_ctx(lesson)
    data = _ask_json("review_questions", ctx, prompts.review_questions(ctx, _asked(lesson)), {"version": item.stage + 3})
    questions = [q for q in validate_items(QuestionOut, _items(data, "questions"), 2) if q.type != "schema"][:4]
    if len(questions) < 2:
        raise LLMError("bad_output", "pas assez de questions de rappel")
    qset = _new_review_set(lesson, questions)
    db.flush()
    item.set_id = qset.id


def gen_error_variant(db: Session, lesson: Lesson, job: Job) -> None:
    """Carnet d'erreurs : repose l'erreur sous une autre forme."""
    item = db.get(ReviewItem, int((job.params or {}).get("item_id", 0)))
    if item is None or item.state != "active" or item.set_id is not None:
        return
    mistake = db.get(Mistake, item.ref_id) if item.ref_id else None
    if mistake is None:
        item.state = "done"
        return
    info = {"enonce": mistake.enonce, "given": mistake.given, "expected": mistake.expected, "notion": mistake.notion}
    ctx = build_ctx(lesson)
    data = _ask_json("error_variant", ctx, prompts.error_variant(ctx, info), {"mistake": info, "round": mistake.successes + item.stage})
    if isinstance(data, dict) and isinstance(data.get("questions"), list) and data["questions"]:
        data = data["questions"][0]
    question = validate(QuestionOut, data)
    if question.type == "schema":
        raise LLMError("bad_output", "type de question inattendu")
    if not question.notion:
        question.notion = mistake.notion
    qset = _new_review_set(lesson, [question])
    db.flush()
    item.set_id = qset.id


HANDLERS: dict[str, Callable[[Session, Lesson, Job], None]] = {
    "extract": gen_extract,
    "explanation": gen_explanation,
    "summary": gen_summary,
    "minitest": gen_minitest,
    "quiz": gen_quiz,
    "exercises": gen_exercises,
    "exercise_variant": gen_exercise_variant,
    "reexplain": gen_reexplain,
    "methods": gen_methods,
    "mindmap": gen_mindmap,
    "videos": gen_videos,
    "review_set": gen_review_set,
    "error_variant": gen_error_variant,
}
