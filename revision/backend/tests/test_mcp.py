"""Préparation par Claude via MCP : réservation des tâches, consignes, vérification, relais par Gemini."""
from __future__ import annotations

import asyncio
import io
import json
from datetime import timedelta

import pytest
from PIL import Image

from .conftest import LESSON_TEXT, run_jobs, subject_id


@pytest.fixture()
def claude_mode(client, monkeypatch):
    from app import config

    monkeypatch.setenv("PREPARATION_PAR", "claude")
    monkeypatch.setenv("HEURE_LIMITE_CLAUDE", "07:00")
    config.get_config.cache_clear()
    yield client
    config.get_config.cache_clear()


def _import(client, text=LESSON_TEXT, files=None):
    data = {"subject_id": subject_id(client), "chapter_title": "Fonctions", "title": "Généralités", "text": text}
    resp = client.post("/api/lessons", data=data, files=files or [])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _jobs(lesson_id):
    from app.db import session_scope
    from app.models import Job

    with session_scope() as db:
        return {f"{j.kind}{(j.params or {}).get('level', '')}": (j.id, j.status, j.executor) for j in db.query(Job).filter(Job.lesson_id == lesson_id)}


def _mock_answer(task: str, payload: dict) -> str:
    """Ce que « Claude » répondrait : on prend la réponse de l'IA simulée, au bon format."""
    from app.services.llm.mock import MockProvider

    return json.dumps(getattr(MockProvider(), f"_{task}")(payload), ensure_ascii=False)


def test_gemini_mode_is_unchanged(client):
    lesson = _import(client)
    assert {e for _, _, e in _jobs(lesson["id"]).values()} == {"auto"}
    assert lesson["generation"]["claude"] is None


def test_claude_jobs_wait_for_claude_and_reactive_ones_do_not(claude_mode):
    from app.services.generation.worker import run_pending

    lesson = _import(claude_mode)
    jobs = _jobs(lesson["id"])
    assert jobs["explanation"][2] == "claude" and jobs["quiz"][2] == "claude" and jobs["exercises3"][2] == "claude"
    assert jobs["videos"][2] == "auto", "les vidéos restent automatiques (recherche YouTube)"
    assert run_pending(ignore_backoff=False) == 0, "la file ne touche pas aux tâches réservées à Claude"
    status = claude_mode.get(f"/api/lessons/{lesson['id']}").json()["generation"]
    assert status["claude"]["waiting"] == 9 and status["claude"]["until"].endswith("Z")

    # Un nouveau test après un échec ne doit pas attendre le lendemain.
    from app.db import session_scope
    from app.models import Lesson
    from app.services.generation.worker import enqueue

    with session_scope() as db:
        job = enqueue(db, db.get(Lesson, lesson["id"]), "minitest", {"version": 2})
        assert job.executor == "auto"


def test_claude_prepares_a_lesson_through_the_tools(claude_mode):
    from app import mcp_server as m

    lesson = _import(claude_mode)
    lid = lesson["id"]
    todo = m.travail_en_attente()
    assert "9 tâche(s) en attente" in todo and "Explication [explanation] — PRÊTE" in todo
    assert "Mini-test [minitest] — après « explanation »" in todo

    jobs = _jobs(lid)
    explanation_id = jobs["explanation"][0]
    minitest_id = jobs["minitest"][0]
    assert "pas encore prête" in m.obtenir_consigne(minitest_id)

    consigne = m.obtenir_consigne(explanation_id)
    assert "=== Rôle et règles ===" in consigne and "ensemble de définition" in consigne.lower()
    assert '"sections"' in consigne and f"enregistrer_contenu(tache_id={explanation_id}" in consigne
    assert "déjà ouverte (réservée)" in m.travail_en_attente()

    # Réponse invalide : refusée avec une explication, rien n'est enregistré.
    refused = m.enregistrer_contenu(explanation_id, '{"titre": "x"}')
    assert refused.startswith("Refusé par Révision") and "sections" in refused
    assert _jobs(lid)["explanation"][1] == "pending"
    assert m.enregistrer_contenu(explanation_id, "désolé").startswith("Refusé par Révision")

    # Réponse valide : enregistrée, la suite se débloque.
    good = _mock_answer("explanation", {"text": LESSON_TEXT, "title": "Généralités"})
    assert m.enregistrer_contenu(explanation_id, good).endswith("enregistrée ✅.")
    assert "déjà faite" in m.enregistrer_contenu(explanation_id, good)
    assert "Mini-test [minitest] — PRÊTE" in m.travail_en_attente()

    # Claude fait tout le reste, tâche par tâche.
    tasks = {"minitest": "minitest", "mindmap": "mindmap", "summary": "summary", "quiz": "quiz", "exercises1": "exercises",
             "exercises2": "exercises", "exercises3": "exercises", "methods": "methods"}
    for key, task in tasks.items():
        job_id = _jobs(lid)[key][0]
        m.obtenir_consigne(job_id)
        level = int(key[-1]) if key.startswith("exercises") else 1
        payload = {"text": LESSON_TEXT, "title": "Généralités", "notions": ["Notion 1"], "version": 1, "level": level, "kind": "sciences", "types": ["Application du cours"]}
        assert m.enregistrer_contenu(job_id, _mock_answer(task, payload)).endswith("✅."), key
    assert m.travail_en_attente().startswith("Rien à préparer")

    run_jobs()  # les vidéos (automatiques) se font de leur côté
    detail = claude_mode.get(f"/api/lessons/{lid}").json()
    assert detail["generation"]["done"] == 10 and detail["generation"]["claude"] is None
    assert detail["current_ready"] is True
    assert claude_mode.get(f"/api/lessons/{lid}/steps/comprendre").json()["content"]["sections"]


def test_claude_reads_the_photos_and_transcribes(claude_mode):
    from app import mcp_server as m
    from mcp.server.mcpserver import Image as McpImage

    buf = io.BytesIO()
    Image.new("RGB", (2400, 3200), (240, 240, 235)).save(buf, format="JPEG")
    files = [("files", (f"p{i}.jpg", buf.getvalue(), "image/jpeg")) for i in range(2)]
    lesson = _import(claude_mode, text="Titre noté à la main.", files=files)
    lid = lesson["id"]
    assert _jobs(lid)["extract"][2] == "claude"

    info = m.lire_lecon(lid)
    assert "Pages à lire avec lire_page : 2" in info and "Titre noté à la main." in info
    page = m.lire_page(lid, 1)
    assert page[0] == f"Leçon {lid}, page 1/2" and isinstance(page[1], McpImage)
    assert "entre 1 et 2" in m.lire_page(lid, 3)[0]
    assert max(Image.open(io.BytesIO(page[1].data)).size) == m.MAX_SIDE

    assert "trop courte" in m.enregistrer_texte_lecon(lid, "court")
    assert "enregistré" in m.enregistrer_texte_lecon(lid, LESSON_TEXT)
    source = claude_mode.get(f"/api/lessons/{lid}/source").json()["text"]
    assert source.startswith("Titre noté à la main.") and "ensemble de définition" in source
    assert "Explication [explanation] — PRÊTE" in m.travail_en_attente()


def test_gemini_takes_over_after_the_delay(claude_mode):
    from app.db import session_scope
    from app.models import Job
    from app.services.generation.worker import run_pending

    lesson = _import(claude_mode)
    with session_scope() as db:
        for job in db.query(Job).filter(Job.lesson_id == lesson["id"]):
            job.created_at -= timedelta(hours=25)  # Claude n'est pas passé de la nuit
    assert run_pending() == 10
    assert claude_mode.get(f"/api/lessons/{lesson['id']}").json()["current_ready"] is True


def test_prepare_now_button(claude_mode):
    lesson = _import(claude_mode)
    detail = claude_mode.post(f"/api/lessons/{lesson['id']}/prepare-now").json()
    assert detail["generation"]["claude"] is None
    assert run_jobs() == 10


def test_followups_are_prepared_by_claude(claude_mode):
    """Les rappels du lendemain et les reprises d'erreurs sont prévisibles : Claude peut les préparer."""
    from app.db import session_scope
    from app.models import Lesson
    from app.services.generation.worker import enqueue

    lesson = _import(claude_mode)
    with session_scope() as db:
        target = db.get(Lesson, lesson["id"])
        assert enqueue(db, target, "review_set", {"item_id": 1}).executor == "claude"
        assert enqueue(db, target, "error_variant", {"item_id": 1}).executor == "claude"
        assert enqueue(db, target, "reexplain", {"set_id": 1}).executor == "auto"
        assert enqueue(db, target, "exercise_variant", {"question_id": 1}).executor == "auto"


def test_mcp_server_exposes_the_tools(claude_mode):
    from app.mcp_server import build_server

    server = build_server()

    async def check():
        names = {t.name for t in await server.list_tools()}
        assert names == {"travail_en_attente", "lire_lecon", "lire_page", "enregistrer_texte_lecon", "obtenir_consigne", "enregistrer_contenu"}
        prompts = {p.name for p in await server.list_prompts()}
        assert "preparer_lecons" in prompts
        result = await server.call_tool("travail_en_attente", {})
        assert "Rien à préparer" in result.content[0].text

    asyncio.run(check())


def test_real_stdio_protocol(claude_mode, tmp_path):
    """Le serveur tel que l'application Claude le lance : un processus séparé qui parle MCP sur stdin/stdout."""
    import os
    import sys
    from pathlib import Path

    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    lesson = _import(claude_mode)
    explanation_id = _jobs(lesson["id"])["explanation"][0]
    launcher = Path(__file__).resolve().parents[1] / "mcp_revision.py"
    env = {**os.environ, "PREPARATION_PAR": "claude", "REVISION_DATA_DIR": os.environ["REVISION_DATA_DIR"]}

    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(launcher)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.server_info.name == "Révision" and "tronc commun" in (init.instructions or "")
                todo = await session.call_tool("travail_en_attente", {})
                assert "9 tâche(s) en attente" in todo.content[0].text
                consigne = await session.call_tool("obtenir_consigne", {"tache_id": explanation_id})
                assert '"sections"' in consigne.content[0].text
                answer = _mock_answer("explanation", {"text": LESSON_TEXT, "title": "Généralités"})
                saved = await session.call_tool("enregistrer_contenu", {"tache_id": explanation_id, "reponse": answer})
                assert saved.content[0].text.endswith("✅.")

    asyncio.run(run())
    assert _jobs(lesson["id"])["explanation"][1] == "done"


def test_deadline_is_the_next_morning_limit(claude_mode):
    from datetime import datetime, timezone

    from app.models import Job
    from app.services.generation.worker import claude_deadline

    def local(h, m=0, day=10):
        return datetime(2026, 3, day, h, m).astimezone()

    def deadline_for(local_created):
        job = Job(created_at=local_created.astimezone(timezone.utc).replace(tzinfo=None))
        return claude_deadline(job).replace(tzinfo=timezone.utc).astimezone()

    assert deadline_for(local(20, 30)).strftime("%d %H:%M") == "11 07:00", "importée le soir : relais le lendemain à 7 h"
    assert deadline_for(local(1, 15, day=11)).strftime("%d %H:%M") == "11 07:00", "importée dans la nuit : relais le matin même"
    assert deadline_for(local(9, 0, day=11)).strftime("%d %H:%M") == "12 07:00", "importée le matin : relais le lendemain (bouton « Préparer maintenant » sinon)"
