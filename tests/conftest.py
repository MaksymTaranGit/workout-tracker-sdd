"""
Глобальні фікстури та конфігурація pytest для тестування за методологіями SDD та TDD.

Забезпечує:
1. Автоочищення `logs/system-execution.log` перед початком кожного прогону pytest (`pytest_sessionstart`).
2. Повну ізоляцію бази даних SQLite через `tmp_path` та `app.dependency_overrides[get_db_path]`.
3. Трасування життєвого циклу кожного тесту з `component="TEST_RUNNER"` на рівні `TRACE`.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.database import get_db_path
from src.core.logger import (
    LOG_DIR,
    LOG_FILE_PATH,
    TRACE_LEVEL_NUM,
    app_logger,
    generate_trace_id,
    log_event,
)
from src.main import app


def _truncate_execution_log() -> None:
    """
    Безпечно очищує `logs/system-execution.log` без перевідкриття відкритого FileHandler
    (запобігає появі NUL-байтів у Windows при активному потоці журналювання).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    truncated_via_handler = False
    for handler in app_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            base_filename = Path(handler.baseFilename).resolve()
            if base_filename == LOG_FILE_PATH.resolve():
                handler.acquire()
                try:
                    if handler.stream is not None and not handler.stream.closed:
                        handler.stream.seek(0)
                        handler.stream.truncate(0)
                        handler.stream.flush()
                        truncated_via_handler = True
                finally:
                    handler.release()
    if not truncated_via_handler:
        LOG_FILE_PATH.write_text("", encoding="utf-8")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Очищує `logs/system-execution.log` на початку кожної тестової сесії."""
    _truncate_execution_log()
    log_event(
        logging.INFO,
        "TEST_RUNNER",
        "PYTEST_SESSION_START",
        "Truncated system-execution.log and started pytest test session",
        context={"rootdir": str(session.config.rootpath)},
        trace_id="trc-pytest-session",
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Повертає шлях до ізольованої тимчасової бази даних SQLite для одного тесту."""
    return tmp_path / "test_workout.db"


@pytest.fixture
def client(db_path: Path, request: pytest.FixtureRequest) -> Generator[TestClient, None, None]:
    """
    Повертає ізольований FastAPI TestClient із підміненим шляхом до тимчасової БД SQLite
    та автоматичним логуванням старту/завершення тесту.
    """
    test_trace_id = generate_trace_id("tst")
    app.dependency_overrides[get_db_path] = lambda: str(db_path)

    log_event(
        TRACE_LEVEL_NUM,
        "TEST_RUNNER",
        "TEST_START",
        f"Starting test '{request.node.nodeid}'",
        context={"test_name": request.node.name, "db_path": str(db_path)},
        trace_id=test_trace_id,
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        log_event(
            TRACE_LEVEL_NUM,
            "TEST_RUNNER",
            "TEST_END",
            f"Finished test '{request.node.nodeid}'",
            context={"test_name": request.node.name},
            trace_id=test_trace_id,
        )
