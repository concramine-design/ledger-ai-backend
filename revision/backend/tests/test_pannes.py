"""Pannes : internet coupé, quota, clé refusée, réponse mal formée. La progression n'est jamais perdue."""
from __future__ import annotations

from app.services.llm import LLMError

from .conftest import LESSON_TEXT, good_answer, import_text, run_jobs, take_test


def _jobs(lesson_id: int) -> dict[str, tuple[str, int]]:
    from app.db import session_scope
    from app.models import Job

    with session_scope() as db:
        return {
            f"{j.kind}{(j.params or {}).get('level', '')}": (j.status, j.attempts)
            for j in db.query(Job).filter(Job.lesson_id == lesson_id)
        }


def test_network_failure_keeps_job_queued_and_retries(client, mock_llm):
    from app.services.generation.worker import run_pending

    lesson = import_text(client)
    mock_llm.failures = [LLMError("network", "pas d'internet")]
    assert run_pending(ignore_backoff=False) == 1  # l'explication échoue ; le reste attend
    jobs = _jobs(lesson["id"])
    assert jobs["explanation"] == ("pending", 1)
    assert jobs["quiz"] == ("pending", 0)

    detail = client.get(f"/api/lessons/{lesson['id']}").json()
    problem = detail["generation"]["problem"]
    assert problem["kind"] == "network" and problem["fatal"] is False and problem["retry_in"] > 0
    assert "internet" in problem["message"]

    # Le bouton « Réessayer » relance tout de suite, sans attendre le délai.
    assert run_pending(ignore_backoff=False) == 0
    client.post(f"/api/lessons/{lesson['id']}/retry")
    assert run_pending(ignore_backoff=False) == 10
    detail = client.get(f"/api/lessons/{lesson['id']}").json()
    assert detail["generation"]["problem"] is None and detail["generation"]["done"] == 10


def test_rate_limit_honours_retry_after(client, mock_llm):
    from app.db import session_scope
    from app.models import Job, utcnow
    from app.services.generation.worker import run_pending

    lesson = import_text(client)
    mock_llm.failures = [LLMError("rate_limit", "quota", retry_after=120)]
    run_pending(ignore_backoff=False)
    with session_scope() as db:
        job = db.query(Job).filter(Job.lesson_id == lesson["id"], Job.kind == "explanation").one()
        wait = (job.next_try_at - utcnow()).total_seconds()
    assert 100 < wait <= 120


def test_invalid_key_is_fatal_until_retry(client, mock_llm):
    lesson = import_text(client)
    mock_llm.failures = [LLMError("auth", "clé refusée")]
    run_jobs()
    assert _jobs(lesson["id"])["explanation"] == ("failed", 1)
    problem = client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["problem"]
    assert problem["fatal"] is True and ".env" in problem["message"]

    client.post(f"/api/lessons/{lesson['id']}/retry")
    run_jobs()
    assert client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["done"] == 10


def test_bad_output_is_retried_three_times_then_fails(client, mock_llm):
    lesson = import_text(client)
    mock_llm.failures = [LLMError("bad_output", "json")] * 2
    run_jobs()
    assert _jobs(lesson["id"])["explanation"] == ("done", 2)

    other = import_text(client, title="Autre leçon")
    mock_llm.failures = [LLMError("bad_output", "json")] * 3
    run_jobs()
    assert _jobs(other["id"])["explanation"] == ("failed", 3)


def test_restart_resumes_interrupted_and_failed_jobs(client, mock_llm):
    from app.db import session_scope
    from app.models import Job
    from app.services.generation.worker import recover_on_startup

    lesson = import_text(client)
    with session_scope() as db:
        jobs = db.query(Job).filter(Job.lesson_id == lesson["id"]).order_by(Job.id).all()
        jobs[0].status = "running"  # coupure en pleine génération
        jobs[1].status = "failed"
    recover_on_startup()
    assert run_jobs() == 10
    assert all(status == "done" for status, _ in _jobs(lesson["id"]).values())


def test_progress_survives_a_failure_during_grading(client, mock_llm):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    client.post(f"/api/lessons/{lid}/steps/comprendre/validate")

    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    open_q = next(q for q in step["set"]["questions"] if q["type"] == "ouverte")
    payload = good_answer(open_q)

    mock_llm.failures = [LLMError("network", "coupure")]
    resp = client.post(f"/api/questions/{open_q['id']}/answer", json=payload)
    assert resp.status_code == 503
    assert resp.json()["detail"]["kind"] == "network" and "internet" in resp.json()["detail"]["message"]

    # Sa réponse est conservée, l'étape validée aussi.
    step = client.get(f"/api/lessons/{lid}/steps/minitest").json()
    kept = next(q for q in step["set"]["questions"] if q["id"] == open_q["id"])
    assert kept["attempt"] == {
        "status": "pending", "answer_text": payload["answer_text"], "choice_index": None, "score": None, "feedback": None,
    }
    assert client.get(f"/api/lessons/{lid}").json()["path"][0]["status"] == "done"

    # Nouvelle tentative : corrigée, sans doublon.
    graded = client.post(f"/api/questions/{open_q['id']}/answer", json=payload).json()
    assert graded["question"]["attempt"]["score"] == 1.0
    from app.db import session_scope
    from app.models import Attempt

    with session_scope() as db:
        assert db.query(Attempt).filter(Attempt.question_id == open_q["id"]).count() == 1


def test_chat_failure_returns_clear_message(client, mock_llm):
    lesson = import_text(client)
    run_jobs()
    mock_llm.failures = [LLMError("rate_limit", "quota")]
    resp = client.post(f"/api/lessons/{lesson['id']}/chat", json={"message": "Aide-moi"})
    assert resp.status_code == 503 and resp.json()["detail"]["kind"] == "rate_limit"
    assert client.get(f"/api/lessons/{lesson['id']}/chat").json()["messages"] == []


def test_no_key_configured(client, monkeypatch):
    from app import config
    from app.services import llm

    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENV_FILE", config.ROOT_DIR / "absent.env")
    config.get_config.cache_clear()
    llm.reset_llm()

    assert client.get("/api/state").json()["ai"] == {"configured": False, "provider": None, "demo": False}
    lesson = import_text(client)
    run_jobs()
    problem = client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["problem"]
    assert problem["kind"] == "config" and problem["fatal"] is True


def test_replacing_the_source_regenerates_everything(client):
    lesson = import_text(client)
    run_jobs()
    lid = lesson["id"]
    client.post(f"/api/lessons/{lid}/steps/comprendre/validate")
    take_test(client, lid, "minitest")

    assert client.put(f"/api/lessons/{lid}/source", json={"text": "trop court"}).status_code == 422
    new_text = LESSON_TEXT.replace("fonction", "application")
    detail = client.put(f"/api/lessons/{lid}/source", json={"text": new_text}).json()
    assert detail["progress"] == 0 and detail["generation"]["done"] == 0 and detail["generation"]["total"] == 10
    run_jobs()
    assert client.get(f"/api/lessons/{lid}/source").json()["text"] == new_text.strip()
    assert client.get(f"/api/lessons/{lid}/steps/minitest").status_code == 403


def test_delete_lesson(client):
    lesson = import_text(client)
    run_jobs()
    assert client.delete(f"/api/lessons/{lesson['id']}").json() == {"ok": True}
    assert client.get(f"/api/lessons/{lesson['id']}").status_code == 404
    assert client.get("/api/next").json() == {"kind": "import"}
    assert all(not s["chapters"] for s in client.get("/api/lessons").json())
