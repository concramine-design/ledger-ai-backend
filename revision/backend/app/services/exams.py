"""Anciens devoirs surveillés et contrôle blanc."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..config import get_config
from ..db import new_session
from ..models import Lesson, MockExam, PastExam, Subject, utcnow
from . import background, ingestion
from .generation import prompts
from .generation.content import ExamNotes, ExamPaper, PastExamAnalysis, validate
from .generation.generators import IMAGE_EXT
from .llm import LLMError, LLMRequest, get_llm

MAX_EXAM_TEXT = 12000


# -- Anciens devoirs ----------------------------------------------------------
def recurring_types(db: Session, subject_id: int) -> list[dict[str, Any]]:
    """Types de questions repérés dans les anciens devoirs de la matière, du plus fréquent au plus rare."""
    counter: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for exam in db.query(PastExam).filter(PastExam.subject_id == subject_id, PastExam.status == "ready"):
        seen = set()
        for t in (exam.analysis or {}).get("types", []):
            name = str(t.get("type", "")).strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                counter[name] += 1
                examples.setdefault(name, t.get("exemple", ""))
    return [{"type": name, "count": count, "exemple": examples[name]} for name, count in counter.most_common()]


def style_hint(db: Session, subject_id: int) -> str:
    """Résumé du style du professeur, glissé dans les consignes de génération."""
    types = recurring_types(db, subject_id)
    if not types:
        return ""
    lines = [f"- {t['type']} (vu dans {t['count']} devoir{'s' if t['count'] > 1 else ''})" for t in types[:8]]
    styles = [
        (e.analysis or {}).get("style", "")
        for e in db.query(PastExam).filter(PastExam.subject_id == subject_id, PastExam.status == "ready").order_by(PastExam.id.desc()).limit(2)
    ]
    return "Types de questions qui reviennent :\n" + "\n".join(lines) + "\n" + " ".join(s for s in styles if s)


def _extract(exam: PastExam, subject: Subject) -> str:
    parts: list[str] = []
    images: list[tuple[bytes, str]] = []
    for info in exam.files or []:
        path = Path(info["path"])
        if path.suffix.lower() == ".pdf":
            text, pdf_images = ingestion.read_pdf(path)
            if pdf_images:
                images += pdf_images
            elif text:
                parts.append(text)
        elif path.suffix.lower() in IMAGE_EXT:
            images.append(ingestion.prepare_image(path.read_bytes()))
    if images:
        parts.append(ingestion.ocr(get_llm(), images, subject.name, subject.language))
    return "\n\n".join(p for p in parts if p.strip()).strip()


def _analyse(exam_id: int) -> None:
    with closing(new_session()) as db:
        exam = db.get(PastExam, exam_id)
        if exam is None:
            return
        subject = db.get(Subject, exam.subject_id)
        assert subject is not None
        if not exam.raw_text:
            text = _extract(exam, subject)
            if len(text) < 40:
                raise LLMError("input", "texte du devoir trop court")
            exam.raw_text = text
            db.commit()
        known = [t["type"] for t in recurring_types(db, subject.id)]
        req = LLMRequest(
            task="past_exam_analysis",
            system="Tu es un professeur marocain de lycée qui analyse des devoirs surveillés de tronc commun. "
            "Réponds par un unique objet JSON valide, en français.",
            messages=[{"role": "user", "content": prompts.past_exam_analysis(subject.name, exam.raw_text[:MAX_EXAM_TEXT], known)}],
            temperature=0.2,
            payload={"text": exam.raw_text, "known": known},
        )
        analysis = validate(PastExamAnalysis, get_llm().generate_json(req))
        exam.analysis = analysis.model_dump()
        exam.status = "ready"
        exam.error = None
        db.commit()


def _past_exam_error(exam_id: int, exc: LLMError) -> None:
    with closing(new_session()) as db:
        exam = db.get(PastExam, exam_id)
        if exam is not None:
            exam.status = "error"
            exam.error = exc.message
            db.commit()


def start_analysis(exam_id: int) -> None:
    background.launch(lambda: _analyse(exam_id), lambda exc: _past_exam_error(exam_id, exc))


# -- Contrôle blanc -----------------------------------------------------------
def _generate(mock_id: int) -> None:
    with closing(new_session()) as db:
        mock = db.get(MockExam, mock_id)
        if mock is None or mock.content:
            return
        subject = db.get(Subject, mock.subject_id)
        assert subject is not None
        lessons = [x for x in (db.get(Lesson, i) for i in mock.lesson_ids) if x is not None and x.raw_text]
        if not lessons:
            raise LLMError("input", "aucune leçon au programme")
        budget = max(1500, get_config().lesson_max_chars // len(lessons))
        blocks = [{"title": x.title, "text": (x.raw_text or "")[:budget]} for x in lessons]
        style = style_hint(db, subject.id)
        req = LLMRequest(
            task="mock_exam",
            system=f"Tu es un professeur de {subject.name} au lycée marocain. Tu rédiges un devoir surveillé de tronc commun, "
            "fidèle aux leçons fournies. Formules en LaTeX entre $...$. Réponds par un unique objet JSON valide ; "
            "dans les chaînes JSON, double chaque barre oblique inverse du LaTeX.",
            messages=[{"role": "user", "content": prompts.mock_exam(subject.name, subject.language, blocks, mock.duration_min, style)}],
            temperature=0.5,
            payload={"lessons": blocks, "duration": mock.duration_min, "style": style},
        )
        paper = validate(ExamPaper, get_llm().generate_json(req))
        paper.normalise()
        titles = {x.title.strip().lower(): x for x in lessons}
        content = paper.model_dump()
        for ex in content["exercices"]:
            for q in ex["questions"]:
                match = titles.get(str(q.get("lecon", "")).strip().lower())
                q["lesson_id"] = match.id if match else (lessons[0].id if len(lessons) == 1 else None)
        if not content.get("titre"):
            content["titre"] = f"Contrôle blanc de {subject.name}"
        mock.content = content
        mock.status = "ready"
        mock.error = None
        db.commit()


def _mock_error(mock_id: int, exc: LLMError) -> None:
    with closing(new_session()) as db:
        mock = db.get(MockExam, mock_id)
        if mock is not None and not mock.content:
            mock.status = "error"
            mock.error = exc.message
            db.commit()


def start_generation(mock_id: int) -> None:
    background.launch(lambda: _generate(mock_id), lambda exc: _mock_error(mock_id, exc))


def grade(db: Session, mock: MockExam) -> dict[str, Any]:
    """Corrige la copie : une demande à l'IA par exercice. Note sur 20 et bilan des points à retravailler."""
    subject = db.get(Subject, mock.subject_id)
    assert subject is not None and mock.content is not None
    answers = {k: str(v) for k, v in (mock.answers or {}).items()}
    graded: list[dict[str, Any]] = []
    for ex in mock.content["exercices"]:
        questions = ex["questions"]
        notes: dict[str, tuple[float, str]] = {}
        if any(answers.get(q["numero"], "").strip() for q in questions):
            req = LLMRequest(
                task="mock_exam_grade",
                system=f"Tu es un professeur de {subject.name} qui corrige un devoir surveillé de tronc commun. "
                f"Tes commentaires sont en {prompts.LANG_NAMES.get(subject.language, 'français')}. Réponds par un unique objet JSON valide.",
                messages=[{"role": "user", "content": prompts.mock_exam_grade(ex, answers)}],
                temperature=0.1,
                payload={"questions": questions, "answers": answers},
            )
            result = validate(ExamNotes, get_llm().generate_json(req))
            notes = {n.numero.strip(): (n.note, n.commentaire) for n in result.notes}
        for q in questions:
            given = answers.get(q["numero"], "").strip()
            note, comment = notes.get(q["numero"], (0.0, ""))
            if not given:
                note, comment = 0.0, "Tu n'as pas répondu à cette question."
            note = max(0.0, min(float(q["points"]), round(note * 2) / 2))
            graded.append(
                {
                    "numero": q["numero"],
                    "points": q["points"],
                    "note": note,
                    "commentaire": comment,
                    "correction": q.get("correction", ""),
                    "notion": q.get("notion", ""),
                    "lesson_id": q.get("lesson_id"),
                    "lecon": q.get("lecon", ""),
                }
            )
    total = round(sum(g["note"] for g in graded) * 2) / 2
    return {"note": total, "sur": 20, "questions": graded, "bilan": _bilan(graded)}


def _bilan(graded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Points à retravailler : par leçon, les notions où elle a perdu des points, du plus faible au plus solide."""
    groups: dict[str, dict[str, Any]] = {}
    for g in graded:
        key = g.get("lecon") or "Autres questions"
        entry = groups.setdefault(key, {"lecon": key, "lesson_id": g.get("lesson_id"), "obtenu": 0.0, "total": 0.0, "notions": []})
        entry["obtenu"] += g["note"]
        entry["total"] += g["points"]
        if g["note"] < 0.75 * g["points"] and g.get("notion") and g["notion"] not in entry["notions"]:
            entry["notions"].append(g["notion"])
    out = list(groups.values())
    for entry in out:
        entry["taux"] = round(100 * entry["obtenu"] / entry["total"]) if entry["total"] else 0
    return sorted(out, key=lambda e: e["taux"])


def finish(db: Session, mock: MockExam) -> Optional[dict[str, Any]]:
    result = grade(db, mock)
    mock.result = result
    mock.status = "graded"
    mock.finished_at = utcnow()
    return result
