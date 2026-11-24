"""Le parcours complet, de l'import à la leçon maîtrisée, et le verrouillage des étapes."""
from __future__ import annotations

from .conftest import (
    advance,
    bad_answer,
    do_explique,
    do_feuille,
    good_answer,
    import_text,
    parent_headers,
    pass_exercises,
    run_jobs,
    subject_id,
    take_test,
)


def test_first_launch(client):
    state = client.get("/api/state").json()
    assert state["onboarded"] is False
    assert state["ai"] == {"configured": True, "provider": "mock", "demo": True}
    assert state["settings"]["quiz_threshold"] == 80

    subjects = client.get("/api/subjects").json()
    assert [s["name"] for s in subjects] == ["Maths", "Physique-Chimie", "SVT", "Philosophie", "Arabe", "Français", "Anglais"]
    assert all(s["available"] for s in subjects), "toutes les matières ont leur parcours"

    maths = subject_id(client)
    subjects = client.patch(f"/api/subjects/{maths}", json={"language": "ar"}).json()
    assert next(s for s in subjects if s["id"] == maths)["language"] == "ar"

    assert client.post("/api/exams", json={"subject_id": maths, "date": "2000-01-01"}).status_code == 422
    exams = client.post("/api/exams", json={"subject_id": maths, "date": "2099-01-15", "title": "DS 1"}).json()
    assert exams[0]["subject_name"] == "Maths" and exams[0]["days_left"] > 0

    assert client.post("/api/onboarding/complete").json() == {"ok": True}
    assert client.get("/api/state").json()["onboarded"] is True


def test_import_generates_everything_without_any_action(client):
    assert client.get("/api/next").json() == {"kind": "import"}
    lesson = import_text(client)
    assert lesson["generation"] == {"total": 10, "done": 0, "active": True, "current": "Explication", "problem": None, "claude": None}

    nxt = client.get("/api/next").json()
    assert nxt["kind"] == "step" and nxt["step"]["key"] == "comprendre" and nxt["ready"] is False

    assert run_jobs() == 10  # explication, mini-test, carte mentale, vidéos, résumé, quiz, 3 niveaux d'exercices, méthodes
    detail = client.get(f"/api/lessons/{lesson['id']}").json()
    assert detail["generation"]["done"] == 10 and detail["generation"]["active"] is False
    assert detail["current_ready"] is True
    assert [s["key"] for s in detail["path"]] == ["comprendre", "minitest", "feuille", "resume", "quiz", "explique", "ex1", "ex2", "ex3"]
    assert [s["status"] for s in detail["path"]] == ["current"] + ["locked"] * 8
    content = client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()["content"]
    assert content["sections"] and content["notions"]


def test_locked_steps_are_refused_by_the_server(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    for key in ("minitest", "feuille", "resume", "quiz", "explique", "ex1", "ex2", "ex3"):
        resp = client.get(f"/api/lessons/{lid}/steps/{key}")
        assert resp.status_code == 403, key
        assert "Comprendre" in resp.json()["detail"]
    assert client.post(f"/api/lessons/{lid}/steps/resume/validate").status_code == 403
    assert client.post(f"/api/lessons/{lid}/steps/feuille/submit", json={"text": "x " * 40}).status_code == 403
    assert client.post(f"/api/lessons/{lid}/steps/explique/message", json={"text": "x " * 40}).status_code == 403
    assert client.get(f"/api/lessons/{lid}/steps/inconnue").status_code == 404

    # Impossible de répondre au quiz en passant directement par l'identifiant d'une question.
    from app.db import session_scope
    from app.models import Question, QuestionSet

    with session_scope() as db:
        quiz_question = db.query(Question).join(QuestionSet).filter(QuestionSet.kind == "quiz").first().id
    assert client.post(f"/api/questions/{quiz_question}/answer", json={"answer_text": "x"}).status_code == 403


def test_full_path_to_mastery(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]

    assert client.post(f"/api/lessons/{lid}/steps/comprendre/validate").json() == {"ok": True, "next": "minitest"}

    # Les questions n'exposent pas leur correction avant la réponse.
    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    assert 3 <= len(step["set"]["questions"]) <= 5
    assert all(q["correction"] is None for q in step["set"]["questions"])
    first = step["set"]["questions"][0]
    graded = client.post(f"/api/questions/{first['id']}/answer", json=good_answer(first)).json()
    assert graded["question"]["correction"]["explication"]
    assert client.post(f"/api/questions/{first['id']}/answer", json=good_answer(first)).status_code == 409

    result = take_test_remaining(client, lid, "minitest")
    assert result["set"]["passed"] is True and result["set"]["score"] == 100 and result["step_done"] is True

    assert client.get(f"/api/lessons/{lid}/steps/resume").status_code == 403
    assert do_feuille(client, lid)["passed"] is True
    assert client.get(f"/api/lessons/{lid}/steps/quiz").status_code == 403
    summary = client.get(f"/api/lessons/{lid}/steps/resume").json()
    assert summary["content"]["definitions"]
    assert client.post(f"/api/lessons/{lid}/steps/resume/validate").json()["next"] == "quiz"

    quiz = client.get(f"/api/lessons/{lid}/steps/quiz").json()
    kinds = [q["type"] for q in quiz["set"]["questions"]]
    assert kinds.count("ouverte") > kinds.count("qcm"), "majorité de questions ouvertes"
    assert quiz["threshold"] == 80
    result = take_test(client, lid, "quiz")
    assert result["set"]["passed"] is True
    assert client.get(f"/api/lessons/{lid}/steps/ex1").status_code == 403
    assert do_explique(client, lid)["step_done"] is True

    for level in (1, 2, 3):
        if level < 3:
            assert client.get(f"/api/lessons/{lid}/steps/ex{level + 1}").status_code == 403
        result = pass_exercises(client, lid, level)
        assert result["step_done"] is True
        assert result["mastered"] is (level == 3)

    detail = client.get(f"/api/lessons/{lid}").json()
    assert detail["mastered"] is True and detail["progress"] == 100 and detail["current_step"] is None
    nxt = client.get("/api/next").json()
    assert nxt["kind"] == "done" and nxt["mastered"] == 1 and nxt["next_review"] is not None


def take_test_remaining(client, lid: int, key: str) -> dict:
    step = client.get(f"/api/lessons/{lid}/steps/{key}").json()
    last = {}
    for q in step["set"]["questions"]:
        if q["attempt"] is None:
            last = client.post(f"/api/questions/{q['id']}/answer", json=good_answer(q)).json()
    return last


def test_failed_minitest_reexplains_then_offers_a_new_test(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    client.post(f"/api/lessons/{lid}/steps/comprendre/validate")

    result = take_test(client, lid, "minitest", good=False)
    assert result["set"] == {"state": "failed", "score": 0, "threshold": 70, "passed": False, "mastered": False}
    assert client.get(f"/api/lessons/{lid}/steps/resume").status_code == 403

    # Avant génération : l'ancien test est visible, le nouveau n'est pas prêt.
    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    assert step["ready"] is False and step["set"] is None
    assert step["previous"]["score"] == 0 and step["previous"]["reexplain"] is None
    old_questions = {q["enonce"] for q in step["previous"]["questions"]}

    assert run_jobs() == 6  # ré-explication, nouveau mini-test, et une reprise par erreur (4)
    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    assert step["ready"] is True and step["set"]["version"] == 2
    assert step["previous"]["reexplain"]["points"]
    assert {q["enonce"] for q in step["set"]["questions"]} != old_questions

    result = take_test(client, lid, "minitest")
    assert result["set"]["passed"] is True
    assert client.get(f"/api/lessons/{lid}/steps/feuille").status_code == 200


def test_quiz_threshold_is_configurable(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "quiz")

    # Les seuils ne se règlent que depuis l'espace parent.
    assert client.patch("/api/settings", json={"quiz_threshold": 60}).status_code == 401
    headers = parent_headers(client)
    assert client.patch("/api/settings", json={"quiz_threshold": 30}, headers=headers).status_code == 422
    assert client.patch("/api/settings", json={"quiz_threshold": 60}, headers=headers).json()["quiz_threshold"] == 60

    # 4 bonnes réponses sur 6 = 67 % : raté à 80 %, réussi à 60 %.
    step = client.get(f"/api/lessons/{lid}/steps/quiz").json()
    questions = step["set"]["questions"]
    for i, q in enumerate(questions):
        payload = good_answer(q) if i < 4 else bad_answer(q)
        last = client.post(f"/api/questions/{q['id']}/answer", json=payload).json()
    assert last["set"]["score"] == 67 and last["set"]["passed"] is True


def test_exercise_feedback_reveal_and_variant(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "ex1")

    step = client.get(f"/api/lessons/{lid}/steps/ex1").json()
    assert len(step["exercises"]) == 3 and step["progress"] == {"succeeded": 0, "required": 2}
    ex = step["exercises"][0]
    assert ex["correction"] is None and ex["can_reveal"] is False

    # Elle doit d'abord tenter : pas de correction sans essai, pas de réponse vide.
    assert client.post(f"/api/questions/{ex['id']}/reveal").status_code == 409
    assert client.post(f"/api/questions/{ex['id']}/answer", json={"answer_text": "  "}).status_code == 422

    wrong = client.post(f"/api/questions/{ex['id']}/answer", json={"answer_text": "aucune idée"}).json()
    q = wrong["question"]
    assert q["state"] == "tried" and q["can_reveal"] is True and q["correction"] is None
    assert "attendu" not in q["attempts"][0]["feedback"]["elements"][0], "pas de solution tant qu'elle peut réessayer"

    revealed = client.post(f"/api/questions/{ex['id']}/reveal").json()["question"]
    assert revealed["state"] == "revealed" and revealed["correction"]["etapes"]

    # Après lecture de la correction, recopier la réponse ne valide pas l'exercice.
    after = client.post(f"/api/questions/{ex['id']}/answer", json=good_answer({"type": "ouverte", "enonce": ex["enonce"]})).json()
    assert after["question"]["state"] == "revealed" and after["progress"]["succeeded"] == 0

    step = client.get(f"/api/lessons/{lid}/steps/ex1").json()
    assert step["variant_pending"] is True
    assert run_jobs() == 2  # nouvel exercice + reprise de l'erreur pour le carnet
    step = client.get(f"/api/lessons/{lid}/steps/ex1").json()
    assert step["variant_pending"] is False and len(step["exercises"]) == 4 and step["exercises"][3]["is_variant"] is True

    # Deux exercices réussis parmi les autres valident le niveau.
    for other in step["exercises"][1:3]:
        last = client.post(f"/api/questions/{other['id']}/answer", json=good_answer({"type": "ouverte", "enonce": other["enonce"]})).json()
    assert last["step_done"] is True and last["progress"] == {"succeeded": 2, "required": 2}
    assert client.get(f"/api/lessons/{lid}/steps/ex2").status_code == 200


def test_next_step_prefers_the_nearest_exam(client):
    first = import_text(client, title="Leçon de maths")
    second = import_text(client, code="pc", title="Leçon de physique")
    run_jobs()
    assert client.get("/api/next").json()["lesson"]["id"] == first["id"]
    client.post("/api/exams", json={"subject_id": subject_id(client, "pc"), "date": "2099-03-01"})
    nxt = client.get("/api/next").json()
    assert nxt["lesson"]["id"] == second["id"] and nxt["exam"]["date"] == "2099-03-01"
    client.post("/api/exams", json={"subject_id": subject_id(client, "maths"), "date": "2099-02-01"})
    assert client.get("/api/next").json()["lesson"]["id"] == first["id"]


def test_chat_and_report(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    reply = client.post(f"/api/lessons/{lid}/chat", json={"message": "C'est quoi une fonction paire ?"}).json()["reply"]
    assert reply.rstrip().endswith("?"), "le chat commence par une question"
    messages = client.get(f"/api/lessons/{lid}/chat").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert client.post("/api/reports", json={"lesson_id": lid, "target": "explanation:0", "comment": "Erreur de signe"}).json() == {"ok": True}
