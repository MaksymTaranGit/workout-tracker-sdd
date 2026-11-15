"""
Шар доступу до даних (Repository Layer) для SQLite.

ВАЖЛИВО (SDD / TDD Red Phase Skeleton):
Жодна бізнес-логіка чи SQL-імплементація не реалізується до затвердження тестів на TEST-GATE.
Усі методи є суворими заглушками, що піднімають `NotImplementedError`.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class WorkoutRepository:
    """Каркас репозиторію для роботи з таблицями профілю, вправ, сесій, блоків та підходів."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def init_schema(self) -> None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def get_profile(self) -> dict[str, Any] | None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def upsert_profile(self, current_body_weight: float) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def create_exercise(self, name: str, exercise_type: str, rm_model: str) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def list_exercises(self, exercise_type: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def get_exercise_by_id(self, exercise_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def update_exercise_model(self, exercise_id: str, rm_model: str) -> dict[str, Any] | None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def create_session(
        self,
        body_weight_snapshot: float,
        started_at: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def list_sessions(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def create_exercise_block(self, session_id: str, exercise_id: str) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def get_exercise_block_by_id(
        self, session_id: str, block_id: str
    ) -> dict[str, Any] | None:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def create_workout_set(
        self,
        session_id: str,
        block_id: str,
        weight: float,
        reps: int,
        rpe: float,
        is_warmup: bool,
    ) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def delete_workout_set(
        self, session_id: str, block_id: str, set_id: str
    ) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")

    def get_exercise_analytics(self, exercise_id: str) -> dict[str, Any]:
        raise NotImplementedError("TDD Red Phase: repository method not implemented")
