"""Application FastAPI : sert l'API et l'interface compilée."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST, get_config
from .db import init_db
from .db import new_session
from .routers import chat, exams, lessons, parent, reviews, setup, steps
from .services.generation.worker import recover_on_startup, worker
from .services.llm import LLMError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
# httpx écrit chaque adresse appelée dans le journal : on le fait taire pour qu'aucune clé n'y apparaisse.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    recover_on_startup()
    if get_config().run_worker:
        worker.start()
        with new_session() as db:
            exams.resume_pending(db)
    yield
    worker.stop()


app = FastAPI(title="Mes révisions", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(LLMError)
async def llm_error(_request: Request, exc: LLMError) -> JSONResponse:
    """L'IA est injoignable ou a mal répondu : message clair, l'interface propose de réessayer."""
    return JSONResponse(status_code=503, content={"detail": {"kind": exc.kind, "message": exc.message}})


for module in (setup, lessons, steps, chat, reviews, parent, exams):
    app.include_router(module.router)


if (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Introuvable.")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
