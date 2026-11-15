"""Correction des réponses : QCM en local, réponses ouvertes par l'IA contre les éléments attendus."""
from __future__ import annotations

from typing import Any

from .generation import prompts
from .generation.content import Evaluation, validate
from .llm import LLMRequest, get_llm


def grade_mcq(data: dict[str, Any], choice_index: int) -> tuple[float, dict[str, Any]]:
    correct = choice_index == data.get("bonne_reponse")
    return (1.0 if correct else 0.0), {"correct": correct}


def grade_open(ctx: prompts.Ctx, data: dict[str, Any], answer: str, spoiler_allowed: bool) -> tuple[float, dict[str, Any]]:
    """Renvoie (score entre 0 et 1, retour détaillé)."""
    expected = [e for e in data.get("elements_attendus", []) if e] or [data.get("reponse_modele", "")]
    model_answer = data.get("reponse_modele") or data.get("reponse_finale") or " ; ".join(expected)

    if len(answer.strip()) < 2:
        return 0.0, {
            "elements": [{"attendu": e, "etat": "absent", "commentaire": ""} for e in expected],
            "points_justes": "",
            "manque": "Tu n'as rien écrit. Essaie même si tu n'es pas sûre : c'est en te trompant que tu apprends.",
            "erreurs": [],
            "conseil": "",
        }

    req = LLMRequest(
        task="evaluate",
        system=prompts.system(ctx),
        messages=[
            {
                "role": "user",
                "content": prompts.evaluate(data.get("enonce", ""), model_answer, expected, answer, spoiler_allowed),
            }
        ],
        temperature=0.1,
        payload={"answer": answer, "expected": expected, "model_answer": model_answer},
    )
    ev: Evaluation = validate(Evaluation, get_llm().generate_json(req))

    # On aligne la réponse de l'IA sur notre liste d'éléments attendus.
    states = [e.etat for e in ev.elements][: len(expected)]
    comments = [e.commentaire for e in ev.elements][: len(expected)]
    while len(states) < len(expected):
        states.append("absent")
        comments.append("")
    weights = {"ok": 1.0, "partiel": 0.5, "absent": 0.0}
    score = sum(weights[s] for s in states) / len(expected)
    feedback = {
        "elements": [
            {"attendu": exp, "etat": state, "commentaire": comment}
            for exp, state, comment in zip(expected, states, comments)
        ],
        "points_justes": ev.points_justes,
        "manque": ev.manque,
        "erreurs": ev.erreurs,
        "conseil": ev.conseil,
    }
    return score, feedback
