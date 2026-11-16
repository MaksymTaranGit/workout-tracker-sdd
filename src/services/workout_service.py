"""
Сервісний шар (Service Layer) для координації репозиторіїв, доменної валідації та телеметрії.

Реалізує бізнес-логіку та доменні правила всіх чотирьох блоків SDD/TDD:
- управління профілем користувача та обмеженням маси тіла `[30.0, 300.0]` (`REQ-F-019`, `AC10`);
- управління каталогом вправ, унікальністю назв та вибором моделі 1RM (`REQ-F-012`, `REQ-F-013`, `REQ-F-020`, `AC11`);
- створення сесій із незмінним знімком `body_weight_snapshot` (`REQ-F-001`, `REQ-F-002`, `BDD-001`, `RSK-06`);
- управління ізольованими блоками вправ (`REQ-F-003`, `RSK-09`);
- запис і видалення підходів із валідацією RPE, повторень та знака ваги (`REQ-F-004`, `REQ-F-005`, `AC2`, `RSK-02`, `RSK-07`);
- обчислення `Volume Load`, `1RM`, Дельти прогресії відносно останньої бази та аналітика дашборду (`REQ-F-006` – `REQ-F-018`, `REQ-F-021`).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from src.core.errors import AppError, ErrorCode
from src.core.logger import TRACE_LEVEL_NUM, log_event
from src.domain.schemas import (
    AnalyticsDataPoint,
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
    LatestProgressionSummary,
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
    row: dict[str, Any],
    exercise_type: str,
    body_weight_snapshot: float,
    rm_model: str = "EPLEY",
) -> WorkoutSet:
    """Формує DTO підходу з обчисленням W_eff, set_volume_load (Блок 2) та 1RM (Блок 3)."""
    weight = float(row["weight"])
    reps = int(row["reps"])
    is_warmup = bool(row["is_warmup"])

    effective_weight = MathEngine.calculate_effective_weight(
        exercise_type, weight, body_weight_snapshot
    )
    set_volume_load = MathEngine.calculate_set_volume_load(
        effective_weight, reps, is_warmup
    )
    estimated_1rm, soft_constraint_warning, warning_message = MathEngine.calculate_1rm(
        effective_weight, reps, rm_model, is_warmup
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
        estimated_1rm=estimated_1rm,
        soft_constraint_warning=soft_constraint_warning,
        warning_message=warning_message,
    )


def _compute_block_sets_and_metrics(
    row: dict[str, Any],
) -> tuple[list[WorkoutSet], float, float | None]:
    """Обчислює перелік підходів, сумарний Volume Load та максимальний 1RM блоку."""
    exercise_type = row["exercise_type"]
    body_weight_snapshot = float(row["body_weight_snapshot"])
    rm_model = row.get("rm_model", RmModel.EPLEY.value)
    sets = [
        _to_workout_set_dto(s, exercise_type, body_weight_snapshot, rm_model)
        for s in row.get("sets", [])
    ]
    block_volume_load = round(sum(s.set_volume_load for s in sets), 2)
    working_1rms = [
        s.estimated_1rm
        for s in sets
        if not s.is_warmup and s.estimated_1rm is not None
    ]
    block_max_1rm = max(working_1rms) if working_1rms else None
    return sets, block_volume_load, block_max_1rm


def _parse_iso_date(raw_date: str, param_name: str) -> date:
    """Валідує рядок дати ISO-8601 (`YYYY-MM-DD` або datetime) і повертає `date` або `400 ERR_BAD_REQUEST`."""
    try:
        if len(raw_date) == 10:
            return date.fromisoformat(raw_date)
        return datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise AppError(
            ErrorCode.ERR_BAD_REQUEST,
            400,
            f"Некоректний формат дати в параметрі '{param_name}'. Очікується ISO-8601 (YYYY-MM-DD).",
            details={"field": param_name, "value": raw_date},
        ) from exc


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
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "updateExerciseModel",
            "Updating exercise 1RM calculation model",
            context={
                "exercise_id": exercise_id,
                "rm_model": payload.rm_model.value,
            },
        )
        updated = self.repository.update_exercise_model(
            exercise_id=exercise_id,
            rm_model=payload.rm_model.value,
        )
        if updated is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Вправу '{exercise_id}' не знайдено.",
                details={"resource": "exercise", "exercise_id": exercise_id},
            )
        return _to_exercise_dto(updated)

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
        working_blocks_cache: dict[str, list[dict[str, Any]]] = {}
        blocks = [
            self._assemble_exercise_block(b, working_blocks_cache=working_blocks_cache)
            for b in session["blocks"]
        ]
        return WorkoutSession(
            session_id=session["session_id"],
            started_at=session["started_at"],
            body_weight_snapshot=session["body_weight_snapshot"],
            notes=session["notes"],
            blocks=blocks,
        )

    def _compute_block_deltas(
        self,
        block_row: dict[str, Any],
        block_volume_load: float,
        block_max_1rm: float | None,
        working_blocks_cache: dict[str, list[dict[str, Any]]] | None = None,
    ) -> tuple[bool, float | None, float | None]:
        """Обчислює Дельту блоку відносно останнього попереднього робочого блоку цієї вправи."""
        if block_max_1rm is None:
            return MathEngine.calculate_deltas(block_volume_load, None, None, None)

        exercise_id = block_row["exercise_id"]
        if working_blocks_cache is not None and exercise_id in working_blocks_cache:
            working_blocks = working_blocks_cache[exercise_id]
        else:
            working_blocks = self.repository.get_exercise_analytics(exercise_id)
            if working_blocks_cache is not None:
                working_blocks_cache[exercise_id] = working_blocks

        block_id = block_row["block_id"]
        current_idx = next(
            (i for i, blk in enumerate(working_blocks) if blk["block_id"] == block_id),
            -1,
        )
        if current_idx <= 0:
            return MathEngine.calculate_deltas(block_volume_load, block_max_1rm, None, None)

        prev_block = working_blocks[current_idx - 1]
        _, prev_vl, prev_1rm = _compute_block_sets_and_metrics(prev_block)
        return MathEngine.calculate_deltas(
            block_volume_load, block_max_1rm, prev_vl, prev_1rm
        )

    def _assemble_exercise_block(
        self,
        row: dict[str, Any],
        working_blocks_cache: dict[str, list[dict[str, Any]]] | None = None,
    ) -> ExerciseBlock:
        sets, block_volume_load, block_max_1rm = _compute_block_sets_and_metrics(row)
        deltas = self._compute_block_deltas(
            row,
            block_volume_load,
            block_max_1rm,
            working_blocks_cache=working_blocks_cache,
        )
        return ExerciseBlock(
            block_id=row["block_id"],
            session_id=row["session_id"],
            exercise_id=row["exercise_id"],
            exercise_name=row["exercise_name"],
            exercise_type=ExerciseType(row["exercise_type"]),
            rm_model=RmModel(row["rm_model"]),
            order_index=int(row["order_index"]),
            block_volume_load=block_volume_load,
            block_max_1rm=block_max_1rm,
            has_previous_baseline=deltas[0],
            volume_load_delta=deltas[1],
            max_1rm_delta=deltas[2],
            sets=sets,
        )

    def _assemble_block_summary(self, block_row: dict[str, Any]) -> ExerciseBlockSummary:
        _, block_volume_load, block_max_1rm = _compute_block_sets_and_metrics(block_row)
        deltas = self._compute_block_deltas(block_row, block_volume_load, block_max_1rm)
        return ExerciseBlockSummary(
            block_id=block_row["block_id"],
            block_volume_load=block_volume_load,
            block_max_1rm=block_max_1rm,
            has_previous_baseline=deltas[0],
            volume_load_delta=deltas[1],
            max_1rm_delta=deltas[2],
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
        return self._assemble_exercise_block(block)

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
        return self._assemble_exercise_block(block)

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
                block["rm_model"],
            ),
            block_summary=self._assemble_block_summary(updated_block),
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
            block_summary=self._assemble_block_summary(updated_block),
        )

    def get_exercise_analytics(
        self,
        exercise_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> ExerciseAnalyticsResponse:
        log_event(
            TRACE_LEVEL_NUM,
            "SERVICE",
            "getExerciseAnalytics",
            "Building exercise analytics progression and time series",
            context={
                "exercise_id": exercise_id,
                "from_date": from_date,
                "to_date": to_date,
                "limit": limit,
            },
        )
        exercise = self.repository.get_exercise_by_id(exercise_id)
        if exercise is None:
            raise AppError(
                ErrorCode.ERR_RESOURCE_NOT_FOUND,
                404,
                f"Вправу '{exercise_id}' не знайдено.",
                details={"resource": "exercise", "exercise_id": exercise_id},
            )

        parsed_from = _parse_iso_date(from_date, "from_date") if from_date is not None else None
        parsed_to = _parse_iso_date(to_date, "to_date") if to_date is not None else None
        if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
            raise AppError(
                ErrorCode.ERR_BAD_REQUEST,
                400,
                "Початкова дата 'from_date' не може перевищувати кінцеву дату 'to_date'.",
                details={"from_date": from_date, "to_date": to_date},
            )

        working_blocks = self.repository.get_exercise_analytics(exercise_id)

        all_points: list[AnalyticsDataPoint] = []
        prev_volume: float | None = None
        prev_max_1rm: float | None = None

        for blk in working_blocks:
            _, cur_vl, cur_1rm = _compute_block_sets_and_metrics(blk)
            _, vl_delta, rm_delta = MathEngine.calculate_deltas(
                cur_vl, cur_1rm, prev_volume, prev_max_1rm
            )
            all_points.append(
                AnalyticsDataPoint(
                    session_id=blk["session_id"],
                    block_id=blk["block_id"],
                    performed_at=blk["started_at"],
                    body_weight_snapshot=float(blk["body_weight_snapshot"]),
                    block_volume_load=cur_vl,
                    block_max_1rm=cur_1rm,
                    volume_load_delta=vl_delta,
                    max_1rm_delta=rm_delta,
                )
            )
            prev_volume = cur_vl
            prev_max_1rm = cur_1rm

        if not all_points:
            latest_progression = LatestProgressionSummary(has_previous_baseline=False)
        elif len(all_points) == 1:
            cur = all_points[0]
            latest_progression = LatestProgressionSummary(
                has_previous_baseline=False,
                current_block_id=cur.block_id,
                previous_block_id=None,
                current_volume_load=cur.block_volume_load,
                previous_volume_load=None,
                volume_load_delta=None,
                current_max_1rm=cur.block_max_1rm,
                previous_max_1rm=None,
                max_1rm_delta=None,
            )
        else:
            prev, cur = all_points[-2], all_points[-1]
            latest_progression = LatestProgressionSummary(
                has_previous_baseline=True,
                current_block_id=cur.block_id,
                previous_block_id=prev.block_id,
                current_volume_load=cur.block_volume_load,
                previous_volume_load=prev.block_volume_load,
                volume_load_delta=cur.volume_load_delta,
                current_max_1rm=cur.block_max_1rm,
                previous_max_1rm=prev.block_max_1rm,
                max_1rm_delta=cur.max_1rm_delta,
            )

        filtered_points = all_points
        if parsed_from is not None:
            filtered_points = [
                p
                for p in filtered_points
                if date.fromisoformat(p.performed_at[:10]) >= parsed_from
            ]
        if parsed_to is not None:
            filtered_points = [
                p
                for p in filtered_points
                if date.fromisoformat(p.performed_at[:10]) <= parsed_to
            ]
        if len(filtered_points) > limit:
            filtered_points = filtered_points[-limit:]

        return ExerciseAnalyticsResponse(
            exercise_id=exercise["exercise_id"],
            exercise_name=exercise["name"],
            exercise_type=ExerciseType(exercise["exercise_type"]),
            rm_model=RmModel(exercise["rm_model"]),
            latest_progression=latest_progression,
            data_points=filtered_points,
        )
