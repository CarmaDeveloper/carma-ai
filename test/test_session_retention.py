"""Chat sessions and their messages are hard-deleted when the retention period ends."""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

import pytest  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.repositories.session_repo import SessionRepository  # noqa: E402


class RecordingAsyncSession:
    """Fake AsyncSession that records the statements and commits."""

    def __init__(self) -> None:
        self.statements = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)

        class Result:
            rowcount = 0

        return Result()

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def compiled(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_cleanup_deletes_messages_and_sessions_by_age_regardless_of_active_flag():
    session = RecordingAsyncSession()
    asyncio.run(SessionRepository(session).delete_old_sessions(30))

    tables = [statement.table.name for statement in session.statements]
    assert tables == ["chatbot_messages", "chatbot_sessions"]
    for statement in session.statements:
        sql = compiled(statement)
        assert sql.startswith("DELETE FROM")
        assert "last_accessed_at" in sql
        assert "is_active" not in sql
    assert session.commits == 1


def test_app_startup_schedules_session_cleanup(monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from app.core.config import settings

    sessions = []

    def factory():
        session = RecordingAsyncSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(main, "async_session_factory", factory)
    monkeypatch.setattr(settings, "CHATBOT_SESSION_RETENTION_DAYS", 30)
    with TestClient(main.create_application()):
        deadline = time.time() + 3
        while not sessions and time.time() < deadline:
            time.sleep(0.05)
    assert sessions, "the cleanup job did not run at startup"
    assert sessions[0].statements[0].table.name == "chatbot_messages"


class FailingAsyncSession(RecordingAsyncSession):
    """Fake AsyncSession whose connection times out, like a paused Aurora Serverless database."""

    async def execute(self, statement):
        raise TimeoutError()


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings = []
        self.errors = []

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        pass


class StopLoop(BaseException):
    """Ends the endless cleanup loop in a test."""


def test_cleanup_retries_soon_after_a_failure_then_waits_the_interval(monkeypatch):
    import main
    from app.core.config import settings

    # Two failed runs (the database is waking up), then runs that work.
    sessions = [FailingAsyncSession(), FailingAsyncSession()]
    monkeypatch.setattr(
        main, "async_session_factory", lambda: sessions.pop(0) if sessions else RecordingAsyncSession()
    )
    monkeypatch.setattr(settings, "CHATBOT_CLEANUP_INTERVAL_SECONDS", 3600)
    monkeypatch.setattr(settings, "CHATBOT_CLEANUP_RETRY_SECONDS", 120)
    logger = RecordingLogger()
    monkeypatch.setattr(main, "setup_logger", lambda name: logger)
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)
        if len(delays) == 4:
            raise StopLoop()

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        asyncio.run(main.run_session_cleanup())

    assert delays == [120, 240, 3600, 3600]
    assert len(logger.warnings) == 1 and "TimeoutError" in logger.warnings[0]
    assert len(logger.errors) == 1 and "failure 2 in a row" in logger.errors[0]


def test_cleanup_retry_delay_doubles_and_never_exceeds_the_interval(monkeypatch):
    import main
    from app.core.config import settings

    monkeypatch.setattr(settings, "CHATBOT_CLEANUP_INTERVAL_SECONDS", 300)
    monkeypatch.setattr(settings, "CHATBOT_CLEANUP_RETRY_SECONDS", 120)

    assert [main.cleanup_retry_delay(n) for n in range(1, 6)] == [120, 240, 300, 300, 300]
    assert main.cleanup_retry_delay(10_000) == 300


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL (postgresql+asyncpg://...) to a disposable database to run this test.",
)
def test_cleanup_against_postgres_removes_old_sessions_and_messages_and_keeps_new_ones():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.database import Base
    from app.models.message import MessageModel
    from app.models.session import SessionModel

    async def scenario():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        old = datetime.now(timezone.utc) - timedelta(days=40)
        ids = {name: uuid.uuid4() for name in ("old_active", "old_inactive", "recent")}
        async with factory() as db:
            db.add_all(
                [
                    SessionModel(session_id=ids["old_active"], is_active=True, last_accessed_at=old),
                    SessionModel(session_id=ids["old_inactive"], is_active=False, last_accessed_at=old),
                    SessionModel(session_id=ids["recent"], is_active=True),
                ]
            )
            await db.flush()
            db.add_all(
                [
                    MessageModel(session_id=session_id, message_type="human", content="chest pain")
                    for session_id in ids.values()
                ]
            )
            await db.commit()

            await SessionRepository(db).delete_old_sessions(30)

            sessions_left = set(
                (await db.execute(select(SessionModel.session_id).where(SessionModel.session_id.in_(ids.values()))))
                .scalars()
                .all()
            )
            messages_left = set(
                (await db.execute(select(MessageModel.session_id).where(MessageModel.session_id.in_(ids.values()))))
                .scalars()
                .all()
            )
            await db.execute(MessageModel.__table__.delete().where(MessageModel.session_id == ids["recent"]))
            await db.execute(SessionModel.__table__.delete().where(SessionModel.session_id == ids["recent"]))
            await db.commit()
        await engine.dispose()
        return sessions_left, messages_left, ids

    sessions_left, messages_left, ids = asyncio.run(scenario())
    assert sessions_left == {ids["recent"]}
    assert messages_left == {ids["recent"]}
