"""Lecture des documents importés : PDF (texte ou scanné) et photos du cahier."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from .generation import prompts
from .llm import LLM, LLMError, LLMRequest

try:  # photos d'iPhone (HEIC) : facultatif
    import pillow_heif  # type: ignore[import-not-found]

    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001
    pass

MAX_PDF_PAGES_OCR = 20
IMAGES_PER_CALL = 4
MAX_SIDE = 1800


def prepare_image(data: bytes) -> tuple[bytes, str]:
    """Redresse, réduit et convertit une photo en JPEG avant de l'envoyer à l'IA."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise LLMError("input", f"image illisible : {exc}") from exc
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def read_pdf(path: Path) -> tuple[str, list[tuple[bytes, str]]]:
    """Renvoie (texte, images). Les images ne sont remplies que pour un PDF scanné."""
    import pymupdf as fitz

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise LLMError("input", f"PDF illisible : {exc}") from exc
    with doc:
        pages = [page.get_text().strip() for page in doc]
        text = "\n\n".join(p for p in pages if p)
        if pages and len(text) / len(pages) >= 80:
            return text, []
        images = []
        for page in list(doc)[:MAX_PDF_PAGES_OCR]:
            pix = page.get_pixmap(dpi=150)
            images.append(prepare_image(pix.tobytes("png")))
        return text, images


def ocr(llm: LLM, images: list[tuple[bytes, str]], subject: str, language: str) -> str:
    """Lit le texte des images avec le modèle de vision, par petits lots."""
    chunks = []
    for start in range(0, len(images), IMAGES_PER_CALL):
        batch = images[start : start + IMAGES_PER_CALL]
        req = LLMRequest(
            task="ocr",
            system="",
            messages=[{"role": "user", "content": prompts.ocr(subject, language)}],
            json_mode=False,
            images=batch,
            temperature=0.0,
            payload={"count": len(batch)},
        )
        chunks.append(llm.generate(req).strip())
    return "\n\n".join(c for c in chunks if c)
