"""
Каркас сервісного шару (Service Layer) для координації репозиторіїв та математичного ядра.

ВАЖЛИВО (SDD / TDD Red Phase Skeleton):
Жодна бізнес-логіка не реалізується до затвердження тестів на TEST-GATE.
Усі методи є суворими заглушками, що піднімають `NotImplementedError`.
"""

from __future__ import annotations

from src.domain.schemas import (
    CreateExerciseBlockRequest,
    CreateExerciseRequest,
    CreateSessionRequest,
    CreateWorkoutSetRequest,
    CreateWorkoutSetResponse,
    DeleteWorkoutSetResponse,
    Exercise,
    ExerciseAnalyticsResponse,
    ExerciseBlock,
    ExerciseListResponse,
    ExerciseType,
    SessionListResponse,
    UpdateExerciseModelRequest,
    UpdateUserProfileRequest,
    UserProfile,
    WorkoutSession,
)
from src.repositories.workout_repository import WorkoutRepository


class WorkoutService:
    """Заглушка сервісу управління тренуваннями та аналітикою (TDD Red Phase)."""

    def __init__(self, repository: WorkoutRepository) -> None:
        self.repository = repository

    def get_user_profile(self) -> UserProfile:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def update_user_profile(self, payload: UpdateUserProfileRequest) -> UserProfile:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def create_exercise(self, payload: CreateExerciseRequest) -> Exercise:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def list_exercises(self, exercise_type: ExerciseType | None = None) -> ExerciseListResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def get_exercise_by_id(self, exercise_id: str) -> Exercise:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def update_exercise_model(
        self, exercise_id: str, payload: UpdateExerciseModelRequest
    ) -> Exercise:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def create_session(self, payload: CreateSessionRequest | None = None) -> WorkoutSession:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def list_sessions(self, limit: int = 20, offset: int = 0) -> SessionListResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def get_session_by_id(self, session_id: str) -> WorkoutSession:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def create_exercise_block(
        self, session_id: str, payload: CreateExerciseBlockRequest
    ) -> ExerciseBlock:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def get_exercise_block_by_id(
        self, session_id: str, block_id: str
    ) -> ExerciseBlock:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def create_workout_set(
        self, session_id: str, block_id: str, payload: CreateWorkoutSetRequest
    ) -> CreateWorkoutSetResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def delete_workout_set(
        self, session_id: str, block_id: str, set_id: str
    ) -> DeleteWorkoutSetResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def get_exercise_analytics(self, exercise_id: str) -> ExerciseAnalyticsResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")
