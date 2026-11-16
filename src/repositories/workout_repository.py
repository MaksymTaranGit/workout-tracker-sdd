"""
Шар доступу до даних (Repository Layer) для SQLite.

Повністю реалізує операції всіх чотирьох блоків SDD/TDD: ініціалізацію схеми БД,
управління профілем користувача, каталогом вправ (включно з оновленням `rm_model`),
тренувальними сесіями, ізольованими блоками вправ, підходами та хронологічною вибіркою аналітики.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src.core.logger import TRACE_LEVEL_NUM, log_event

DEFAULT_USER_ID = "018f3a10-0000-7000-8000-000000000001"
DEFAULT_BODY_WEIGHT = 80.0


def _utc_now_iso() -> str:
    """Повертає поточний час UTC у форматі ISO-8601 із суфіксом `Z`."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _new_id(prefix: str) -> str:
    """Генерує унікальний ідентифікатор сутності з префіксом."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _row_to_profile(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "current_body_weight": float(row["current_body_weight"]),
        "unit": row["unit"],
        "updated_at": row["updated_at"],
    }


def _row_to_exercise(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "exercise_id": row["exercise_id"],
        "name": row["name"],
        "exercise_type": row["exercise_type"],
        "rm_model": row["rm_model"],
        "is_archived": bool(row["is_archived"]),
        "archived_at": row["archived_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_set(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "set_id": row["set_id"],
        "block_id": row["block_id"],
        "set_number": int(row["set_number"]),
        "weight": float(row["weight"]),
        "reps": int(row["reps"]),
        "rpe": float(row["rpe"]),
        "is_warmup": bool(row["is_warmup"]),
        "created_at": row["created_at"],
    }


def _row_to_block(
    row: sqlite3.Row,
    sets: list[dict[str, Any]],
    body_weight_snapshot: float | None = None,
) -> dict[str, Any]:
    resolved_snapshot = (
        float(body_weight_snapshot)
        if body_weight_snapshot is not None
        else float(row["body_weight_snapshot"])
    )
    return {
        "block_id": row["block_id"],
        "session_id": row["session_id"],
        "exercise_id": row["exercise_id"],
        "exercise_name": row["exercise_name"],
        "exercise_type": row["exercise_type"],
        "rm_model": row["rm_model"],
        "order_index": int(row["order_index"]),
        "body_weight_snapshot": resolved_snapshot,
        "created_at": row["created_at"],
        "sets": sets,
    }


class WorkoutRepository:
    """Репозиторій для роботи з таблицями профілю, вправ, сесій, блоків та підходів у SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _ensure_exercises_archiving_columns(self) -> None:
        """Безпечно додає стовпці `is_archived` та `archived_at` у вже існуючу таблицю `exercises`."""
        cols = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(exercises);").fetchall()
        }
        migrated = False
        if "is_archived" not in cols:
            self.conn.execute(
                "ALTER TABLE exercises ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0;"
            )
            migrated = True
        if "archived_at" not in cols:
            self.conn.execute("ALTER TABLE exercises ADD COLUMN archived_at TEXT;")
            migrated = True
        if migrated:
            self.conn.commit()

    def init_schema(self) -> None:
        """Створює таблиці БД за відсутності та ініціалізує дефолтний профіль користувача."""
        self.conn.execute("PRAGMA foreign_keys = ON;")
        tables_row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('user_profile', 'exercises', 'workout_sessions', 'exercise_blocks', 'workout_sets');
            """
        ).fetchone()
        if tables_row is not None and int(tables_row["cnt"]) == 5:
            self._ensure_exercises_archiving_columns()
            has_profile = self.conn.execute(
                "SELECT 1 FROM user_profile LIMIT 1;"
            ).fetchone()
            if has_profile is not None:
                return

        log_event(
            TRACE_LEVEL_NUM,
            "DB",
            "init_schema",
            "Initializing SQLite schema and default user profile if needed",
        )
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN;")

        for ddl in (
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id TEXT PRIMARY KEY,
                current_body_weight REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT 'kg',
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS exercises (
                exercise_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                exercise_type TEXT NOT NULL,
                rm_model TEXT NOT NULL DEFAULT 'EPLEY',
                is_archived INTEGER NOT NULL DEFAULT 0,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_exercises_active_name
            ON exercises(name) WHERE is_archived = 0;
            """,
            """
            CREATE TABLE IF NOT EXISTS workout_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                body_weight_snapshot REAL NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS exercise_blocks (
                block_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES workout_sessions(session_id) ON DELETE CASCADE,
                exercise_id TEXT NOT NULL REFERENCES exercises(exercise_id),
                order_index INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS workout_sets (
                set_id TEXT PRIMARY KEY,
                block_id TEXT NOT NULL REFERENCES exercise_blocks(block_id) ON DELETE CASCADE,
                set_number INTEGER NOT NULL,
                weight REAL NOT NULL,
                reps INTEGER NOT NULL,
                rpe REAL NOT NULL,
                is_warmup INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """,
        ):
            self.conn.execute(ddl)

        count_row = self.conn.execute("SELECT COUNT(*) AS cnt FROM user_profile;").fetchone()
        if count_row is not None and int(count_row["cnt"]) == 0:
            self.conn.execute(
                """
                INSERT INTO user_profile (user_id, current_body_weight, unit, updated_at)
                VALUES (?, ?, 'kg', ?);
                """,
                (DEFAULT_USER_ID, DEFAULT_BODY_WEIGHT, _utc_now_iso()),
            )
        self.conn.commit()

    def get_profile(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT user_id, current_body_weight, unit, updated_at
            FROM user_profile
            ORDER BY updated_at DESC
            LIMIT 1;
            """
        ).fetchone()
        return _row_to_profile(row) if row is not None else None

    def upsert_profile(self, current_body_weight: float) -> dict[str, Any]:
        now = _utc_now_iso()
        existing = self.get_profile()
        target_user_id = existing["user_id"] if existing is not None else DEFAULT_USER_ID

        self.conn.execute(
            """
            INSERT INTO user_profile (user_id, current_body_weight, unit, updated_at)
            VALUES (?, ?, 'kg', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                current_body_weight = excluded.current_body_weight,
                updated_at = excluded.updated_at;
            """,
            (target_user_id, float(current_body_weight), now),
        )
        self.conn.commit()

        updated = self.conn.execute(
            """
            SELECT user_id, current_body_weight, unit, updated_at
            FROM user_profile
            WHERE user_id = ?;
            """,
            (target_user_id,),
        ).fetchone()
        assert updated is not None
        return _row_to_profile(updated)

    _EXERCISE_COLUMNS = (
        "exercise_id, name, exercise_type, rm_model, "
        "is_archived, archived_at, created_at, updated_at"
    )

    def get_exercise_by_name(self, name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"""
            SELECT {self._EXERCISE_COLUMNS}
            FROM exercises
            WHERE name = ? AND is_archived = 0;
            """,
            (name,),
        ).fetchone()
        return _row_to_exercise(row) if row is not None else None

    def create_exercise(
        self, name: str, exercise_type: str, rm_model: str = "EPLEY"
    ) -> dict[str, Any]:
        exercise_id = _new_id("ex")
        created_at = _utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO exercises (
                exercise_id, name, exercise_type, rm_model,
                is_archived, archived_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 0, NULL, ?, NULL);
            """,
            (exercise_id, name, exercise_type, rm_model, created_at),
        )
        self.conn.commit()

        created = self.get_exercise_by_id(exercise_id)
        assert created is not None
        return created

    def list_exercises(self, exercise_type: str | None = None) -> list[dict[str, Any]]:
        if exercise_type is not None:
            rows = self.conn.execute(
                f"""
                SELECT {self._EXERCISE_COLUMNS}
                FROM exercises
                WHERE exercise_type = ? AND is_archived = 0
                ORDER BY created_at ASC, rowid ASC;
                """,
                (exercise_type,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"""
                SELECT {self._EXERCISE_COLUMNS}
                FROM exercises
                WHERE is_archived = 0
                ORDER BY created_at ASC, rowid ASC;
                """
            ).fetchall()
        return [_row_to_exercise(row) for row in rows]

    def get_exercise_by_id(self, exercise_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"""
            SELECT {self._EXERCISE_COLUMNS}
            FROM exercises
            WHERE exercise_id = ?;
            """,
            (exercise_id,),
        ).fetchone()
        return _row_to_exercise(row) if row is not None else None

    def update_exercise_model(self, exercise_id: str, rm_model: str) -> dict[str, Any] | None:
        if self.get_exercise_by_id(exercise_id) is None:
            return None
        updated_at = _utc_now_iso()
        self.conn.execute(
            """
            UPDATE exercises
            SET rm_model = ?, updated_at = ?
            WHERE exercise_id = ?;
            """,
            (rm_model, updated_at, exercise_id),
        )
        self.conn.commit()
        return self.get_exercise_by_id(exercise_id)

    def archive_exercise(self, exercise_id: str) -> dict[str, Any] | None:
        """Позначає вправу як архівовану (Soft Delete); повертає None, якщо не знайдено або вже архівовано."""
        existing = self.get_exercise_by_id(exercise_id)
        if existing is None or existing["is_archived"]:
            return None
        now = _utc_now_iso()
        self.conn.execute(
            """
            UPDATE exercises
            SET is_archived = 1, archived_at = ?, updated_at = ?
            WHERE exercise_id = ?;
            """,
            (now, now, exercise_id),
        )
        self.conn.commit()
        return self.get_exercise_by_id(exercise_id)

    def create_session(
        self,
        body_weight_snapshot: float,
        started_at: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        session_id = _new_id("ses")
        created_at = _utc_now_iso()
        resolved_started_at = started_at or created_at
        self.conn.execute(
            """
            INSERT INTO workout_sessions (
                session_id, started_at, body_weight_snapshot, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                session_id,
                resolved_started_at,
                float(body_weight_snapshot),
                notes,
                created_at,
            ),
        )
        self.conn.commit()
        return {
            "session_id": session_id,
            "started_at": resolved_started_at,
            "body_weight_snapshot": float(body_weight_snapshot),
            "notes": notes,
            "blocks": [],
        }

    def list_sessions(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        total_row = self.conn.execute(
            "SELECT COUNT(*) AS total FROM workout_sessions;"
        ).fetchone()
        total = int(total_row["total"]) if total_row is not None else 0

        rows = self.conn.execute(
            """
            SELECT
                s.session_id,
                s.started_at,
                s.body_weight_snapshot,
                s.notes,
                COUNT(eb.block_id) AS blocks_count
            FROM workout_sessions s
            LEFT JOIN exercise_blocks eb ON eb.session_id = s.session_id
            GROUP BY s.session_id
            ORDER BY s.started_at DESC, s.rowid DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
        ).fetchall()

        items = [
            {
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "body_weight_snapshot": float(row["body_weight_snapshot"]),
                "notes": row["notes"],
                "blocks_count": int(row["blocks_count"]),
            }
            for row in rows
        ]
        return items, total

    def _fetch_sets_for_block(self, block_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT set_id, block_id, set_number, weight, reps, rpe, is_warmup, created_at
            FROM workout_sets
            WHERE block_id = ?
            ORDER BY set_number ASC, rowid ASC;
            """,
            (block_id,),
        ).fetchall()
        return [_row_to_set(row) for row in rows]

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        session_row = self.conn.execute(
            """
            SELECT session_id, started_at, body_weight_snapshot, notes
            FROM workout_sessions
            WHERE session_id = ?;
            """,
            (session_id,),
        ).fetchone()
        if session_row is None:
            return None

        block_rows = self.conn.execute(
            """
            SELECT
                eb.block_id,
                eb.session_id,
                eb.exercise_id,
                eb.order_index,
                eb.created_at,
                e.name AS exercise_name,
                e.exercise_type,
                e.rm_model
            FROM exercise_blocks eb
            INNER JOIN exercises e ON e.exercise_id = eb.exercise_id
            WHERE eb.session_id = ?
            ORDER BY eb.order_index ASC, eb.rowid ASC;
            """,
            (session_id,),
        ).fetchall()

        sets_by_block: dict[str, list[dict[str, Any]]] = {}
        if block_rows:
            set_rows = self.conn.execute(
                """
                SELECT ws.set_id, ws.block_id, ws.set_number, ws.weight, ws.reps, ws.rpe, ws.is_warmup, ws.created_at
                FROM workout_sets ws
                INNER JOIN exercise_blocks eb ON eb.block_id = ws.block_id
                WHERE eb.session_id = ?
                ORDER BY ws.set_number ASC, ws.rowid ASC;
                """,
                (session_id,),
            ).fetchall()
            for set_row in set_rows:
                sets_by_block.setdefault(set_row["block_id"], []).append(_row_to_set(set_row))

        snapshot = float(session_row["body_weight_snapshot"])
        blocks = [
            _row_to_block(
                b_row,
                sets_by_block.get(b_row["block_id"], []),
                body_weight_snapshot=snapshot,
            )
            for b_row in block_rows
        ]
        return {
            "session_id": session_row["session_id"],
            "started_at": session_row["started_at"],
            "body_weight_snapshot": snapshot,
            "notes": session_row["notes"],
            "blocks": blocks,
        }

    def create_exercise_block(self, session_id: str, exercise_id: str) -> dict[str, Any]:
        order_row = self.conn.execute(
            """
            SELECT COALESCE(MAX(order_index), 0) + 1 AS next_order
            FROM exercise_blocks
            WHERE session_id = ?;
            """,
            (session_id,),
        ).fetchone()
        next_order = int(order_row["next_order"]) if order_row is not None else 1

        block_id = _new_id("blk")
        created_at = _utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO exercise_blocks (block_id, session_id, exercise_id, order_index, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (block_id, session_id, exercise_id, next_order, created_at),
        )
        self.conn.commit()

        created = self.get_exercise_block_by_id(session_id, block_id)
        assert created is not None
        return created

    def get_exercise_block_by_id(
        self, session_id: str, block_id: str
    ) -> dict[str, Any] | None:
        block_row = self.conn.execute(
            """
            SELECT
                eb.block_id,
                eb.session_id,
                eb.exercise_id,
                eb.order_index,
                eb.created_at,
                e.name AS exercise_name,
                e.exercise_type,
                e.rm_model,
                ws_ses.body_weight_snapshot
            FROM exercise_blocks eb
            INNER JOIN exercises e ON e.exercise_id = eb.exercise_id
            INNER JOIN workout_sessions ws_ses ON ws_ses.session_id = eb.session_id
            WHERE eb.session_id = ? AND eb.block_id = ?;
            """,
            (session_id, block_id),
        ).fetchone()
        if block_row is None:
            return None

        sets = self._fetch_sets_for_block(block_id)
        return _row_to_block(block_row, sets)

    def create_workout_set(
        self,
        session_id: str,
        block_id: str,
        weight: float,
        reps: int,
        rpe: float,
        is_warmup: bool,
    ) -> dict[str, Any]:
        set_num_row = self.conn.execute(
            """
            SELECT COALESCE(MAX(set_number), 0) + 1 AS next_set_number
            FROM workout_sets
            WHERE block_id = ?;
            """,
            (block_id,),
        ).fetchone()
        next_set_number = int(set_num_row["next_set_number"]) if set_num_row is not None else 1

        set_id = _new_id("set")
        created_at = _utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO workout_sets (
                set_id, block_id, set_number, weight, reps, rpe, is_warmup, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                set_id,
                block_id,
                next_set_number,
                float(weight),
                int(reps),
                float(rpe),
                1 if is_warmup else 0,
                created_at,
            ),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT set_id, block_id, set_number, weight, reps, rpe, is_warmup, created_at
            FROM workout_sets
            WHERE set_id = ?;
            """,
            (set_id,),
        ).fetchone()
        assert row is not None
        return _row_to_set(row)

    def delete_workout_set(
        self, session_id: str, block_id: str, set_id: str
    ) -> dict[str, Any] | None:
        existing_row = self.conn.execute(
            """
            SELECT ws.set_id, ws.block_id, ws.set_number, ws.weight, ws.reps, ws.rpe, ws.is_warmup, ws.created_at
            FROM workout_sets ws
            INNER JOIN exercise_blocks eb ON eb.block_id = ws.block_id
            WHERE eb.session_id = ? AND ws.block_id = ? AND ws.set_id = ?;
            """,
            (session_id, block_id, set_id),
        ).fetchone()
        if existing_row is None:
            return None

        self.conn.execute(
            "DELETE FROM workout_sets WHERE set_id = ? AND block_id = ?;",
            (set_id, block_id),
        )
        self.conn.commit()
        return _row_to_set(existing_row)

    def get_exercise_analytics(self, exercise_id: str) -> list[dict[str, Any]]:
        """
        Повертає всі блоки вправи з щонайменше одним робочим підходом (`is_warmup = 0`)
        у суворому хронологічному порядку `(started_at ASC, order_index ASC, rowid ASC)`.
        """
        block_rows = self.conn.execute(
            """
            SELECT
                eb.block_id,
                eb.session_id,
                eb.exercise_id,
                eb.order_index,
                eb.created_at,
                e.name AS exercise_name,
                e.exercise_type,
                e.rm_model,
                ws_ses.started_at,
                ws_ses.body_weight_snapshot
            FROM exercise_blocks eb
            INNER JOIN exercises e ON e.exercise_id = eb.exercise_id
            INNER JOIN workout_sessions ws_ses ON ws_ses.session_id = eb.session_id
            WHERE eb.exercise_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM workout_sets ws
                  WHERE ws.block_id = eb.block_id AND ws.is_warmup = 0
              )
            ORDER BY ws_ses.started_at ASC, eb.order_index ASC, eb.rowid ASC;
            """,
            (exercise_id,),
        ).fetchall()

        if not block_rows:
            return []

        set_rows = self.conn.execute(
            """
            SELECT ws.set_id, ws.block_id, ws.set_number, ws.weight, ws.reps, ws.rpe, ws.is_warmup, ws.created_at
            FROM workout_sets ws
            INNER JOIN exercise_blocks eb ON eb.block_id = ws.block_id
            WHERE eb.exercise_id = ?
            ORDER BY ws.set_number ASC, ws.rowid ASC;
            """,
            (exercise_id,),
        ).fetchall()

        sets_by_block: dict[str, list[dict[str, Any]]] = {}
        for set_row in set_rows:
            sets_by_block.setdefault(set_row["block_id"], []).append(_row_to_set(set_row))

        result: list[dict[str, Any]] = []
        for b_row in block_rows:
            block_dict = _row_to_block(b_row, sets_by_block.get(b_row["block_id"], []))
            block_dict["started_at"] = b_row["started_at"]
            result.append(block_dict)
        return result
