"""Validation du contenu renvoyé par l'IA (tolérante sur la forme, stricte sur le fond)."""
from __future__ import annotations

import random
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ..llm import LLMError


def _as_list(value: Any) -> Any:
    """L'IA renvoie parfois une chaîne là où on attend une liste."""
    if value is None:
        return []
    if isinstance(value, str):
        lines = [re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip() for line in value.splitlines()]
        return [line for line in lines if line]
    return value


class Tolerant(BaseModel):
    model_config = {"extra": "ignore", "str_strip_whitespace": True}

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


# -- Explication ------------------------------------------------------------
class Section(Tolerant):
    titre: str = Field(min_length=1)
    contenu: str = Field(min_length=1)
    exemple: str = ""
    a_retenir: str = ""


class Explanation(Tolerant):
    titre: str = ""
    accroche: str = ""
    sections: list[Section] = Field(min_length=1)
    notions: list[str] = Field(min_length=1)

    _lists = field_validator("notions", mode="before")(_as_list)


# -- Résumé -----------------------------------------------------------------
class Definition(Tolerant):
    terme: str
    definition: str


class Formule(Tolerant):
    nom: str = ""
    formule: str
    quand: str = ""


class Methode(Tolerant):
    titre: str
    etapes: list[str] = []

    _lists = field_validator("etapes", mode="before")(_as_list)


class Piege(Tolerant):
    piege: str
    conseil: str = ""


class Summary(Tolerant):
    titre: str = ""
    definitions: list[Definition] = []
    formules: list[Formule] = []
    methodes: list[Methode] = []
    pieges: list[Piege] = []
    a_savoir_par_coeur: list[str] = []

    _lists = field_validator("a_savoir_par_coeur", mode="before")(_as_list)

    @model_validator(mode="after")
    def _not_empty(self) -> "Summary":
        if not (self.definitions or self.formules or self.methodes):
            raise ValueError("résumé vide")
        return self


# -- Questions --------------------------------------------------------------
class QuestionOut(Tolerant):
    type: Literal["qcm", "ouverte"]
    enonce: str = Field(min_length=3)
    choix: list[str] = []
    bonne_reponse: Optional[int] = None
    reponse_modele: str = ""
    elements_attendus: list[str] = []
    explication: str = ""
    notion: str = ""

    _lists = field_validator("choix", "elements_attendus", mode="before")(_as_list)

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        kind = str(data.get("type", "")).strip().lower()
        data["type"] = "qcm" if kind in ("qcm", "mcq", "choix multiple", "choix_multiple") else "ouverte"
        answer = data.get("bonne_reponse")
        choices = data.get("choix") or []
        if isinstance(answer, str):
            a = answer.strip()
            if a.isdigit():
                data["bonne_reponse"] = int(a)
            elif len(a) == 1 and a.upper() in "ABCDEF":
                data["bonne_reponse"] = "ABCDEF".index(a.upper())
            elif a in choices:
                data["bonne_reponse"] = choices.index(a)
            else:
                data["bonne_reponse"] = None
        return data

    @model_validator(mode="after")
    def _coherent(self) -> "QuestionOut":
        if self.type == "qcm":
            if len(self.choix) < 2 or self.bonne_reponse is None or not 0 <= self.bonne_reponse < len(self.choix):
                raise ValueError("QCM sans bonne réponse valide")
        else:
            if not self.reponse_modele and not self.elements_attendus:
                raise ValueError("question ouverte sans réponse attendue")
            if not self.elements_attendus:
                self.elements_attendus = [self.reponse_modele]
            if not self.reponse_modele:
                self.reponse_modele = " ; ".join(self.elements_attendus)
            self.choix, self.bonne_reponse = [], None
        return self


class ExerciseOut(Tolerant):
    titre: str = ""
    enonce: str = Field(min_length=10)
    type_exercice: str = ""
    elements_attendus: list[str] = Field(min_length=1)
    reponse_finale: str = ""
    indices: list[str] = []
    correction_etapes: list[str] = Field(min_length=1)
    notion: str = ""

    _lists = field_validator("elements_attendus", "indices", "correction_etapes", mode="before")(_as_list)


# -- Correction et ré-explication -------------------------------------------
class EvalElement(Tolerant):
    attendu: str = ""
    etat: Literal["ok", "partiel", "absent"] = "absent"
    commentaire: str = ""

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, value: Any) -> str:
        v = str(value).strip().lower()
        if v in ("ok", "oui", "present", "présent", "correct", "true"):
            return "ok"
        if v.startswith("part"):
            return "partiel"
        return "absent"


class Evaluation(Tolerant):
    elements: list[EvalElement] = Field(min_length=1)
    points_justes: str = ""
    manque: str = ""
    erreurs: list[str] = []
    conseil: str = ""

    _lists = field_validator("erreurs", mode="before")(_as_list)

    @property
    def score(self) -> float:
        weights = {"ok": 1.0, "partiel": 0.5, "absent": 0.0}
        return sum(weights[e.etat] for e in self.elements) / len(self.elements)


class ReexplainPoint(Tolerant):
    notion: str = ""
    ce_qui_a_coince: str = ""
    explication: str = Field(min_length=1)
    exemple: str = ""
    astuce: str = ""


class Reexplain(Tolerant):
    points: list[ReexplainPoint] = Field(min_length=1)


# -- Outils -----------------------------------------------------------------
def validate(model: type[BaseModel], data: Any) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise LLMError("bad_output", f"{model.__name__} invalide : {exc.errors()[:3]}") from exc


def validate_items(model: type[BaseModel], items: Any, minimum: int) -> list[Any]:
    """Garde les éléments valides ; échoue s'il en reste trop peu."""
    if not isinstance(items, list):
        raise LLMError("bad_output", "liste attendue")
    valid = []
    for item in items:
        try:
            valid.append(model.model_validate(item))
        except ValidationError:
            continue
    if len(valid) < minimum:
        raise LLMError("bad_output", f"seulement {len(valid)} élément(s) valide(s) sur {len(items)}")
    return valid


def shuffle_choices(question: QuestionOut, seed: int) -> None:
    """Mélange les choix d'un QCM pour que la bonne réponse ne soit pas toujours la première."""
    if question.type != "qcm" or question.bonne_reponse is None:
        return
    order = list(range(len(question.choix)))
    random.Random(seed).shuffle(order)
    question.choix = [question.choix[i] for i in order]
    question.bonne_reponse = order.index(question.bonne_reponse)
