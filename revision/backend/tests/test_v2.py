"""Version 2 : SVT, langues, philosophie, indices, vidéos, carnet d'erreurs, répétition espacée."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.llm import LLMError

from .conftest import advance, bad_answer, good_answer, import_text, pass_exercises, run_jobs, subject_id, take_test

LONG_COPY = " ".join(["Je pense que cette idée est importante parce qu'elle explique le monde."] * 6)


def _to_exercises(client, lid: int) -> None:
    advance(client, lid, "ex1")


def _master(client, lid: int) -> None:
    advance(client, lid)


def _make_due(lesson_id: int, kind: str | None = None) -> None:
    """Fait comme si le temps avait passé : les rappels de la leçon sont dus aujourd'hui."""
    from app.db import session_scope
    from app.models import ReviewItem

    with session_scope() as db:
        query = db.query(ReviewItem).filter(ReviewItem.lesson_id == lesson_id, ReviewItem.state == "active")
        for item in query:
            if kind is None or item.kind == kind:
                item.due = date.today()


def _items(lesson_id: int) -> list[dict]:
    from app.db import session_scope
    from app.models import ReviewItem

    with session_scope() as db:
        return [
            {"kind": i.kind, "stage": i.stage, "due": i.due, "state": i.state, "ready": i.set_id is not None or i.kind == "card"}
            for i in db.query(ReviewItem).filter(ReviewItem.lesson_id == lesson_id).order_by(ReviewItem.id)
        ]


# -- Matières ------------------------------------------------------------------
def test_language_lesson_has_vocabulary_cards_and_writing(client):
    lesson = import_text(client, code="francais", title="L'accord du participe passé")
    assert lesson["generation"]["total"] == 9, "pas de fiche « méthodes types » pour une langue"
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "resume")

    fiche = client.get(f"/api/lessons/{lid}/steps/resume").json()
    assert fiche["kind"] == "langue" and len(fiche["content"]["vocabulaire"]) == 4
    client.post(f"/api/lessons/{lid}/steps/resume/validate")
    cards = [i for i in _items(lid) if i["kind"] == "card"]
    assert len(cards) == 3 + 4, "définitions et vocabulaire deviennent des cartes mémoire"
    assert all(c["due"] == date.today() + timedelta(days=1) for c in cards)

    advance(client, lid, "ex3")

    # Niveau 3 : production écrite, corrigée par critères, sans réécriture.
    step = client.get(f"/api/lessons/{lid}/steps/ex3").json()
    assert step["progress"] == {"succeeded": 0, "required": 1}
    sujet = step["exercises"][0]
    assert sujet["mode"] == "redaction"
    short = client.post(f"/api/questions/{sujet['id']}/answer", json={"answer_text": "Trop court."}).json()
    assert short["question"]["attempts"][0]["score"] == 0 and short["step_done"] is False
    weak = client.post(f"/api/questions/{sujet['id']}/answer", json={"answer_text": "Je pense que cette idée est bonne pour nous."}).json()
    feedback = weak["question"]["attempts"][1]["feedback"]
    assert feedback["mode"] == "redaction" and len(feedback["criteres"]) == 4
    assert feedback["fautes"][0]["piste"].endswith("?") and feedback["fautes"][0]["extrait"]
    good = client.post(f"/api/questions/{sujet['id']}/answer", json={"answer_text": LONG_COPY}).json()
    assert good["step_done"] is True and good["mastered"] is True


def test_philosophy_plan_and_argumentation_levels(client):
    lesson = import_text(client, code="philo", title="La conscience")
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "resume")
    fiche = client.get(f"/api/lessons/{lid}/steps/resume").json()["content"]
    assert fiche["auteurs"][0]["these"]
    client.post(f"/api/lessons/{lid}/steps/resume/validate")
    assert sum(i["kind"] == "card" for i in _items(lid)) == 3 + 1  # notions + auteur
    advance(client, lid, "ex2")
    for level in (2, 3):
        step = client.get(f"/api/lessons/{lid}/steps/ex{level}").json()
        assert all(ex["mode"] == "redaction" for ex in step["exercises"]) and step["progress"]["required"] == 1
        done = client.post(f"/api/questions/{step['exercises'][0]['id']}/answer", json={"answer_text": LONG_COPY}).json()
        assert done["step_done"] is True


def test_svt_schema_question_and_documents(client):
    lesson = import_text(client, code="svt", title="Les échanges gazeux")
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "quiz")

    quiz = client.get(f"/api/lessons/{lid}/steps/quiz").json()
    schema = next(q for q in quiz["set"]["questions"] if q["type"] == "schema")
    assert sorted(schema["schema"]["banque"]) == ["Étape 1", "Étape 2", "Étape 3", "Étape 4"]
    assert all("nom" not in case for case in schema["schema"]["cases"]), "les noms ne sont pas envoyés avant la réponse"
    assert client.post(f"/api/questions/{schema['id']}/answer", json={"labels": ["Étape 1"]}).status_code == 422

    half = ["Étape 1", "Étape 2", "Étape 4", "Étape 3"]
    graded = client.post(f"/api/questions/{schema['id']}/answer", json={"labels": half}).json()["question"]
    assert graded["attempt"]["score"] == 0.5 and graded["attempt"]["feedback"]["cases"] == [True, True, False, False]
    assert graded["correction"]["noms"] == ["Étape 1", "Étape 2", "Étape 3", "Étape 4"]

    for q in quiz["set"]["questions"]:
        if q["type"] != "schema":
            last = client.post(f"/api/questions/{q['id']}/answer", json=good_answer(q)).json()
    assert last["set"]["passed"] is True  # 6,5 / 7 = 93 %

    advance(client, lid, "ex2")
    level2 = client.get(f"/api/lessons/{lid}/steps/ex2").json()
    assert all("| Mesure | Valeur |" in ex["document"] for ex in level2["exercises"])


# -- Indices -------------------------------------------------------------------
def test_three_progressive_hints(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    _to_exercises(client, lid)
    ex = client.get(f"/api/lessons/{lid}/steps/ex1").json()["exercises"][0]
    assert ex["hints"] == [] and ex["hints_total"] == 3

    seen = []
    for expected in (1, 2, 3, 3):
        ex = client.post(f"/api/questions/{ex['id']}/hint").json()["question"]
        assert len(ex["hints"]) == expected
        seen = ex["hints"]
    assert seen[0].startswith("Relis") and seen[2].startswith("Commence par")
    assert ex["correction"] is None and ex["can_reveal"] is False, "un indice ne donne pas la correction"

    # Un exercice réussi avec indices compte quand même.
    done = client.post(f"/api/questions/{ex['id']}/answer", json=good_answer({"type": "ouverte", "enonce": ex["enonce"]})).json()
    assert done["question"]["state"] == "succeeded" and done["progress"]["succeeded"] == 1

    quiz_question = client.get(f"/api/lessons/{lid}/steps/quiz").json()["set"]["questions"][0]
    assert client.post(f"/api/questions/{quiz_question['id']}/hint").status_code == 404, "pas d'indice dans un quiz"


# -- Carnet d'erreurs ----------------------------------------------------------
def test_mistakes_are_recorded_and_asked_again_in_another_form(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    client.post(f"/api/lessons/{lid}/steps/comprendre/validate")

    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    questions = step["set"]["questions"]
    wrong = next(q for q in questions if q["type"] == "ouverte")
    for q in questions:
        client.post(f"/api/questions/{q['id']}/answer", json=bad_answer(q) if q["id"] == wrong["id"] else good_answer(q))

    book = client.get("/api/mistakes").json()
    assert len(book) == 1
    entry = book[0]
    assert entry["source"] == "minitest" and entry["given"] == "aucune idée" and entry["resolved"] is False
    assert entry["enonce"] == wrong["enonce"] and entry["expected"]
    assert entry["next_due"] == (date.today() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/lessons/{lid}").json()["open_mistakes"] == 1

    # Pas encore due : rien à revoir aujourd'hui.
    run_jobs()
    assert client.get("/api/reviews/today").json()["items"] == []

    _make_due(lid, "error")
    session = client.get("/api/reviews/today").json()
    assert len(session["items"]) == 1 and session["items"][0]["kind"] == "error"
    variant = session["items"][0]["questions"][0]
    assert variant["enonce"] != wrong["enonce"], "l'erreur est reposée sous une autre forme"

    first = client.post(f"/api/questions/{variant['id']}/answer", json=good_answer(variant)).json()
    assert first["review"]["passed"] is True and first["review"]["done"] is False
    assert first["review"]["next_due"] == (date.today() + timedelta(days=3)).isoformat()
    assert client.post(f"/api/questions/{variant['id']}/answer", json=good_answer(variant)).status_code == 409

    # Deuxième reprise réussie : l'erreur sort du carnet.
    run_jobs()
    _make_due(lid, "error")
    second = client.get("/api/reviews/today").json()["items"][0]["questions"][0]
    assert second["enonce"] != variant["enonce"]
    done = client.post(f"/api/questions/{second['id']}/answer", json=good_answer(second)).json()
    assert done["review"] == {"passed": True, "done": True, "next_due": None}
    book = client.get("/api/mistakes").json()
    assert book[0]["resolved"] is True and book[0]["successes"] == 2 and book[0]["next_due"] is None


def test_failed_error_review_comes_back_tomorrow(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    client.post(f"/api/lessons/{lid}/steps/comprendre/validate")
    take_test(client, lid, "minitest", good=False)
    run_jobs()
    assert len(client.get("/api/mistakes").json()) == 4
    _make_due(lid, "error")
    variant = client.get("/api/reviews/today").json()["items"][0]["questions"][0]
    result = client.post(f"/api/questions/{variant['id']}/answer", json=bad_answer(variant)).json()
    assert result["review"]["passed"] is False
    assert result["review"]["next_due"] == (date.today() + timedelta(days=1)).isoformat()
    assert len(client.get("/api/mistakes").json()) == 4, "une reprise ratée ne crée pas une nouvelle erreur"


# -- Répétition espacée ---------------------------------------------------------
def test_mastered_lesson_gets_spaced_reviews(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    _master(client, lid)
    run_jobs()
    lesson_items = [i for i in _items(lid) if i["kind"] == "lesson"]
    assert lesson_items == [{"kind": "lesson", "stage": 0, "due": date.today() + timedelta(days=1), "state": "active", "ready": True}]

    nxt = client.get("/api/next").json()
    assert nxt["kind"] == "done" and nxt["next_review"] == (date.today() + timedelta(days=1)).isoformat()

    _make_due(lid, "lesson")
    nxt = client.get("/api/next").json()
    assert nxt["kind"] == "review" and nxt["size"]["questions"] == 3 and nxt["subjects"] == ["Maths"]

    for expected_days in (3, 7, 14, 30):
        session = client.get("/api/reviews/today").json()
        recall = next(i for i in session["items"] if i["kind"] == "lesson")
        for q in recall["questions"]:
            last = client.post(f"/api/questions/{q['id']}/answer", json=good_answer(q)).json()
        assert last["review"]["passed"] is True
        assert last["review"]["next_due"] == (date.today() + timedelta(days=expected_days)).isoformat()
        run_jobs()  # les questions du rappel suivant se préparent toutes seules
        _make_due(lid, "lesson")

    # Cinquième rappel réussi (J+30) : la série est terminée.
    recall = next(i for i in client.get("/api/reviews/today").json()["items"] if i["kind"] == "lesson")
    for q in recall["questions"]:
        last = client.post(f"/api/questions/{q['id']}/answer", json=good_answer(q)).json()
    assert last["review"] == {"passed": True, "done": True, "next_due": None}


def test_failed_recall_steps_back_and_feeds_the_error_book(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    _master(client, lid)
    run_jobs()
    _make_due(lid, "lesson")
    recall = next(i for i in client.get("/api/reviews/today").json()["items"] if i["kind"] == "lesson")
    for q in recall["questions"]:
        last = client.post(f"/api/questions/{q['id']}/answer", json=bad_answer(q)).json()
    assert last["review"]["passed"] is False
    assert last["review"]["next_due"] == (date.today() + timedelta(days=1)).isoformat()
    assert {m["source"] for m in client.get("/api/mistakes").json()} == {"rappel"}
    assert len(client.get("/api/mistakes").json()) == 3


def test_flashcards_are_self_graded(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    advance(client, lid, "quiz")
    client.post(f"/api/lessons/{lid}/steps/resume/validate")  # deux fois : pas de doublons
    assert sum(i["kind"] == "card" for i in _items(lid)) == 3

    _make_due(lid, "card")
    session = client.get("/api/reviews/today").json()
    assert session["size"]["cards"] == 3 and session["size"]["questions"] == 0
    card = session["items"][0]
    assert card["card"]["recto"] == "Terme 1" and card["card"]["verso"]
    knew = client.post(f"/api/reviews/{card['id']}/card", json={"knew": True}).json()
    assert knew["next_due"] == (date.today() + timedelta(days=3)).isoformat()
    forgot = client.post(f"/api/reviews/{session['items'][1]['id']}/card", json={"knew": False}).json()
    assert forgot["next_due"] == (date.today() + timedelta(days=1)).isoformat()
    assert client.get("/api/reviews/today").json()["size"]["cards"] == 1


def test_session_mixes_lessons_and_subjects(client):
    maths = import_text(client, title="Leçon de maths")
    physique = import_text(client, code="pc", title="Leçon de physique")
    run_jobs()
    for lesson in (maths, physique):
        advance(client, lesson["id"], "quiz")
        _make_due(lesson["id"])
    session = client.get("/api/reviews/today").json()
    order = [i["lesson"]["id"] for i in session["items"]]
    assert len(order) == 6
    assert all(a != b for a, b in zip(order, order[1:])), "deux éléments qui se suivent viennent de leçons différentes"

    plan = client.get("/api/reviews/plan").json()
    assert plan["today"]["total_due"] == 6 and {s["subject"]["name"] for s in plan["today"]["subjects"]} == {"Maths", "Physique-Chimie"}
    assert plan["upcoming"][0]["count"] == 6 and len(plan["upcoming"]) == 14


def test_reviews_are_tightened_before_an_exam():
    from app.models import ReviewItem
    from app.services.srs import effective_due

    today = date(2026, 3, 10)
    far = ReviewItem(kind="lesson", due=today + timedelta(days=20), last_reviewed=today - timedelta(days=1))
    assert effective_due(far, None, today) == today + timedelta(days=20)
    # Contrôle dans 5 jours : pas plus de deux jours sans rappel.
    assert effective_due(far, today + timedelta(days=5), today) == today + timedelta(days=1)
    # Contrôle lointain : un dernier rappel la veille.
    assert effective_due(far, today + timedelta(days=12), today) == today + timedelta(days=11)
    # Veille du contrôle, pas encore revu aujourd'hui : dû aujourd'hui.
    assert effective_due(far, today + timedelta(days=1), today) == today
    reviewed = ReviewItem(kind="lesson", due=today + timedelta(days=20), last_reviewed=today)
    assert effective_due(reviewed, today + timedelta(days=1), today) == today + timedelta(days=2)
    # Contrôle passé : calendrier normal.
    assert effective_due(far, today - timedelta(days=2), today) == today + timedelta(days=20)


# -- Vidéos --------------------------------------------------------------------
def _fake_youtube(monkeypatch, responder):
    from app import config
    from app.services import youtube

    monkeypatch.setenv("YOUTUBE_API_KEY", "CLE-YT")
    config.get_config.cache_clear()
    calls = []

    def fake_get(path, params, key):
        calls.append((path, dict(params), key))
        result = responder(path, params)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(youtube, "_get", fake_get)
    monkeypatch.setattr(youtube, "transcript_excerpt", lambda vid, langs: "sous-titres" if vid == "v1" else None)
    return calls


def _video(vid, title, duration):
    return {
        "id": vid,
        "snippet": {"title": title, "channelTitle": "Prof", "description": "cours", "defaultAudioLanguage": "fr"},
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": "5000"},
    }


def test_without_youtube_key_the_path_is_not_blocked(client):
    lesson = import_text(client)
    run_jobs()
    step = client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()
    assert step["videos"] == {"status": "no_key", "videos": []} and step["ready"] is True
    assert client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["problem"] is None


def test_videos_are_searched_compared_and_explained(client, monkeypatch):
    def responder(path, params):
        if path == "search":
            assert params["type"] == "video" and params["regionCode"] == "MA" and params["relevanceLanguage"] == "fr"
            return {"items": [{"id": {"videoId": v}} for v in ("v1", "v2", "v3", "court", "long")]}
        return {
            "items": [
                _video("v1", "Généralités sur les fonctions - tronc commun", "PT12M"),
                _video("v2", "Les fonctions TCS exercices corrigés", "PT20M5S"),
                _video("v3", "Fonctions : cours complet", "PT35M"),
                _video("court", "Astuce fonctions", "PT40S"),
                _video("long", "Révision générale", "PT3H"),
            ]
        }

    calls = _fake_youtube(monkeypatch, responder)
    lesson = import_text(client)
    run_jobs()
    content = client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()["videos"]
    assert content["status"] == "ok"
    assert [v["id"] for v in content["videos"]] == ["v1", "v2", "v3"], "trop courtes et trop longues écartées"
    assert all(v["raison"] for v in content["videos"]) and content["videos"][0]["subtitles_used"] is True
    assert content["videos"][0]["duration_s"] == 720
    assert [c[0] for c in calls] == ["search", "search", "videos"] and all(c[2] == "CLE-YT" for c in calls)
    assert "tronc commun" in calls[0][1]["q"]


def test_youtube_quota_or_bad_key_does_not_block(client, monkeypatch):
    from app.services.youtube import YouTubeUnavailable

    _fake_youtube(monkeypatch, lambda path, params: YouTubeUnavailable("quota", "quota épuisé"))
    lesson = import_text(client)
    run_jobs()
    detail = client.get(f"/api/lessons/{lesson['id']}").json()
    assert detail["generation"]["problem"] is None and detail["generation"]["done"] == 10
    assert client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()["videos"]["status"] == "quota"

    # Au prochain démarrage, la recherche est retentée.
    from app.services.generation.worker import recover_on_startup

    recover_on_startup()
    assert client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["total"] == 11


def test_youtube_network_failure_is_retried(client, monkeypatch):
    state = {"fail": True}

    def responder(path, params):
        if state["fail"]:
            return LLMError("network", "coupure")
        if path == "search":
            return {"items": [{"id": {"videoId": "v1"}}]}
        return {"items": [_video("v1", "Fonctions tronc commun", "PT10M")]}

    _fake_youtube(monkeypatch, responder)
    lesson = import_text(client)
    from app.services.generation.worker import run_pending

    run_pending(ignore_backoff=False)
    problem = client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["problem"]
    assert problem["kind"] == "network" and problem["label"] == "Sélection de vidéos" and problem["fatal"] is False
    state["fail"] = False
    run_jobs()
    assert client.get(f"/api/lessons/{lesson['id']}/steps/comprendre").json()["videos"]["videos"][0]["id"] == "v1"


def test_youtube_http_errors(monkeypatch):
    import httpx

    from app.services import youtube

    def respond(status, body):
        return lambda *a, **k: httpx.Response(status, json=body, request=httpx.Request("GET", "https://x"))

    monkeypatch.setattr(httpx, "get", respond(403, {"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}}))
    with pytest.raises(youtube.YouTubeUnavailable) as err:
        youtube.search("q", "fr", "k")
    assert err.value.reason == "quota"
    monkeypatch.setattr(httpx, "get", respond(400, {"error": {"message": "bad key", "errors": [{"reason": "keyInvalid"}]}}))
    with pytest.raises(youtube.YouTubeUnavailable) as err:
        youtube.search("q", "fr", "k")
    assert err.value.reason == "key"
    monkeypatch.setattr(httpx, "get", respond(503, {}))
    with pytest.raises(LLMError) as llm_err:
        youtube.search("q", "fr", "k")
    assert llm_err.value.kind == "server"
    assert youtube.transcript_excerpt("inconnu", ["fr"]) is None, "sans bibliothèque de sous-titres : on s'en passe"


# -- Méthodes types ------------------------------------------------------------
def test_methods_sheet_per_chapter(client):
    lesson = import_text(client)
    run_jobs()
    detail = client.get(f"/api/lessons/{lesson['id']}").json()
    assert detail["has_methods"] is True
    sheet = client.get(f"/api/chapters/{detail['chapter']['id']}/methods").json()
    assert sheet["subject"]["name"] == "Maths" and len(sheet["lessons"]) == 1
    method = sheet["lessons"][0]["types"][0]
    assert method["nom"] and method["reconnaitre"] and len(method["etapes"]) == 3
    assert client.get("/api/chapters/999/methods").status_code == 404


def test_older_lessons_get_the_new_content_on_startup(client):
    from app.db import session_scope
    from app.models import Job
    from app.services.generation.worker import recover_on_startup

    lesson = import_text(client)
    with session_scope() as db:  # leçon importée avec la version 1 : ni vidéos, ni méthodes, ni carte mentale
        for job in db.query(Job).filter(Job.kind.in_(["videos", "methods", "mindmap"])):
            db.delete(job)
    assert client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["total"] == 7
    recover_on_startup()
    recover_on_startup()  # sans doublon
    assert client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["total"] == 10
    assert run_jobs() == 10
