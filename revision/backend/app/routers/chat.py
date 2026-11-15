"""Chat sur la leçon (il pose d'abord une question) et signalement d'erreurs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatMessage, Report
from ..services.generation import prompts
from ..services.generation.generators import build_ctx
from ..services.llm import LLMRequest, get_llm
from .lessons import get_lesson

router = APIRouter(prefix="/api")

HISTORY = 12


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.get("/lessons/{lesson_id}/chat")
def history(lesson_id: int, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    return {"messages": [{"role": m.role, "content": m.content} for m in lesson.messages]}


@router.post("/lessons/{lesson_id}/chat")
def send(lesson_id: int, body: MessageIn, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, lesson_id)
    if not lesson.raw_text:
        raise HTTPException(409, "La leçon n'est pas encore lue.")
    past = [{"role": m.role, "content": m.content} for m in lesson.messages[-HISTORY:]]
    while past and past[0]["role"] != "user":
        past.pop(0)
    question = body.message.strip()
    req = LLMRequest(
        task="chat",
        system=prompts.chat_system(build_ctx(lesson)),
        messages=[*past, {"role": "user", "content": question}],
        json_mode=False,
        temperature=0.5,
    )
    reply = get_llm().generate(req).strip()  # en cas d'échec : erreur 503, rien n'est enregistré
    lesson.messages.append(ChatMessage(role="user", content=question))
    lesson.messages.append(ChatMessage(role="assistant", content=reply))
    db.commit()
    return {"reply": reply}


class ReportIn(BaseModel):
    lesson_id: int
    target: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(default="", max_length=2000)
    comment: str = Field(default="", max_length=2000)


@router.post("/reports")
def report(body: ReportIn, db: Session = Depends(get_db)) -> dict:
    lesson = get_lesson(db, body.lesson_id)
    lesson.reports.append(Report(target=body.target, excerpt=body.excerpt, comment=body.comment.strip()))
    db.commit()
    return {"ok": True}
