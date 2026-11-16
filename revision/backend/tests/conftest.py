"""Chaque test tourne sur une base vide, avec l'IA simulée et sans fil d'arrière-plan."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

LESSON_TEXT = """Une fonction numérique associe à chaque nombre réel x au plus une image notée f(x).
L'ensemble de définition regroupe tous les réels x pour lesquels f(x) existe.
Pour une fonction rationnelle, le dénominateur doit être différent de zéro.
Pour une racine carrée, l'expression sous la racine doit être positive ou nulle.
La courbe représentative est l'ensemble des points de coordonnées (x ; f(x)).
Une fonction est paire lorsque f(-x) = f(x) pour tout x de son ensemble de définition.
Une fonction est impaire lorsque f(-x) = -f(x) pour tout x de son ensemble de définition.
Une fonction est croissante sur un intervalle lorsque les images sont rangées dans le même ordre que les antécédents.
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REVISION_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("REVISION_WORKER", "0")
    from app import config
    from app.services import llm

    config.get_config.cache_clear()
    llm.reset_llm()
    from app.routers import parent

    parent._sessions.clear()
    parent._failures.clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    config.get_config.cache_clear()
    llm.reset_llm()


@pytest.fixture()
def mock_llm(client):
    from app.services.llm import get_llm

    return get_llm().providers[0]


def run_jobs() -> int:
    from app.services.generation.worker import run_pending

    return run_pending()


def subject_id(client, code: str = "maths") -> int:
    return next(s["id"] for s in client.get("/api/subjects").json() if s["code"] == code)


def import_text(client, text: str = LESSON_TEXT, code: str = "maths", title: str = "Généralités sur les fonctions") -> dict:
    resp = client.post(
        "/api/lessons",
        data={"subject_id": subject_id(client, code), "chapter_title": "Fonctions", "title": title, "text": text},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def good_answer(question: dict) -> dict:
    """La bonne réponse selon les règles de l'IA simulée."""
    if question["type"] == "qcm":
        index = next(i for i, c in enumerate(question["choix"]) if "n'apparaît pas" not in c)
        return {"choice_index": index}
    quoted = re.search(r"«\s*(.+?)\s*»", question["enonce"], re.S)
    return {"answer_text": quoted.group(1) if quoted else question["enonce"]}


def bad_answer(question: dict) -> dict:
    if question["type"] == "qcm":
        index = next(i for i, c in enumerate(question["choix"]) if "n'apparaît pas" in c)
        return {"choice_index": index}
    return {"answer_text": "aucune idée"}


def take_test(client, lesson_id: int, key: str, good: bool = True) -> dict:
    """Répond à toutes les questions du test courant. Renvoie la dernière réponse du serveur."""
    step = client.get(f"/api/lessons/{lesson_id}/steps/{key}").json()
    assert step["ready"], step
    last = {}
    for q in step["set"]["questions"]:
        resp = client.post(f"/api/questions/{q['id']}/answer", json=good_answer(q) if good else bad_answer(q))
        assert resp.status_code == 200, resp.text
        last = resp.json()
    return last


def pass_exercises(client, lesson_id: int, level: int) -> dict:
    step = client.get(f"/api/lessons/{lesson_id}/steps/ex{level}").json()
    last = {}
    for ex in step["exercises"][: step["progress"]["required"]]:
        resp = client.post(f"/api/questions/{ex['id']}/answer", json=good_answer({"type": "ouverte", "enonce": ex["enonce"]}))
        assert resp.status_code == 200, resp.text
        last = resp.json()
    return last


LONG_TEXT = " ".join(["Je pense que cette idée est importante parce qu'elle explique le monde."] * 6)
STEP_ORDER = ["comprendre", "minitest", "feuille", "resume", "quiz", "explique", "ex1", "ex2", "ex3"]


def do_feuille(client, lesson_id: int, text: str = LESSON_TEXT) -> dict:
    """Feuille blanche : recopier la leçon donne 100 % avec l'IA simulée."""
    resp = client.post(f"/api/lessons/{lesson_id}/steps/feuille/submit", json={"text": text})
    assert resp.status_code == 200, resp.text
    return resp.json()


def do_explique(client, lesson_id: int, text: str = LONG_TEXT) -> dict:
    """Explique-moi : une explication, puis deux réponses aux questions du camarade."""
    last = {}
    for _ in range(3):
        resp = client.post(f"/api/lessons/{lesson_id}/steps/explique/message", json={"text": text})
        assert resp.status_code == 200, resp.text
        last = resp.json()
    return last


def advance(client, lesson_id: int, until: str | None = None) -> None:
    """Valide les étapes dans l'ordre jusqu'à `until` (non comprise) ; sans `until`, jusqu'à la maîtrise."""
    for key in STEP_ORDER:
        if key == until:
            return
        status = next(s["status"] for s in client.get(f"/api/lessons/{lesson_id}").json()["path"] if s["key"] == key)
        if status == "done":
            continue
        if key in ("comprendre", "resume"):
            assert client.post(f"/api/lessons/{lesson_id}/steps/{key}/validate").status_code == 200
        elif key in ("minitest", "quiz"):
            take_test(client, lesson_id, key)
        elif key == "feuille":
            assert do_feuille(client, lesson_id)["passed"]
        elif key == "explique":
            assert do_explique(client, lesson_id)["step_done"]
        else:
            step = client.get(f"/api/lessons/{lesson_id}/steps/{key}").json()
            for ex in step["exercises"][: step["progress"]["required"]]:
                answer = LONG_TEXT if ex["mode"] == "redaction" else good_answer({"type": "ouverte", "enonce": ex["enonce"]})["answer_text"]
                assert client.post(f"/api/questions/{ex['id']}/answer", json={"answer_text": answer}).status_code == 200


def parent_headers(client, code: str = "1234") -> dict:
    """Ouvre l'espace parent (crée le code au premier appel)."""
    if client.get("/api/parent/status").json()["code_set"]:
        token = client.post("/api/parent/login", json={"code": code}).json()["token"]
    else:
        token = client.post("/api/parent/setup", json={"code": code}).json()["token"]
    return {"X-Parent-Token": token}
