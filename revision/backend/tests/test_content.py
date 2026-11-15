import pytest

from app.services.generation.content import (
    Evaluation,
    ExerciseOut,
    QuestionOut,
    shuffle_choices,
    validate,
    validate_items,
)
from app.services.llm import LLMError


def test_question_normalisation():
    q = validate(QuestionOut, {"type": "QCM", "enonce": "Combien ?", "choix": ["1", "2", "3"], "bonne_reponse": "B"})
    assert q.type == "qcm" and q.bonne_reponse == 1
    q = validate(QuestionOut, {"type": "open", "enonce": "Définis f.", "reponse_modele": "Une fonction.", "explication": None})
    assert q.type == "ouverte" and q.elements_attendus == ["Une fonction."] and q.explication == ""


def test_invalid_mcq_rejected_and_minimum_enforced():
    bad = {"type": "qcm", "enonce": "Combien ?", "choix": ["1", "2"], "bonne_reponse": 7}
    good = {"type": "ouverte", "enonce": "Définis f.", "reponse_modele": "Une fonction."}
    assert len(validate_items(QuestionOut, [bad, good], minimum=1)) == 1
    with pytest.raises(LLMError) as err:
        validate_items(QuestionOut, [bad, good], minimum=2)
    assert err.value.kind == "bad_output"


def test_shuffle_keeps_the_right_answer():
    for seed in range(20):
        q = validate(QuestionOut, {"type": "qcm", "enonce": "Vrai ?", "choix": ["bon", "a", "b", "c"], "bonne_reponse": 0})
        shuffle_choices(q, seed)
        assert q.choix[q.bonne_reponse] == "bon"


def test_exercise_accepts_string_lists():
    ex = validate(
        ExerciseOut,
        {"enonce": "Calcule 2 + 2 puis justifie.", "elements_attendus": "- 4\n- addition", "correction_etapes": "1. On additionne.\n2. On trouve 4."},
    )
    assert ex.elements_attendus == ["4", "addition"]
    assert ex.correction_etapes == ["On additionne.", "On trouve 4."]


def test_evaluation_score():
    ev = validate(Evaluation, {"elements": [{"etat": "OK"}, {"etat": "partiellement"}, {"etat": "non"}]})
    assert ev.score == pytest.approx(0.5)
