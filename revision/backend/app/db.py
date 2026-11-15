"""Connexion SQLite, création des tables et valeurs par défaut."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_config
from .models import Base, Setting, Subject

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None

DEFAULT_SETTINGS: dict[str, Any] = {
    "onboarded": False,
    "minitest_threshold": 70,  # % pour valider le mini-test
    "quiz_threshold": 80,  # % pour valider le quiz complet
    "exercise_threshold": 70,  # % pour qu'un exercice compte comme réussi
    "exercises_required": 2,  # exercices réussis pour valider un niveau
}

# (code, nom, type, langue par défaut, couleur)
DEFAULT_SUBJECTS = [
    ("maths", "Maths", "sciences", "fr", "#7c9cff"),
    ("pc", "Physique-Chimie", "sciences", "fr", "#4fd1a5"),
    ("svt", "SVT", "sciences", "fr", "#8bd450"),
    ("philo", "Philosophie", "philo", "ar", "#c79bff"),
    ("arabe", "Arabe", "langue", "ar", "#f5b84a"),
    ("francais", "Français", "langue", "fr", "#ff8fa3"),
    ("anglais", "Anglais", "langue", "en", "#5cc8f0"),
]


def init_engine() -> Engine:
    """(Ré)initialise le moteur à partir de la configuration courante."""
    global _engine, _Session
    cfg = get_config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(
        f"sqlite:///{cfg.db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(_engine, "connect")
    def _pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _add_missing_columns(engine: Engine) -> None:
    """Migration minimale : ajoute les colonnes apparues dans une version plus récente."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def init_db() -> None:
    engine = init_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    with session_scope() as db:
        if db.query(Subject).count() == 0:
            for pos, (code, name, kind, lang, color) in enumerate(DEFAULT_SUBJECTS):
                db.add(Subject(code=code, name=name, kind=kind, language=lang, color=color, position=pos))
        for key, value in DEFAULT_SETTINGS.items():
            if db.get(Setting, key) is None:
                db.add(Setting(key=key, value=value))


def new_session() -> Session:
    if _Session is None:
        init_engine()
    assert _Session is not None
    return _Session()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI."""
    db = new_session()
    try:
        yield db
    finally:
        db.close()


def get_settings(db: Session) -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
