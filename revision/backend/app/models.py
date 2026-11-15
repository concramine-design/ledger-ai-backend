"""Tables SQLite."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))  # sciences | langue | philo
    language: Mapped[str] = mapped_column(String(2), default="fr")  # fr | ar | en
    color: Mapped[str] = mapped_column(String(16), default="#7c9cff")
    position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="subject", cascade="all, delete-orphan")
    exams: Mapped[list["Exam"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(120), default="")

    subject: Mapped[Subject] = relationship(back_populates="exams")


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    title: Mapped[str] = mapped_column(String(160))
    position: Mapped[int] = mapped_column(Integer, default=0)

    subject: Mapped[Subject] = relationship(back_populates="chapters")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"))
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(8))  # text | pdf | photo
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    mastered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    chapter: Mapped[Chapter] = relationship(back_populates="lessons")
    files: Mapped[list["LessonFile"]] = relationship(cascade="all, delete-orphan", order_by="LessonFile.position")
    jobs: Mapped[list["Job"]] = relationship(cascade="all, delete-orphan", order_by="Job.id")
    artifacts: Mapped[list["Artifact"]] = relationship(cascade="all, delete-orphan")
    sets: Mapped[list["QuestionSet"]] = relationship(cascade="all, delete-orphan", back_populates="lesson")
    progress: Mapped[list["StepProgress"]] = relationship(cascade="all, delete-orphan")
    messages: Mapped[list["ChatMessage"]] = relationship(cascade="all, delete-orphan", order_by="ChatMessage.id")
    reports: Mapped[list["Report"]] = relationship(cascade="all, delete-orphan")

    @property
    def subject(self) -> Subject:
        return self.chapter.subject


class LessonFile(Base):
    __tablename__ = "lesson_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(80), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    """Une tâche de génération en arrière-plan."""

    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    kind: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    depends_on: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_kind: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_try_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Artifact(Base):
    """Contenu généré non interactif : explication, résumé, ré-explication."""

    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    kind: Mapped[str] = mapped_column(String(32))  # explanation | summary | reexplain
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QuestionSet(Base):
    """Un mini-test, un quiz (une version = un passage) ou un niveau d'exercices."""

    __tablename__ = "question_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    kind: Mapped[str] = mapped_column(String(16))  # minitest | quiz | exercises
    level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(12), default="active")  # active | passed | failed
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    lesson: Mapped[Lesson] = relationship(back_populates="sets")
    questions: Mapped[list["Question"]] = relationship(
        cascade="all, delete-orphan", back_populates="qset", order_by="Question.position"
    )


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    qtype: Mapped[str] = mapped_column(String(12))  # qcm | ouverte | exercice
    notion: Mapped[str] = mapped_column(String(200), default="")
    data: Mapped[dict] = mapped_column(JSON)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revealed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    qset: Mapped[QuestionSet] = relationship(back_populates="questions")
    attempts: Mapped[list["Attempt"]] = relationship(cascade="all, delete-orphan", order_by="Attempt.id")


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    answer_text: Mapped[str] = mapped_column(Text, default="")
    choice_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | graded
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_reveal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StepProgress(Base):
    """Une ligne par étape validée."""

    __tablename__ = "step_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    step: Mapped[str] = mapped_column(String(16))
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    done_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    """« Signaler une erreur » sur une explication ou une correction."""

    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    target: Mapped[str] = mapped_column(String(80))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
