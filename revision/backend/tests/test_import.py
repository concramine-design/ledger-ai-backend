"""Import : texte collé, PDF avec texte, PDF scanné, photos du cahier."""
from __future__ import annotations

import io

import pymupdf as fitz
from PIL import Image

from .conftest import LESSON_TEXT, run_jobs, subject_id


def _pdf_with_text(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=11)
    return doc.tobytes()


def _photo(color=(240, 240, 235)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2400, 3200), color).save(buf, format="JPEG")
    return buf.getvalue()


def _scanned_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=_photo())
    return doc.tobytes()


def _post(client, files, text=""):
    return client.post(
        "/api/lessons",
        data={"subject_id": subject_id(client), "chapter_title": "Fonctions", "title": "Leçon importée", "text": text},
        files=files,
    )


def test_pdf_with_text_layer(client, mock_llm):
    resp = _post(client, [("files", ("cours.pdf", _pdf_with_text(LESSON_TEXT), "application/pdf"))])
    assert resp.status_code == 200, resp.text
    lesson = resp.json()
    assert lesson["source_type"] == "pdf" and lesson["has_text"] is False
    assert lesson["generation"]["total"] == 10 and lesson["generation"]["current"] == "Lecture du document"
    assert run_jobs() == 10
    assert "ocr" not in mock_llm.calls, "un PDF avec texte ne passe pas par l'OCR"
    source = client.get(f"/api/lessons/{lesson['id']}/source").json()["text"]
    assert "ensemble de définition" in source.replace("\n", " ")


def test_scanned_pdf_and_photos_go_through_ocr(client, mock_llm):
    resp = _post(client, [("files", ("scan.pdf", _scanned_pdf(), "application/pdf"))])
    lesson = resp.json()
    run_jobs()
    assert mock_llm.calls.count("ocr") == 1
    assert "mode démonstration" in client.get(f"/api/lessons/{lesson['id']}/source").json()["text"]

    mock_llm.calls.clear()
    files = [("files", (f"page{i}.jpg", _photo(), "image/jpeg")) for i in range(5)]
    resp = _post(client, files, text="Titre noté à la main : généralités sur les fonctions.")
    lesson = resp.json()
    assert lesson["source_type"] == "photo"
    run_jobs()
    assert mock_llm.calls.count("ocr") == 2, "5 photos = 2 appels (4 par appel)"
    source = client.get(f"/api/lessons/{lesson['id']}/source").json()["text"]
    assert source.startswith("Titre noté à la main")
    assert client.get(f"/api/lessons/{lesson['id']}").json()["current_ready"] is True


def test_photos_are_resized_before_being_sent(client):
    from app.services.ingestion import MAX_SIDE, prepare_image

    data, mime = prepare_image(_photo())
    assert mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(data)).size) == MAX_SIDE


def test_rejected_imports(client):
    sid = subject_id(client)
    base = {"subject_id": sid, "chapter_title": "Fonctions", "title": "Leçon"}
    assert client.post("/api/lessons", data={**base, "text": "trop court"}).status_code == 422
    assert client.post("/api/lessons", data={**base, "text": LESSON_TEXT, "title": " "}).status_code == 422
    bad = _post(client, [("files", ("notes.docx", b"xx", "application/octet-stream"))])
    assert bad.status_code == 422 and "PDF" in bad.json()["detail"]
    off = subject_id(client, "svt")
    client.patch(f"/api/subjects/{off}", json={"enabled": False})
    assert client.post("/api/lessons", data={**base, "subject_id": off, "text": LESSON_TEXT}).status_code == 404


def test_unreadable_file_fails_with_a_clear_message(client):
    lesson = _post(client, [("files", ("photo.jpg", b"pas une image", "image/jpeg"))]).json()
    run_jobs()
    problem = client.get(f"/api/lessons/{lesson['id']}").json()["generation"]["problem"]
    assert problem["kind"] == "input" and problem["fatal"] is True and "photo plus nette" in problem["message"]


def test_same_chapter_is_reused(client):
    for title in ("Leçon 1", "Leçon 2"):
        client.post(
            "/api/lessons",
            data={"subject_id": subject_id(client), "chapter_title": " fonctions ", "title": title, "text": LESSON_TEXT},
        )
    maths = next(g for g in client.get("/api/lessons").json() if g["subject"]["code"] == "maths")
    assert len(maths["chapters"]) == 1 and len(maths["chapters"][0]["lessons"]) == 2
    assert len(client.get(f"/api/chapters?subject_id={subject_id(client)}").json()) == 1
