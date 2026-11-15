"""IA simulée : sert aux tests automatiques et au mode démonstration (LLM_PROVIDER=mock).

Elle ne comprend rien : elle fabrique un contenu plausible à partir des phrases de la leçon.
Règle de correction simulée : une réponse est juste si elle reprend les mots de l'élément attendu.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .base import LLMError, LLMRequest, Provider

_FILLER = [
    "Cette leçon présente une idée importante du programme.",
    "Chaque définition doit être apprise avec précision.",
    "Un exemple aide à comprendre la règle générale.",
    "La méthode s'applique étape par étape.",
    "Il faut toujours vérifier le résultat obtenu.",
    "Les erreurs de signe sont un piège fréquent.",
]


def sentences(text: str, minimum: int = 6) -> list[str]:
    parts = [p.strip(" \t-•*#") for p in re.split(r"(?<=[.!?؟])\s+|\n+", text or "")]
    found = [p for p in parts if len(p.split()) >= 4][:14]
    for extra in _FILLER:
        if len(found) >= minimum:
            break
        found.append(extra)
    return found


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W\d_]{4,}", text.lower())}


def overlap(expected: str, answer: str) -> float:
    exp = _words(expected)
    if not exp:
        return 1.0 if expected.strip().lower() in answer.lower() else 0.0
    return len(exp & _words(answer)) / len(exp)


class MockProvider(Provider):
    name = "mock"
    supports_vision = True

    def __init__(self) -> None:
        self.failures: list[LLMError] = []  # erreurs à lever aux prochains appels (tests)
        self.calls: list[str] = []

    def generate(self, req: LLMRequest) -> str:
        self.calls.append(req.task)
        if self.failures:
            raise self.failures.pop(0)
        handler = getattr(self, f"_{req.task}", None)
        if handler is None:
            raise LLMError("bad_output", f"tâche inconnue pour l'IA simulée : {req.task}")
        result = handler(req.payload)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    # -- Tâches ---------------------------------------------------------------
    def _ocr(self, p: dict[str, Any]) -> str:
        n = p.get("count", 1)
        return (
            f"Leçon lue sur {n} page(s) (mode démonstration).\n"
            "Une fonction associe à chaque nombre x une image unique notée f(x).\n"
            "L'ensemble de définition regroupe les valeurs de x pour lesquelles f(x) existe.\n"
            "Pour une fraction, le dénominateur doit être différent de zéro.\n"
            "Pour une racine carrée, l'expression sous la racine doit être positive ou nulle.\n"
            "La courbe représentative est l'ensemble des points de coordonnées (x ; f(x)).\n"
            "Une fonction est paire si f(-x) = f(x) pour tout x de son ensemble de définition."
        )

    def _explanation(self, p: dict[str, Any]) -> dict[str, Any]:
        s = sentences(p.get("text", ""))
        chunks = [s[i : i + 2] for i in range(0, min(len(s), 8), 2)]
        sections = []
        for i, chunk in enumerate(chunks, start=1):
            sections.append(
                {
                    "titre": f"Partie {i} : {chunk[0][:50]}",
                    "contenu": " ".join(chunk) + "\n\nEn résumé : $a + b = b + a$.",
                    "exemple": f"Exemple : on applique « {chunk[0][:60]} » à un cas simple, comme $\\frac{{1}}{{2}} + \\frac{{1}}{{3}} = \\frac{{5}}{{6}}$.",
                    "a_retenir": chunk[-1],
                }
            )
        notions = [f"Notion {i + 1} : {x[:40]}" for i, x in enumerate(s[:5])]
        return {
            "titre": p.get("title", "Leçon"),
            "accroche": "Cette leçon te donne les bases pour réussir les exercices du chapitre.",
            "sections": sections,
            "notions": notions,
        }

    def _questions(self, p: dict[str, Any], count: int, n_qcm: int) -> dict[str, Any]:
        s = sentences(p.get("text", ""))
        notions = p.get("notions") or ["Notion générale"]
        shift = (int(p.get("version", 1)) - 1) * 2
        out = []
        for i in range(count):
            sent = s[(i + shift) % len(s)]
            notion = notions[i % len(notions)]
            if i < n_qcm:
                out.append(
                    {
                        "type": "qcm",
                        "enonce": "Laquelle de ces phrases figure dans la leçon ?",
                        "choix": [
                            sent,
                            "Cette phrase n'apparaît pas dans la leçon (A).",
                            "Cette phrase n'apparaît pas dans la leçon (B).",
                            "Cette phrase n'apparaît pas dans la leçon (C).",
                        ],
                        "bonne_reponse": 0,
                        "explication": f"La leçon dit bien : « {sent} »",
                        "notion": notion,
                    }
                )
            else:
                out.append(
                    {
                        "type": "ouverte",
                        "enonce": f"Explique avec tes mots : « {sent} »",
                        "reponse_modele": sent,
                        "elements_attendus": [sent],
                        "explication": f"L'idée à retenir : {sent}",
                        "notion": notion,
                    }
                )
        return {"questions": out}

    def _minitest(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._questions(p, 4, 2)

    def _quiz(self, p: dict[str, Any]) -> dict[str, Any]:
        out = self._questions(p, 6, 2)
        if p.get("code") == "svt":
            s = sentences(p.get("text", ""))
            out["questions"].append(
                {
                    "type": "schema",
                    "enonce": "Complète la légende de ce schéma.",
                    "disposition": "chaine",
                    "elements": [{"nom": f"Étape {i + 1}", "role": s[i % len(s)][:60]} for i in range(4)],
                    "explication": "Les étapes se suivent dans l'ordre de la leçon.",
                    "notion": (p.get("notions") or ["Notion générale"])[0],
                }
            )
        return out

    def _review_questions(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._questions(p, 3, 1)

    def _error_variant(self, p: dict[str, Any]) -> dict[str, Any]:
        expected = (p.get("mistake") or {}).get("expected") or "la règle de la leçon"
        return {
            "type": "ouverte",
            "enonce": f"Autrement dit ({int(p.get('round', 0)) + 1}) : explique avec tes mots « {expected} »",
            "reponse_modele": expected,
            "elements_attendus": [expected],
            "explication": f"L'idée à retenir : {expected}",
            "notion": (p.get("mistake") or {}).get("notion", ""),
        }

    def _methods(self, p: dict[str, Any]) -> dict[str, Any]:
        types = [t for t in p.get("types", []) if t] or ["Application du cours"]
        return {
            "types": [
                {
                    "nom": t,
                    "reconnaitre": "L'énoncé demande d'appliquer directement une règle du cours.",
                    "etapes": ["Repérer la règle.", "L'appliquer aux données.", "Vérifier le résultat."],
                    "erreur_classique": "Oublier une condition de la règle.",
                    "exemple": "Par exemple : $2 + 3 = 5$.",
                }
                for t in types
            ]
        }

    def _video_queries(self, p: dict[str, Any]) -> dict[str, Any]:
        return {"requetes": [f"{p.get('title', 'leçon')} tronc commun", f"{p.get('title', 'leçon')} cours"]}

    def _video_rank(self, p: dict[str, Any]) -> dict[str, Any]:
        ids = list(p.get("candidates", []))[:3]
        return {"selection": [{"id": i, "raison": f"Vidéo n°{n + 1} : elle traite la leçon au bon niveau."} for n, i in enumerate(ids)]}

    def _evaluate_writing(self, p: dict[str, Any]) -> dict[str, Any]:
        """Règle simulée : une copie d'au moins 40 mots est jugée bonne."""
        words = len(str(p.get("answer", "")).split())
        note = 3 if words >= 40 else 1
        criteria = p.get("criteres") or ["Respect de la consigne", "Langue"]
        return {
            "criteres": [{"nom": c, "note": note, "commentaire": "Commentaire simulé."} for c in criteria],
            "fautes": [
                {
                    "extrait": " ".join(str(p.get("answer", "")).split()[:4]),
                    "type": "accord",
                    "explication": "Vérifie l'accord entre le sujet et le verbe.",
                    "piste": "Quel est le sujet de cette phrase ?",
                }
            ],
            "points_forts": "Tes idées se suivent dans un ordre logique." if note == 3 else "",
            "priorite": "Développe davantage tes idées." if note == 1 else "Relis-toi pour les accords.",
        }

    def _summary(self, p: dict[str, Any]) -> dict[str, Any]:
        s = sentences(p.get("text", ""))
        kind = p.get("kind", "sciences")
        extra: dict[str, Any] = {"vocabulaire": [], "auteurs": []}
        if kind == "langue":
            extra["vocabulaire"] = [{"mot": f"mot {i + 1}", "sens": x[:50], "exemple": x} for i, x in enumerate(s[:4])]
        if kind == "philo":
            extra["auteurs"] = [{"nom": "Auteur du cours", "these": s[0], "argument": s[1]}]
        return {
            **extra,
            "titre": p.get("title", "Leçon"),
            "definitions": [{"terme": f"Terme {i + 1}", "definition": x} for i, x in enumerate(s[:3])],
            "formules": [
                {"nom": "Identité remarquable", "formule": "$(a+b)^2 = a^2 + 2ab + b^2$", "quand": "Pour développer un carré."}
            ],
            "methodes": [{"titre": "Résoudre pas à pas", "etapes": ["Lire l'énoncé.", "Repérer la formule.", "Calculer.", "Vérifier."]}],
            "pieges": [{"piege": "Oublier une condition.", "conseil": "Relis la définition avant de conclure."}],
            "a_savoir_par_coeur": s[3:5],
        }

    def _exercise(self, sent: str, level: int, n: int, notion: str, redaction: bool = False, code: str = "") -> dict[str, Any]:
        if redaction:
            return {
                "titre": f"Sujet {n}",
                "enonce": f"(Niveau {level}) Rédige un paragraphe de 8 à 12 lignes à partir de cette idée : « {sent} »",
                "mode": "redaction",
                "criteres": ["Respect de la consigne", "Organisation des idées", "Correction de la langue", "Richesse du contenu"],
                "type_exercice": "Production écrite",
                "elements_attendus": ["Une idée principale", "Des exemples", "Une conclusion"],
                "reponse_finale": "",
                "indices": ["Pars de ton expérience.", "Annonce ton idée, développe, conclus.", "Commence par : « À mon avis… »"],
                "correction_etapes": ["Annoncer l'idée.", "Donner deux arguments.", "Conclure."],
                "notion": notion,
            }
        document = f"| Mesure | Valeur |\n| --- | --- |\n| A | {n} |\n| B | {n + 2} |" if code == "svt" and level >= 2 else ""
        return {
            "titre": f"Exercice {n}",
            "enonce": f"(Niveau {level}) Applique la règle suivante et rédige ta réponse : « {sent} »",
            "document": document,
            "type_exercice": "Analyse de documents" if document else "Application du cours",
            "elements_attendus": [sent],
            "reponse_finale": sent,
            "indices": ["Relis la partie du cours concernée.", "Repère la règle à appliquer.", f"Commence par : {sent[:25]}…"],
            "correction_etapes": ["On repère la règle du cours.", f"On l'applique : {sent}", "On vérifie le résultat."],
            "notion": notion,
        }

    def _exercises(self, p: dict[str, Any]) -> dict[str, Any]:
        s = sentences(p.get("text", ""))
        level = int(p.get("level", 1))
        notions = p.get("notions") or ["Notion générale"]
        redaction = bool(p.get("redaction"))
        return {
            "exercices": [
                self._exercise(s[(i + level) % len(s)], level, i + 1, notions[i % len(notions)], redaction, p.get("code", ""))
                for i in range(2 if redaction else 3)
            ]
        }

    def _exercise_variant(self, p: dict[str, Any]) -> dict[str, Any]:
        s = sentences(p.get("text", ""))
        n = int(p.get("index", 3)) + 1
        return self._exercise(s[(n + 2) % len(s)], int(p.get("level", 1)), n, p.get("notion", "Notion générale"))

    def _evaluate(self, p: dict[str, Any]) -> dict[str, Any]:
        answer = p.get("answer", "")
        elements = []
        for exp in p.get("expected") or [p.get("model_answer", "")]:
            ratio = overlap(exp, answer)
            state = "ok" if ratio >= 0.6 else "partiel" if ratio >= 0.3 else "absent"
            elements.append({"attendu": exp, "etat": state, "commentaire": ""})
        missing = [e["attendu"] for e in elements if e["etat"] != "ok"]
        return {
            "elements": elements,
            "points_justes": "Tu as repris l'idée principale." if len(missing) < len(elements) else "",
            "manque": "Il manque une partie de la réponse attendue." if missing else "",
            "erreurs": [],
            "conseil": "Relis la partie du cours concernée, puis réessaie." if missing else "Continue comme ça.",
        }

    def _reexplain(self, p: dict[str, Any]) -> dict[str, Any]:
        points = []
        for item in p.get("failed") or [{"notion": "Notion générale", "enonce": ""}]:
            points.append(
                {
                    "notion": item.get("notion") or "Point à revoir",
                    "ce_qui_a_coince": "Ta réponse ne reprenait pas l'idée de la leçon.",
                    "explication": "Reprenons autrement : imagine la règle comme une recette à suivre dans l'ordre.",
                    "exemple": "Par exemple : $2 \\times 3 = 6$.",
                    "astuce": "Redis la règle à voix haute avant de répondre.",
                }
            )
        return {"points": points}

    def _chat(self, p: dict[str, Any]) -> str:
        return "Bonne question ! Avant de te répondre : d'après la leçon, qu'est-ce que tu as déjà compris sur ce point ?"
