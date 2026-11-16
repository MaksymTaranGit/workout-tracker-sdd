"""
Сервісний шар (Service Layer) для координації репозиторіїв, доменної валідації та телеметрії.

Реалізує бізнес-логіку та доменні правила Блоку 1 (`TKT-02`, `TKT-04`):
- управління профілем користувача та обмеженням маси тіла `[30.0, 300.0]` (`REQ-F-019`, `AC10`);
- управління каталогом вправ та унікальністю назв (`REQ-F-020`, `REQ-F-013`, `AC11`);
- створення сесій із незмінним знімком `body_weight_snapshot` (`REQ-F-001`, `REQ-F-002`, `BDD-001`, `RSK-06`);
- управління ізольованими блоками вправ (`REQ-F-003`, `RSK-09`);
- запис і видалення підходів із валідацією RPE та повторень (`REQ-F-004`, `REQ-F-005`, `AC2`, `RSK-02`).

Математичні формули Блоків 2-4 (`MathEngine`) та операції Блоків 3-4 залишаються у фазі RED (`NotImplementedError`).
"""

from __future__ import annotations

import math
from typing import Any

from src.core.errors import AppError, ErrorCode
from src.core.logger import TRACE_LEVEL_NUM, log_event
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
    ExerciseBlockSummary,
    ExerciseListResponse,
    ExerciseType,
    RmModel,
    SessionListResponse,
    UpdateExerciseModelRequest,
    UpdateUserProfileRequest,
    UserProfile,
    WorkoutSession,
    WorkoutSessionSummary,
    WorkoutSet,
)
from src.repositories.workout_repository import WorkoutRepository
from src.services.math_engine import MathEngine

MIN_BODY_WEIGHT_KG = 30.0
MAX_BODY_WEIGHT_KG = 300.0
MIN_RPE = 6.0
MAX_RPE = 10.0
MAX_BRZYCKI_REPS = 36


def _to_exercise_dto(row: dict[str, Any]) -> Exercise:
    return Exercise(
        exercise_id=row["exercise_id"],
        name=row["name"],
        exercise_type=ExerciseType(row["exercise_type"]),
        rm_model=RmModel(row["rm_model"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_workout_set_dto(
    row: dict[str, Any], exercise_type: str, body_weight_snapshot: float
) -> WorkoutSet:
    """Формує DTO підходу з обчисленням W_eff і set_volume_load (Блок 2)."""
    weight = float(row["weight"])
    reps = int(row["reps"])
    is_warmup = bool(row["is_warmup"])

    effective_weight = MathEngine.calculate_effective_weight(
        exercise_type, weight, body_weight_snapshot
    )
    set_volume_load = MathEngine.calculate_set_volume_load(
        effective_weight, reps, is_warmup
    )
    return WorkoutSet(
        set_id=row["set_id"],
        block_id=row["block_id"],
        set_number=int(row["set_number"]),
        weight=weight,
        effective_weight=effective_weight,
        reps=reps,
        rpe=float(row["rpe"]),
        is_warmup=is_warmup,
        set_volume_load=set_volume_load,
        estimated_1rm=None,
        soft_constraint_warning=False,
        warning_message=None,
    )


def _compute_block_sets_and_volume(
    row: dict[str, Any],
) -> tuple[list[WorkoutSet], float]:
    """Обчислює перелік підходів і сумарний Volume Load виключно для одного блоку."""
    exercise_type = row["exercise_type"]
    body_weight_snapshot = float(row["body_weight_snapshot"])
    sets = [
        _to_workout_set_dto(s, exercise_type, body_weight_snapshot)
        for s in row.get("sets", [])
    ]
    block_volume_load = round(sum(s.set_volume_load for s in sets), 2)
    return sets, block_volume_load


def _build_block_summary_dto(block_row: dict[str, Any]) -> ExerciseBlockSummary:
    """Повертає актуальне зведення блоку з розрахованим `block_volume_load`."""
    _, block_volume_load = _compute_block_sets_and_volume(block_row)
    return ExerciseBlockSummary(
        block_id=block_row["block_id"],
        block_volume_load=block_volume_load,
        block_max_1rm=None,
        has_previous_baseline=False,
        volume_load_delta=None,
        max_1rm_delta=None,
    )


def _to_exercise_block_dto(row: dict[str, Any]) -> ExerciseBlock:
    sets, block_volume_load = _compute_block_sets_and_volume(row)
    return ExerciseBlock(
        block_id=row["block_id"],
        session_id=row["session_id"],
        exercise_id=row["exercise_id"],
        exercise_name=row["exercise_name"],
        exercise_type=ExerciseType(row["exercise_type"]),
        rm_model=RmModel(row["rm_model"]),
        order_index=int(row["order_index"]),
        block_volume_load=block_volume_load,
        block_max_1rm=None,
        has_previous_baseline=False,
        volume_load_delta=None,
        max_1rm_delta=None,
        sets=sets,
    )


def _validate_set_weight(
    exercise_type: str, weight: float, body_weight_snapshot: float
) -> None:
    """Перевіряє знак ваги та умову позитивного навантаження (RSK-07, 422)."""
    if not math.isfinite(weight):
        raise AppError(
            ErrorCode.ERR_BAD_REQUEST,
            400,
            "Некоректне числове значення ваги.",
            details={"field": "weight", "value": str(weight)},
        )

    if exercise_type == ExerciseType.STANDARD.value and weight <= 0.0:
        raise AppError(
            ErrorCode.ERR_NEGATIVE_WEIGHT_NOT_ALLOWED,
            422,
            "Для вправи типу STANDARD вага обтяження повинна бути строго додатною (> 0 кг).",
            details={"field": "weight", "exercise_type": exercise_type, "value": weight},
        )

    if exercise_type == ExerciseType.BODYWEIGHT.value and weight < 0.0:
        raise AppError(
            ErrorCode.ERR_NEGATIVE_WEIGHT_NOT_ALLOWED,
            422,
            "Для вправи типу BODYWEIGHT додаткова вага не може бути від'ємною (>= 0 кг).",
            details={"field": "weight", "exercise_type": exercise_type, "value": weight},
        )

    if exercise_type == ExerciseType.ASSISTED.value:
        if weight > 0.0:
            raise AppError(
                ErrorCode.ERR_POSITIVE_WEIGHT_IN_ASSISTED,
                422,
                "Для вправи з компенсацією (ASSISTED) значення weight має бути <= 0.",
                details={"field": "weight", "exercise_type": exercise_type, "value": weight},
            )
        if body_weight_snapshot + weight <= 0.0:
            raise AppError(
                ErrorCode.ERR_NON_POSITIVE_EFFECTIVE_LOAD,
                422,
                "Величина компенсації не може перевищувати або дорівнювати масі тіла користувача (W_eff <= 0).",
                details={
                    "field": "weight",
                    "exercise_type": exercise_type,
                    "weight": weight,
                    "body_weight_snapshot": body_weight_snapshot,
                    "effective_weight": body_weight_snapshot + weight,
                },
            )


class WorkoutService:
    """Сервіс управління тренуваннями (Етап 1 / Блок 1)."""

    def __init__(self, repository: WorkoutRepository) -> None:
        self.repository = repository
        self.repository.init_schema()

    def get_user_profile(self) -> UserProfile:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "getUserProfile",
            "Fetching global user profile",
        )
        profile = self.repository.get_profile()
        if profile is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                "Профіль користувача не знайдено.",
            )
        return UserProfile(**profile)

    def update_user_profile(self, payload: UpdateUserProfileRequest) -> UserProfile:
        weight = payload.current_body_weight
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "updateUserProfile",
            "Validating and updating user body weight",
            context={"current_body_weight": weight},
        )
        if not math.isfinite(weight) or weight < MIN_BODY_WEIGHT_KG or weight > MAX_BODY_WEIGHT_KG:
            raise AppError(
                ErrorCode.ERR_INVALID_BODY_WEIGHT,
                422,
                f"Маса тіла користувача повинна бути в діапазоні [{MIN_BODY_WEIGHT_KG}, {MAX_BODY_WEIGHT_KG}] кг.",
                details={
                    "field": "current_body_weight",
                    "value": weight,
                    "min": MIN_BODY_WEIGHT_KG,
                    "max": MAX_BODY_WEIGHT_KG,
                },
            )
        updated = self.repository.upsert_profile(weight)
        return UserProfile(**updated)

    def create_exercise(self, payload: CreateExerciseRequest) -> Exercise:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "createExercise",
            "Validating and creating exercise in catalog",
            context={
                "name": payload.name,
                "exercise_type": payload.exercise_type.value,
                "rm_model": payload.rm_model.value,
            },
        )
        existing = self.repository.get_exercise_by_name(payload.name)
        if existing is not None:
            raise AppError(
                ErrorCode.ERR_DUPLICATE_EXERCISE_NAME,
                422,
                f"Вправа з назвою '{payload.name}' вже існує в каталозі.",
                details={"field": "name", "value": payload.name},
            )
        created = self.repository.create_exercise(
            name=payload.name,
            exercise_type=payload.exercise_type.value,
            rm_model=payload.rm_model.value,
        )
        return _to_exercise_dto(created)

    def list_exercises(self, exercise_type: ExerciseType | None = None) -> ExerciseListResponse:
        filter_type = exercise_type.value if exercise_type is not None else None
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "listExercises",
            "Listing catalog exercises",
            context={"exercise_type": filter_type},
        )
        rows = self.repository.list_exercises(exercise_type=filter_type)
        items = [_to_exercise_dto(row) for row in rows]
        return ExerciseListResponse(items=items, total=len(items))

    def get_exercise_by_id(self, exercise_id: str) -> Exercise:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "getExerciseById",
            "Fetching exercise details",
            context={"exercise_id": exercise_id},
        )
        row = self.repository.get_exercise_by_id(exercise_id)
        if row is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Вправу '{exercise_id}' не знайдено.",
                details={"resource": "exercise", "exercise_id": exercise_id},
            )
        return _to_exercise_dto(row)

    def update_exercise_model(
        self, exercise_id: str, payload: UpdateExerciseModelRequest
    ) -> Exercise:
        raise NotImplementedError("TDD Red Phase: service method not implemented")

    def create_session(self, payload: CreateSessionRequest | None = None) -> WorkoutSession:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "createSession",
            "Creating workout session with immutable body weight snapshot",
            context={
                "started_at": payload.started_at if payload else None,
                "has_notes": bool(payload and payload.notes is not None),
            },
        )
        profile = self.repository.get_profile()
        if profile is None:
            raise AppError(
                ErrorCode.ERR_PROFILE_WEIGHT_MISSING,
                422,
                "У профілі користувача відсутня поточна маса тіла для фіксації снапшота.",
            )

        body_weight = float(profile["current_body_weight"])
        if body_weight < MIN_BODY_WEIGHT_KG or body_weight > MAX_BODY_WEIGHT_KG:
            raise AppError(
                ErrorCode.ERR_PROFILE_WEIGHT_MISSING,
                422,
                "Поточна маса тіла в профілі некоректна або відсутня.",
                details={"current_body_weight": body_weight},
            )

        created = self.repository.create_session(
            body_weight_snapshot=body_weight,
            started_at=payload.started_at if payload else None,
            notes=payload.notes if payload else None,
        )
        return WorkoutSession(
            session_id=created["session_id"],
            started_at=created["started_at"],
            body_weight_snapshot=created["body_weight_snapshot"],
            notes=created["notes"],
            blocks=[],
        )

    def list_sessions(self, limit: int = 20, offset: int = 0) -> SessionListResponse:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "listSessions",
            "Listing workout sessions with pagination",
            context={"limit": limit, "offset": offset},
        )
        rows, total = self.repository.list_sessions(limit=limit, offset=offset)
        items = [WorkoutSessionSummary(**row) for row in rows]
        return SessionListResponse(items=items, total=total, limit=limit, offset=offset)

    def get_session_by_id(self, session_id: str) -> WorkoutSession:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "getSessionById",
            "Fetching full workout session details",
            context={"session_id": session_id},
        )
        session = self.repository.get_session_by_id(session_id)
        if session is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Тренувальну сесію '{session_id}' не знайдено.",
                details={"resource": "session", "session_id": session_id},
            )
        blocks = [_to_exercise_block_dto(b) for b in session["blocks"]]
        return WorkoutSession(
            session_id=session["session_id"],
            started_at=session["started_at"],
            body_weight_snapshot=session["body_weight_snapshot"],
            notes=session["notes"],
            blocks=blocks,
        )

    def create_exercise_block(
        self, session_id: str, payload: CreateExerciseBlockRequest
    ) -> ExerciseBlock:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "createExerciseBlock",
            "Creating isolated exercise block in session",
            context={"session_id": session_id, "exercise_id": payload.exercise_id},
        )
        session = self.repository.get_session_by_id(session_id)
        if session is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Тренувальну сесію '{session_id}' не знайдено.",
                details={"resource": "session", "session_id": session_id},
            )
        exercise = self.repository.get_exercise_by_id(payload.exercise_id)
        if exercise is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Вправу '{payload.exercise_id}' не знайдено в каталозі.",
                details={"resource": "exercise", "exercise_id": payload.exercise_id},
            )
        block = self.repository.create_exercise_block(session_id, payload.exercise_id)
        return _to_exercise_block_dto(block)

    def get_exercise_block_by_id(
        self, session_id: str, block_id: str
    ) -> ExerciseBlock:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "getExerciseBlockById",
            "Fetching isolated exercise block details",
            context={"session_id": session_id, "block_id": block_id},
        )
        block = self.repository.get_exercise_block_by_id(session_id, block_id)
        if block is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Блок вправи '{block_id}' у сесії '{session_id}' не знайдено.",
                details={"resource": "block", "session_id": session_id, "block_id": block_id},
            )
        return _to_exercise_block_dto(block)

    def create_workout_set(
        self, session_id: str, block_id: str, payload: CreateWorkoutSetRequest
    ) -> CreateWorkoutSetResponse:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "createWorkoutSet",
            "Validating domain constraints and recording workout set",
            context={
                "session_id": session_id,
                "block_id": block_id,
                "weight": payload.weight,
                "reps": payload.reps,
                "rpe": payload.rpe,
                "is_warmup": payload.is_warmup,
            },
        )
        block = self.repository.get_exercise_block_by_id(session_id, block_id)
        if block is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Блок вправи '{block_id}' у сесії '{session_id}' не знайдено.",
                details={"resource": "block", "session_id": session_id, "block_id": block_id},
            )

        if not math.isfinite(payload.rpe) or payload.rpe < MIN_RPE or payload.rpe > MAX_RPE:
            raise AppError(
                ErrorCode.ERR_RPE_OUT_OF_RANGE,
                422,
                f"Показник RPE повинен бути в межах від {MIN_RPE} до {MAX_RPE}.",
                details={
                    "field": "rpe",
                    "value": payload.rpe,
                    "min": MIN_RPE,
                    "max": MAX_RPE,
                },
            )

        if payload.reps <= 0:
            raise AppError(
                ErrorCode.ERR_INVALID_REPS_COUNT,
                422,
                "Кількість повторень повинна бути більшою за 0.",
                details={"field": "reps", "value": payload.reps, "min": 1},
            )

        if payload.reps > MAX_BRZYCKI_REPS:
            raise AppError(
                ErrorCode.ERR_BRZYCKI_MATHEMATICAL_LIMIT,
                422,
                f"Кількість повторень {payload.reps} перевищує математичне обмеження (<= {MAX_BRZYCKI_REPS}) формули Brzycki.",
                details={
                    "field": "reps",
                    "value": payload.reps,
                    "max": MAX_BRZYCKI_REPS,
                },
            )

        _validate_set_weight(
            exercise_type=block["exercise_type"],
            weight=payload.weight,
            body_weight_snapshot=float(block["body_weight_snapshot"]),
        )

        created_set = self.repository.create_workout_set(
            session_id=session_id,
            block_id=block_id,
            weight=payload.weight,
            reps=payload.reps,
            rpe=payload.rpe,
            is_warmup=payload.is_warmup,
        )
        updated_block = self.repository.get_exercise_block_by_id(session_id, block_id)
        assert updated_block is not None
        return CreateWorkoutSetResponse(
            set=_to_workout_set_dto(
                created_set,
                block["exercise_type"],
                float(block["body_weight_snapshot"]),
            ),
            block_summary=_build_block_summary_dto(updated_block),
        )

    def delete_workout_set(
        self, session_id: str, block_id: str, set_id: str
    ) -> DeleteWorkoutSetResponse:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "deleteWorkoutSet",
            "Deleting workout set from exercise block",
            context={
                "session_id": session_id,
                "block_id": block_id,
                "set_id": set_id,
            },
        )
        block = self.repository.get_exercise_block_by_id(session_id, block_id)
        if block is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Блок вправи '{block_id}' у сесії '{session_id}' не знайдено.",
                details={"resource": "block", "session_id": session_id, "block_id": block_id},
            )

        deleted_set = self.repository.delete_workout_set(session_id, block_id, set_id)
        if deleted_set is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Підхід '{set_id}' у блоці '{block_id}' не знайдено.",
                details={
                    "resource": "set",
                    "session_id": session_id,
                    "block_id": block_id,
                    "set_id": set_id,
                },
            )

        updated_block = self.repository.get_exercise_block_by_id(session_id, block_id)
        assert updated_block is not None
        return DeleteWorkoutSetResponse(
            deleted_set_id=deleted_set["set_id"],
            block_summary=_build_block_summary_dto(updated_block),
        )

    def get_exercise_analytics(self, exercise_id: str) -> ExerciseAnalyticsResponse:
        raise NotImplementedError("TDD Red Phase: service method not implemented")
