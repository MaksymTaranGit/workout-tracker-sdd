"""
Маршрутизатор REST API (`/api/v1`) із оголошенням і повною реалізацією всіх 14 операцій зі `spec/openapi.yaml`.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query, Request

from src.core.database import get_db
from src.core.logger import TRACE_LEVEL_NUM, get_trace_id, log_event
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
from src.services.workout_service import WorkoutService

router = APIRouter(prefix="/api/v1")


def get_workout_service(
    db: sqlite3.Connection = Depends(get_db),
) -> WorkoutService:
    """Фабрика залежності `WorkoutService` із ініціалізованою БД SQLite."""
    return WorkoutService(WorkoutRepository(db))


def _log_api_operation(
    request: Request,
    operation_id: str,
    context: dict[str, Any] | None = None,
) -> str:
    """Логує вхід в операцію API на рівні TRACE та повертає `trace_id`."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    log_context = {
        "method": request.method,
        "path": request.url.path,
        "operation_id": operation_id,
        **(context or {}),
    }
    log_event(
        TRACE_LEVEL_NUM,
        "API",
        operation_id,
        f"Invoking API operation '{operation_id}'",
        context=log_context,
        trace_id=trace_id,
    )
    return trace_id


# =====================================================================
# 1. PROFILE (/api/v1/profile) — REQ-F-002, REQ-F-019, BDD-001
# =====================================================================


@router.get(
    "/profile",
    operation_id="getUserProfile",
    tags=["Profile"],
    response_model=UserProfile,
    summary="Отримання профілю користувача (REQ-F-002, REQ-F-019)",
)
def get_user_profile(
    request: Request,
    service: WorkoutService = Depends(get_workout_service),
) -> UserProfile:
    _log_api_operation(request, "getUserProfile")
    return service.get_user_profile()


@router.put(
    "/profile",
    operation_id="updateUserProfile",
    tags=["Profile"],
    response_model=UserProfile,
    summary="Оновлення поточної маси тіла в профілі (REQ-F-019, BDD-001)",
)
def update_user_profile(
    request: Request,
    payload: UpdateUserProfileRequest,
    service: WorkoutService = Depends(get_workout_service),
) -> UserProfile:
    _log_api_operation(
        request,
        "updateUserProfile",
        context={"payload": payload.model_dump(mode="json")},
    )
    return service.update_user_profile(payload)


# =====================================================================
# 2. EXERCISES (/api/v1/exercises) — REQ-F-012, REQ-F-013, REQ-F-020
# =====================================================================


@router.post(
    "/exercises",
    operation_id="createExercise",
    tags=["Exercises"],
    status_code=201,
    response_model=Exercise,
    summary="Створення нової вправи в довіднику (REQ-F-012, REQ-F-013, REQ-F-020)",
)
def create_exercise(
    request: Request,
    payload: CreateExerciseRequest,
    service: WorkoutService = Depends(get_workout_service),
) -> Exercise:
    _log_api_operation(
        request,
        "createExercise",
        context={"payload": payload.model_dump(mode="json")},
    )
    return service.create_exercise(payload)


@router.get(
    "/exercises",
    operation_id="listExercises",
    tags=["Exercises"],
    response_model=ExerciseListResponse,
    summary="Отримання списку вправ довідника (REQ-F-020)",
)
def list_exercises(
    request: Request,
    exercise_type: ExerciseType | None = Query(
        default=None,
        description="Фільтр за біомеханічним типом вправи",
    ),
    service: WorkoutService = Depends(get_workout_service),
) -> ExerciseListResponse:
    _log_api_operation(
        request,
        "listExercises",
        context={"exercise_type": exercise_type.value if exercise_type else None},
    )
    return service.list_exercises(exercise_type=exercise_type)


@router.get(
    "/exercises/{exerciseId}",
    operation_id="getExerciseById",
    tags=["Exercises"],
    response_model=Exercise,
    summary="Отримання деталей та конфігурації конкретної вправи (REQ-F-012, REQ-F-020)",
)
def get_exercise_by_id(
    request: Request,
    exercise_id: str = Path(..., alias="exerciseId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> Exercise:
    _log_api_operation(
        request,
        "getExerciseById",
        context={"exerciseId": exercise_id},
    )
    return service.get_exercise_by_id(exercise_id)


@router.patch(
    "/exercises/{exerciseId}",
    operation_id="updateExerciseModel",
    tags=["Exercises"],
    response_model=Exercise,
    summary="Налаштування математичної моделі 1RM для вправи (REQ-F-012, BDD-006)",
)
def update_exercise_model(
    request: Request,
    payload: UpdateExerciseModelRequest,
    exercise_id: str = Path(..., alias="exerciseId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> Exercise:
    _log_api_operation(
        request,
        "updateExerciseModel",
        context={
            "exerciseId": exercise_id,
            "payload": payload.model_dump(mode="json"),
        },
    )
    return service.update_exercise_model(exercise_id, payload)


# =====================================================================
# 3. SESSIONS (/api/v1/sessions) — REQ-F-001, REQ-F-002, BDD-001
# =====================================================================


@router.post(
    "/sessions",
    operation_id="createSession",
    tags=["Sessions"],
    status_code=201,
    response_model=WorkoutSession,
    summary="Створення нової тренувальної сесії зі снапшотом ваги (REQ-F-001, REQ-F-002, BDD-001)",
)
def create_session(
    request: Request,
    payload: CreateSessionRequest | None = Body(default=None),
    service: WorkoutService = Depends(get_workout_service),
) -> WorkoutSession:
    _log_api_operation(
        request,
        "createSession",
        context={"payload": payload.model_dump(mode="json") if payload else {}},
    )
    return service.create_session(payload)


@router.get(
    "/sessions",
    operation_id="listSessions",
    tags=["Sessions"],
    response_model=SessionListResponse,
    summary="Отримання списку тренувальних сесій (REQ-F-001)",
)
def list_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: WorkoutService = Depends(get_workout_service),
) -> SessionListResponse:
    _log_api_operation(
        request,
        "listSessions",
        context={"limit": limit, "offset": offset},
    )
    return service.list_sessions(limit=limit, offset=offset)


@router.get(
    "/sessions/{sessionId}",
    operation_id="getSessionById",
    tags=["Sessions"],
    response_model=WorkoutSession,
    summary="Отримання детального стану сесії з усіма блоками та підходами (REQ-F-001 – REQ-F-016)",
)
def get_session_by_id(
    request: Request,
    session_id: str = Path(..., alias="sessionId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> WorkoutSession:
    _log_api_operation(
        request,
        "getSessionById",
        context={"sessionId": session_id},
    )
    return service.get_session_by_id(session_id)


# =====================================================================
# 4. EXERCISE BLOCKS (/api/v1/sessions/{sessionId}/blocks) — REQ-F-003, REQ-F-006
# =====================================================================


@router.post(
    "/sessions/{sessionId}/blocks",
    operation_id="createExerciseBlock",
    tags=["ExerciseBlocks"],
    status_code=201,
    response_model=ExerciseBlock,
    summary="Додавання нового ізольованого блоку вправи до сесії (REQ-F-003, REQ-F-006, RSK-09)",
)
def create_exercise_block(
    request: Request,
    payload: CreateExerciseBlockRequest,
    session_id: str = Path(..., alias="sessionId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> ExerciseBlock:
    _log_api_operation(
        request,
        "createExerciseBlock",
        context={
            "sessionId": session_id,
            "payload": payload.model_dump(mode="json"),
        },
    )
    return service.create_exercise_block(session_id, payload)


@router.get(
    "/sessions/{sessionId}/blocks/{blockId}",
    operation_id="getExerciseBlockById",
    tags=["ExerciseBlocks"],
    response_model=ExerciseBlock,
    summary="Отримання даних конкретного блоку вправи, його об'єму та Дельти (REQ-F-006, REQ-F-015, REQ-F-016)",
)
def get_exercise_block_by_id(
    request: Request,
    session_id: str = Path(..., alias="sessionId", min_length=1),
    block_id: str = Path(..., alias="blockId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> ExerciseBlock:
    _log_api_operation(
        request,
        "getExerciseBlockById",
        context={"sessionId": session_id, "blockId": block_id},
    )
    return service.get_exercise_block_by_id(session_id, block_id)


# =====================================================================
# 5. WORKOUT SETS (/api/v1/sessions/{sessionId}/blocks/{blockId}/sets)
# =====================================================================


@router.post(
    "/sessions/{sessionId}/blocks/{blockId}/sets",
    operation_id="createWorkoutSet",
    tags=["WorkoutSets"],
    status_code=201,
    response_model=CreateWorkoutSetResponse,
    summary="Запис (Auto-Save) підходу з миттєвим обчисленням Volume Load, 1RM та Дельти (REQ-F-004 – REQ-F-011, REQ-F-014)",
)
def create_workout_set(
    request: Request,
    payload: CreateWorkoutSetRequest,
    session_id: str = Path(..., alias="sessionId", min_length=1),
    block_id: str = Path(..., alias="blockId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> CreateWorkoutSetResponse:
    _log_api_operation(
        request,
        "createWorkoutSet",
        context={
            "sessionId": session_id,
            "blockId": block_id,
            "payload": payload.model_dump(mode="json"),
        },
    )
    return service.create_workout_set(session_id, block_id, payload)


@router.delete(
    "/sessions/{sessionId}/blocks/{blockId}/sets/{setId}",
    operation_id="deleteWorkoutSet",
    tags=["WorkoutSets"],
    response_model=DeleteWorkoutSetResponse,
    summary="Видалення помилково введеного підходу з перерахунком блоку (REQ-F-004, REQ-F-006)",
)
def delete_workout_set(
    request: Request,
    session_id: str = Path(..., alias="sessionId", min_length=1),
    block_id: str = Path(..., alias="blockId", min_length=1),
    set_id: str = Path(..., alias="setId", min_length=1),
    service: WorkoutService = Depends(get_workout_service),
) -> DeleteWorkoutSetResponse:
    _log_api_operation(
        request,
        "deleteWorkoutSet",
        context={"sessionId": session_id, "blockId": block_id, "setId": set_id},
    )
    return service.delete_workout_set(session_id, block_id, set_id)


# =====================================================================
# 6. ANALYTICS (/api/v1/exercises/{exerciseId}/analytics) — REQ-F-015..018
# =====================================================================


@router.get(
    "/exercises/{exerciseId}/analytics",
    operation_id="getExerciseAnalytics",
    tags=["Analytics"],
    response_model=ExerciseAnalyticsResponse,
    summary="Отримання даних візуального дашборду прогресії Volume Load, 1RM та Дельти (REQ-F-015 – REQ-F-018)",
)
def get_exercise_analytics(
    request: Request,
    exercise_id: str = Path(..., alias="exerciseId", min_length=1),
    from_date: str | None = Query(
        default=None,
        description="Початкова дата вибірки (ISO 8601, наприклад YYYY-MM-DD)",
    ),
    to_date: str | None = Query(
        default=None,
        description="Кінцева дата вибірки (ISO 8601, наприклад YYYY-MM-DD)",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Максимальна кількість історичних точок для графіка",
    ),
    service: WorkoutService = Depends(get_workout_service),
) -> ExerciseAnalyticsResponse:
    _log_api_operation(
        request,
        "getExerciseAnalytics",
        context={
            "exerciseId": exercise_id,
            "from_date": from_date,
            "to_date": to_date,
            "limit": limit,
        },
    )
    return service.get_exercise_analytics(
        exercise_id=exercise_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
