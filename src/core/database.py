"""
Модуль підключення до реляційної СКБД SQLite (`sqlite3`) із підтримкою:
1. Автоматичного логування всіх SQL-операцій на рівні TRACE (REQ-NF-009).
2. Підміни шляху до файлу БД через FastAPI Dependency Injection (`Depends`) або
   змінну оточення `WORKOUT_TRACKER_DB_PATH` для повної ізоляції тестових запусків `pytest`.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends

from src.core.logger import PROJECT_ROOT, TRACE_LEVEL_NUM, log_event

DEFAULT_DB_PATH = PROJECT_ROOT / "workout_tracker.db"


def get_db_path() -> str:
    """
    Повертає шлях до файлу бази даних SQLite.
    Може бути перевизначений через `app.dependency_overrides[get_db_path]` у фікстурах `pytest`
    або через змінну середовища `WORKOUT_TRACKER_DB_PATH`.
    """
    env_path = os.getenv("WORKOUT_TRACKER_DB_PATH")
    if env_path:
        return env_path
    return str(DEFAULT_DB_PATH)


def create_sqlite_connection(db_path: str | Path) -> sqlite3.Connection:
    """
    Створює підключення до SQLite з увімкненим контролем зовнішніх ключів (`PRAGMA foreign_keys = ON`)
    та реєструє trace-callback для запису кожного SQL-виразу в `logs/system-execution.log` на рівні TRACE.
    """
    resolved_path = str(db_path)
    conn = sqlite3.connect(resolved_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    def _sql_trace_callback(statement: str) -> None:
        log_event(
            TRACE_LEVEL_NUM,
            "DB",
            "SQL_TRACE",
            "Executing SQL statement",
            context={"sql": statement, "db_path": resolved_path},
        )

    conn.set_trace_callback(_sql_trace_callback)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_db(
    db_path: str = Depends(get_db_path),
) -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI Dependency для отримання сесійного підключення до SQLite.
    Гарантує закриття з'єднання після завершення обробки HTTP-запиту.
    """
    log_event(
        TRACE_LEVEL_NUM,
        "DB",
        "DB_CONNECT_OPEN",
        "Opening SQLite database connection",
        context={"db_path": db_path},
    )
    conn = create_sqlite_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
        log_event(
            TRACE_LEVEL_NUM,
            "DB",
            "DB_CONNECT_CLOSE",
            "Closed SQLite database connection",
            context={"db_path": db_path},
        )
