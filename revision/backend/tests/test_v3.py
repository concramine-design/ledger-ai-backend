"""Version 3 : feuille blanche, explique-moi, contrôle blanc, carte mentale, série, maîtrise, mode parent."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.llm import LLMError

from .conftest import (
    LESSON_TEXT,
    LONG_TEXT,
    advance,
    do_explique,
    do_feuille,
    good_answer,
    import_text,
    parent_headers,
    run_jobs,
    subject_id,
    take_test,
)


def _run_background() -> None:
    """Les tâches de fond (contrôle blanc, ancien devoir) s'exécutent tout de suite quand le worker est coupé."""


# -- Feuille blanche -----------------------------------------------------------
def test_feuille_blanche_compares_with_the_lesson(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "feuille")

    # Verrouillée tant que le mini-test n'est pas validé : déjà couvert ; ici on teste le contenu.
    step = client.get(f"/api/lessons/{lid}/steps/feuille").json()
    assert step["status"] == "current" and step["threshold"] == 50 and step["feuille"]["submissions"] == []

    # Trop court : refusé.
    assert client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": "les fonctions"}).status_code == 422

    # Quelques souvenirs seulement : signale les oublis, ne valide pas.
    partial = client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": LESSON_TEXT.split("\n")[0] + " " + LESSON_TEXT.split("\n")[1]}).json()
    assert partial["passed"] is False and partial["coverage"] < 50
    assert any(p["etat"] == "absent" for p in partial["result"]["points"])
    assert any(p["rappel"] for p in partial["result"]["points"] if p["etat"] != "ok")
    assert client.get(f"/api/lessons/{lid}/steps/resume").status_code == 403

    # Tout restitué : validé, l'étape suivante se débloque.
    full = client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": LESSON_TEXT}).json()
    assert full["passed"] is True and full["coverage"] == 100 and full["step_done"] is True
    assert all(p["etat"] == "ok" for p in full["result"]["points"])
    assert client.get(f"/api/lessons/{lid}/steps/resume").status_code == 200

    step = client.get(f"/api/lessons/{lid}/steps/feuille").json()
    assert len(step["feuille"]["submissions"]) == 2 and step["status"] == "done"


def test_feuille_detects_errors(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "feuille")
    result = client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": LESSON_TEXT + " Mais tout cela est faux."}).json()
    assert result["result"]["erreurs"], "les erreurs de la feuille sont signalées"


def test_feuille_keeps_text_on_ai_failure(client, mock_llm):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "feuille")
    mock_llm.failures = [LLMError("rate_limit", "quota")]
    resp = client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": LESSON_TEXT})
    assert resp.status_code == 503 and resp.json()["detail"]["kind"] == "rate_limit"
    # Rien n'est enregistré, l'étape reste à faire : elle garde son texte côté navigateur.
    assert client.get(f"/api/lessons/{lid}/steps/feuille").json()["feuille"]["submissions"] == []


# -- Explique-moi --------------------------------------------------------------
def test_explique_moi_roleplay_then_evaluation(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "explique")

    assert client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": "trop court"}).status_code == 422

    # Première explication : le camarade pose une question.
    first = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": LONG_TEXT}).json()
    assert first["explique"]["messages"][-1]["role"] == "camarade"
    assert first["explique"]["messages"][-1]["content"].endswith("?")
    assert first["explique"]["evaluation"] is None and first["step_done"] is False

    # Deuxième réponse : nouvelle question.
    second = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": LONG_TEXT}).json()
    assert sum(m["role"] == "camarade" for m in second["explique"]["messages"]) == 2

    # Troisième : évaluation de la clarté.
    third = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": LONG_TEXT}).json()
    assert third["explique"]["evaluation"] is not None and third["explique"]["score"] >= 60
    assert third["step_done"] is True
    assert client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": LONG_TEXT}).status_code == 409
    assert client.get(f"/api/lessons/{lid}/steps/ex1").status_code == 200


def test_explique_unclear_can_be_restarted(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "explique")
    # Première explication assez longue pour être acceptée, mais le total reste trop pauvre pour être jugé clair.
    last = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": "C'est une fonction et elle fait des choses avec les nombres je crois bien oui."}).json()
    last = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": "Oui."}).json()
    last = client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": "Non."}).json()
    assert last["explique"]["passed"] is False and last["step_done"] is False
    assert client.get(f"/api/lessons/{lid}/steps/ex1").status_code == 403

    restarted = client.post(f"/api/lessons/{lid}/steps/explique/restart").json()
    assert restarted["explique"]["messages"] == [] and restarted["explique"]["evaluation"] is None
    assert do_explique(client, lid)["step_done"] is True


# -- Carte mentale -------------------------------------------------------------
def test_mindmap_generated_for_each_lesson(client):
    lesson = import_text(client)
    run_jobs()
    step = client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()
    mind = step["mindmap"]
    assert mind["centre"] and 2 <= len(mind["branches"]) <= 7
    assert all(b["titre"] and b["feuilles"] for b in mind["branches"])
    assert client.get(f"/api/lessons/{lesson['id']}").json()["mindmap"]["centre"]


# -- Série de jours, maîtrise, récompenses ------------------------------------
def test_streak_counts_consecutive_days(client):
    from app.db import session_scope
    from app.models import ActivityDay

    lesson = import_text(client)
    run_jobs()
    advance(client, lesson["id"], "resume")  # du travail aujourd'hui
    with session_scope() as db:
        today = date.today()
        for delta in (1, 2, 4):  # hier, avant-hier (série), et un trou
            db.add(ActivityDay(day=today - timedelta(days=delta), actions=3))
    activity = client.get("/api/activity").json()
    assert activity["streak"] == 3  # aujourd'hui + 2 jours, le trou à J-3 casse la suite
    assert len(activity["history"]) == 14
    earned = {r["key"] for r in activity["rewards"] if r["earned"]}
    assert "premiere_lecon" in earned and "serie_3" in earned


def test_mastery_score_grows_along_the_path(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    start = client.get(f"/api/lessons/{lid}").json()
    assert start["mastery"] == 0 and start["color"] == "rouge"
    advance(client, lid, "quiz")
    mid = client.get(f"/api/lessons/{lid}").json()
    assert 0 < mid["mastery"] < 100 and mid["color"] in ("rouge", "orange")
    advance(client, lid)
    full = client.get(f"/api/lessons/{lid}").json()
    assert full["mastered"] is True and full["mastery"] >= 75 and full["color"] == "vert"


def test_pomodoro_counts_sessions(client):
    client.post("/api/activity/pomodoro", json={"minutes": 25})
    result = client.post("/api/activity/pomodoro", json={"minutes": 25}).json()
    assert result["streak"] == 1
    from app.db import session_scope
    from app.models import ActivityDay

    with session_scope() as db:
        row = db.get(ActivityDay, date.today())
        assert row.pomodoros == 2 and row.minutes == 50


# -- Mode parent ---------------------------------------------------------------
def test_parent_area_is_code_protected(client):
    assert client.get("/api/parent/status").json() == {"code_set": False}
    assert client.get("/api/parent/overview").status_code == 401
    assert client.post("/api/parent/login", json={"code": "1234"}).status_code == 409  # pas encore de code

    token = client.post("/api/parent/setup", json={"code": "1234"}).json()["token"]
    assert client.get("/api/parent/status").json() == {"code_set": True}
    assert client.post("/api/parent/setup", json={"code": "9999"}).status_code == 409  # déjà défini

    headers = {"X-Parent-Token": token}
    assert client.get("/api/parent/overview", headers=headers).status_code == 200
    assert client.get("/api/parent/overview", headers={"X-Parent-Token": "faux"}).status_code == 401

    # Mauvais code refusé, bon code accepté.
    assert client.post("/api/parent/login", json={"code": "0000"}).status_code == 401
    assert client.post("/api/parent/login", json={"code": "1234"}).status_code == 200

    # Changement de code depuis l'espace.
    assert client.post("/api/parent/code", json={"new_code": "5678"}).status_code == 401
    assert client.post("/api/parent/code", json={"new_code": "5678"}, headers=headers).json() == {"ok": True}
    assert client.post("/api/parent/login", json={"code": "5678"}).status_code == 200


def test_parent_login_rate_limited(client):
    client.post("/api/parent/setup", json={"code": "1234"})
    for _ in range(5):
        assert client.post("/api/parent/login", json={"code": "0000"}).status_code == 401
    assert client.post("/api/parent/login", json={"code": "0000"}).status_code == 429


def test_parent_overview_shows_progress(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "quiz")

    headers = parent_headers(client)
    data = client.get("/api/parent/overview", headers=headers).json()
    assert data["streak"] >= 1 and len(data["history"]) == 14
    maths = next(s for s in data["subjects"] if s["subject"]["code"] == "maths")
    assert maths["mastery"] > 0
    row = maths["lessons"][0]
    assert row["title"] == lesson["title"] and 0 < row["mastery"] < 100 and row["step"] in ("Quiz complet", "Explique-moi")
    assert "minitest" in row["scores"]


def test_parent_sees_reports(client):
    lesson = import_text(client)
    run_jobs()
    client.post("/api/reports", json={"lesson_id": lesson["id"], "target": "explication:partie-1", "comment": "Erreur de signe"})
    data = client.get("/api/parent/overview", headers=parent_headers(client)).json()
    assert data["reports"][0]["comment"] == "Erreur de signe" and data["reports"][0]["lesson"] == lesson["title"]


# -- Contrôle blanc ------------------------------------------------------------
def _ready_lesson(client, **kw) -> int:
    lesson = import_text(client, **kw)
    run_jobs()
    return lesson["id"]


def test_mock_exam_timed_graded_on_20(client):
    sid = subject_id(client)
    lid = _ready_lesson(client)
    assert client.post("/api/mock-exams", json={"subject_id": sid, "duration_min": 45}).status_code == 200
    mock = client.get("/api/mock-exams").json()[0]
    assert mock["status"] == "ready" and mock["duration_min"] == 45
    assert mock["summary"]["questions"] >= 2 and mock["paper"] is None  # sujet caché avant le départ

    started = client.post(f"/api/mock-exams/{mock['id']}/start").json()
    assert started["status"] == "started" and started["remaining_seconds"] <= 45 * 60
    paper = started["paper"]
    total = sum(q["points"] for ex in paper["exercices"] for q in ex["questions"])
    assert total == 20 and all("correction" not in q for ex in paper["exercices"] for q in ex["questions"])

    # Sauvegarde en cours d'épreuve, puis copie rendue.
    numeros = [q["numero"] for ex in paper["exercices"] for q in ex["questions"]]
    client.put(f"/api/mock-exams/{mock['id']}/answers", json={"answers": {numeros[0]: "une réponse en cours"}})
    quoted = {}
    for ex in paper["exercices"]:
        for q in ex["questions"]:
            quoted[q["numero"]] = q["enonce"].split("«")[1].split("»")[0].strip() if "«" in q["enonce"] else "réponse"
    result = client.post(f"/api/mock-exams/{mock['id']}/submit", json={"answers": quoted}).json()
    assert result["status"] == "graded"
    assert 0 <= result["result"]["note"] <= 20 and result["result"]["sur"] == 20
    assert result["result"]["note"] > 15  # bonnes réponses recopiées depuis les énoncés
    assert all("correction" in q for ex in result["paper"]["exercices"] for q in ex["questions"])  # corrigé visible après
    assert result["result"]["bilan"], "bilan des points à retravailler"


def test_mock_exam_empty_copy_scores_zero(client):
    sid = subject_id(client)
    _ready_lesson(client)
    mock = client.post("/api/mock-exams", json={"subject_id": sid}).json()
    client.post(f"/api/mock-exams/{mock['id']}/start")
    result = client.post(f"/api/mock-exams/{mock['id']}/submit", json={"answers": {}}).json()
    assert result["result"]["note"] == 0
    assert client.post(f"/api/mock-exams/{mock['id']}/start").json()["status"] == "graded"  # déjà corrigé


def test_mock_exam_needs_a_lesson(client):
    assert client.post("/api/mock-exams", json={"subject_id": subject_id(client)}).status_code == 422


def test_mock_exam_generation_failure_can_be_retried(client, mock_llm):
    sid = subject_id(client)
    _ready_lesson(client)
    mock_llm.failures = [LLMError("server", "panne")]
    mock = client.post("/api/mock-exams", json={"subject_id": sid}).json()
    assert mock["status"] == "error" and "souci" in mock["error"]
    retried = client.post(f"/api/mock-exams/{mock['id']}/retry").json()
    assert retried["status"] == "ready"


# -- Anciens devoirs -----------------------------------------------------------
def test_import_past_exam_and_detect_recurring_types(client):
    sid = subject_id(client)
    first = client.post(
        "/api/past-exams",
        data={"subject_id": sid, "title": "DS 1", "text": "Exercice 1 : appliquer le cours. Exercice 2 : justifier la réponse. " * 3},
    ).json()
    assert first["status"] == "ready" and first["analysis"]["types"]

    client.post(
        "/api/past-exams",
        data={"subject_id": sid, "title": "DS 2", "text": "Un problème de synthèse en plusieurs étapes. Appliquer le cours. " * 3},
    )
    groups = client.get("/api/past-exams").json()
    maths = next(g for g in groups if g["subject"]["code"] == "maths")
    assert len(maths["exams"]) == 2
    recurring = {t["type"]: t["count"] for t in maths["recurring"]}
    assert recurring.get("Application du cours") == 2, "un type vu dans deux devoirs est compté deux fois"

    assert client.delete(f"/api/past-exams/{first['id']}").json() == {"ok": True}
    assert len(client.get("/api/past-exams").json()[0]["exams"]) == 1


def test_past_exam_style_feeds_control_level_exercises(client):
    sid = subject_id(client)
    client.post("/api/past-exams", data={"subject_id": sid, "title": "DS", "text": "Exercice de synthèse. Justifier. " * 5})
    lesson = import_text(client)
    run_jobs()
    # Les exercices de niveau 2 sont générés en tenant compte du style : ils sont bien là.
    advance(client, lesson["id"], "ex2")
    step = client.get(f"/api/lessons/{lesson['id']}/steps/ex2").json()
    assert len(step["exercises"]) >= 2


def test_past_exam_failure_can_be_retried(client, mock_llm):
    sid = subject_id(client)
    mock_llm.failures = [LLMError("server", "panne")]
    exam = client.post("/api/past-exams", data={"subject_id": sid, "title": "DS", "text": "Un devoir. " * 20}).json()
    assert exam["status"] == "error"
    assert client.post(f"/api/past-exams/{exam['id']}/retry").json()["status"] == "ready"
