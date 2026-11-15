"""
Pydantic-моделі запитів і відповідей REST API у суворій відповідності до
секції `components/schemas` формальної специфікації `spec/openapi.yaml`
та вимог `spec/srs.tex` і `spec/srs-addendum.md`.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from src.core.errors import ErrorCode, ErrorObject, ErrorResponse


class ExerciseType(str, Enum):
    """Біомеханічний тип силової вправи (Глосарій SRS, REQ-F-020)."""

    STANDARD = "STANDARD"
    BODYWEIGHT = "BODYWEIGHT"
    ASSISTED = "ASSISTED"


class RmModel(str, Enum):
    """Математична модель розрахунку одноповторного максимуму 1RM (REQ-F-012, REQ-F-013)."""

    EPLEY = "EPLEY"
    BRZYCKI = "BRZYCKI"


class UserProfile(BaseModel):
    """Глобальний профіль користувача (Глосарій SRS, REQ-F-019)."""

    user_id: str = Field(..., description="Унікальний ідентифікатор профілю користувача")
    current_body_weight: float = Field(
        ...,
        ge=30.0,
        le=300.0,
        description="Поточна маса тіла користувача в кг (REQ-F-019)",
    )
    unit: Literal["kg"] = Field(default="kg", description="Одиниця вимірювання маси тіла")
    updated_at: str = Field(..., description="Час останнього оновлення профілю (ISO-8601 UTC)")


class UpdateUserProfileRequest(BaseModel):
    """Запит на оновлення поточної маси тіла в профілі (REQ-F-019, BDD-001)."""

    current_body_weight: float = Field(
        ...,
        description="Нове значення маси тіла в діапазоні 30.0..300.0 кг (доменна перевірка 422 ERR_INVALID_BODY_WEIGHT)",
    )


class CreateExerciseRequest(BaseModel):
    """Запит на створення нової вправи в каталозі (REQ-F-012, REQ-F-013, REQ-F-020)."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="Унікальна назва вправи",
    )
    exercise_type: ExerciseType = Field(..., description="Біомеханічний тип силової вправи")
    rm_model: RmModel = Field(
        default=RmModel.EPLEY,
        description="Математична модель 1RM (за замовчуванням EPLEY згідно з REQ-F-013)",
    )


class UpdateExerciseModelRequest(BaseModel):
    """Запит на зміну математичної моделі 1RM для конкретної вправи (REQ-F-012)."""

    rm_model: RmModel = Field(..., description="Обрана математична модель 1RM (EPLEY або BRZYCKI)")


class Exercise(BaseModel):
    """Сутність вправи в довіднику (REQ-F-012, REQ-F-013, REQ-F-020)."""

    exercise_id: str = Field(..., description="Унікальний ідентифікатор вправи")
    name: str = Field(..., min_length=2, max_length=120, description="Назва вправи")
    exercise_type: ExerciseType = Field(..., description="Біомеханічний тип вправи")
    rm_model: RmModel = Field(..., description="Активна математична модель 1RM")
    created_at: str = Field(..., description="Час створення запису (ISO-8601 UTC)")
    updated_at: str | None = Field(default=None, description="Час останнього оновлення (ISO-8601 UTC)")


class ExerciseListResponse(BaseModel):
    """Відповідь зі списком вправ каталогу (REQ-F-020)."""

    items: list[Exercise] = Field(..., description="Перелік вправ у довіднику")
    total: int = Field(..., ge=0, description="Загальна кількість знайдених вправ")


class CreateSessionRequest(BaseModel):
    """Параметри створення нової тренувальної сесії (REQ-F-001)."""

    started_at: str | None = Field(
        default=None,
        description="Час початку тренування (за замовчуванням — поточний UTC час сервера)",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Опціональні нотатки до тренувальної сесії",
    )


class WorkoutSessionSummary(BaseModel):
    """Коротке представлення тренувальної сесії у списку."""

    session_id: str = Field(..., description="Унікальний ідентифікатор сесії")
    started_at: str = Field(..., description="Дата та час початку сесії (ISO-8601 UTC)")
    body_weight_snapshot: float = Field(
        ...,
        ge=30.0,
        le=300.0,
        description="Незмінний знімок маси тіла користувача на момент створення сесії (REQ-F-002, BDD-001)",
    )
    notes: str | None = Field(default=None, description="Нотатки до сесії")
    blocks_count: int = Field(..., ge=0, description="Кількість блоків вправ у сесії")


class SessionListResponse(BaseModel):
    """Відповідь зі списком тренувальних сесій з пагінацією."""

    items: list[WorkoutSessionSummary] = Field(..., description="Масив сесій")
    total: int = Field(..., ge=0, description="Загальна кількість сесій")
    limit: int = Field(..., ge=1, description="Ліміт записів на сторінку")
    offset: int = Field(..., ge=0, description="Зміщення вибірки")


class CreateExerciseBlockRequest(BaseModel):
    """Запит на додавання ізольованого блоку вправи до сесії (REQ-F-003, REQ-F-006)."""

    exercise_id: str = Field(
        ...,
        min_length=1,
        description="Ідентифікатор вправи з каталогу",
    )


class ExerciseBlockSummary(BaseModel):
    """Розрахункове зведення агрегатів ізольованого блоку вправи (REQ-F-006, REQ-F-015, REQ-F-016, REQ-F-018)."""

    block_id: str = Field(..., description="Унікальний ідентифікатор блоку")
    block_volume_load: float = Field(
        ...,
        ge=0.0,
        description="Сумарний Volume Load робочих підходів виключно цього блоку (REQ-F-006, REQ-F-007)",
    )
    block_max_1rm: float | None = Field(
        default=None,
        description="Максимальний розрахунковий 1RM серед робочих підходів блоку (REQ-F-011)",
    )
    has_previous_baseline: bool = Field(
        ...,
        description="Чи існує попередній хронологічний запис цієї вправи для обчислення Дельти (REQ-F-018)",
    )
    volume_load_delta: float | None = Field(
        default=None,
        description="Різниця Volume Load відносно останнього хронологічного блоку цієї вправи (REQ-F-015)",
    )
    max_1rm_delta: float | None = Field(
        default=None,
        description="Різниця максимального 1RM відносно останнього хронологічного блоку цієї вправи (REQ-F-016)",
    )


class CreateWorkoutSetRequest(BaseModel):
    """Вхідні дані для фіксації підходу (REQ-F-004, REQ-F-005, REQ-F-010)."""

    weight: float = Field(
        ...,
        description=(
            "Вага обтяження у кг: для STANDARD > 0, для BODYWEIGHT >= 0, "
            "для ASSISTED <= 0 (де body_weight_snapshot + weight > 0)"
        ),
    )
    reps: int = Field(
        ...,
        description="Кількість виконаних повторень (доменне обмеження 1..36, REQ-F-004, RSK-02)",
    )
    rpe: float = Field(
        ...,
        description="Суб'єктивна оцінка важкості підходу за шкалою RPE 6.0..10.0 (REQ-F-004)",
    )
    is_warmup: bool = Field(
        default=False,
        description="Прапорець розминочного підходу (REQ-F-005). Якщо true, ігнорується у Volume Load та 1RM.",
    )


class WorkoutSet(BaseModel):
    """Зафіксований підхід разом з обчисленими сервером метриками Volume Load та 1RM."""

    set_id: str = Field(..., description="Унікальний ідентифікатор підходу")
    block_id: str = Field(..., description="Ідентифікатор батьківського блоку вправи")
    set_number: int = Field(..., ge=1, description="Порядковий номер підходу в блоці")
    weight: float = Field(..., description="Введена вага обтяження (або компенсації)")
    effective_weight: float = Field(
        ...,
        description="Фактичне розрахункове навантаження W_eff (REQ-F-021)",
    )
    reps: int = Field(..., ge=1, le=36, description="Кількість повторень (1..36)")
    rpe: float = Field(..., ge=6.0, le=10.0, description="Оцінка RPE (6.0..10.0)")
    is_warmup: bool = Field(..., description="Прапорець розминочного підходу")
    set_volume_load: float = Field(
        ...,
        ge=0.0,
        description="Обчислений тоннаж підходу (0.0 для розминочних підходів, REQ-F-006 – REQ-F-009)",
    )
    estimated_1rm: float | None = Field(
        default=None,
        description="Розрахунковий одноповторний максимум (null для розминочних підходів, REQ-F-011, BDD-006)",
    )
    soft_constraint_warning: bool = Field(
        ...,
        description="Індикатор зниженої точності розрахунку 1RM при кількості повторень > 10 (REQ-F-014, BDD-004)",
    )
    warning_message: str | None = Field(
        default=None,
        description="Текстове пояснення попередження Soft Constraint",
    )


class ExerciseBlock(BaseModel):
    """Ізольований блок виконання вправи в межах сесії (REQ-F-006, RSK-09)."""

    block_id: str = Field(..., description="Унікальний ідентифікатор блоку")
    session_id: str = Field(..., description="Ідентифікатор тренувальної сесії")
    exercise_id: str = Field(..., description="Ідентифікатор вправи з каталогу")
    exercise_name: str = Field(..., description="Назва вправи")
    exercise_type: ExerciseType = Field(..., description="Біомеханічний тип вправи")
    rm_model: RmModel = Field(..., description="Математична модель 1RM")
    order_index: int = Field(..., ge=1, description="Порядковий номер блоку в межах сесії (REQ-F-021)")
    block_volume_load: float = Field(..., ge=0.0, description="Сумарний Volume Load блоку")
    block_max_1rm: float | None = Field(default=None, description="Максимальний 1RM блоку")
    has_previous_baseline: bool = Field(..., description="Наявність попереднього блоку цієї вправи")
    volume_load_delta: float | None = Field(default=None, description="Дельта Volume Load")
    max_1rm_delta: float | None = Field(default=None, description="Дельта максимального 1RM")
    sets: list[WorkoutSet] = Field(default_factory=list, description="Підходи в межах блоку")


class WorkoutSession(BaseModel):
    """Повна модель тренувальної сесії з ізольованими блоками вправ (REQ-F-001, REQ-F-002)."""

    session_id: str = Field(..., description="Унікальний ідентифікатор тренувальної сесії")
    started_at: str = Field(..., description="Час початку сесії (ISO-8601 UTC)")
    body_weight_snapshot: float = Field(
        ...,
        ge=30.0,
        le=300.0,
        description="Незмінний (immutable) знімок маси тіла користувача в кг (REQ-F-002, RSK-06)",
    )
    notes: str | None = Field(default=None, description="Нотатки до сесії")
    blocks: list[ExerciseBlock] = Field(default_factory=list, description="Ізольовані блоки вправ")


class CreateWorkoutSetResponse(BaseModel):
    """Відповідь при збереженні підходу з миттєвим оновленням агрегатів блоку (REQ-NF-001)."""

    set: WorkoutSet
    block_summary: ExerciseBlockSummary


class DeleteWorkoutSetResponse(BaseModel):
    """Відповідь після видалення підходу з перерахованим станом блоку."""

    deleted_set_id: str = Field(..., description="Ідентифікатор видаленого підходу")
    block_summary: ExerciseBlockSummary


class LatestProgressionSummary(BaseModel):
    """Підсумковий блок Дельти прогресії для останнього виконання вправи (REQ-F-015, REQ-F-016, REQ-F-018, BDD-005)."""

    has_previous_baseline: bool
    current_block_id: str | None = None
    previous_block_id: str | None = None
    current_volume_load: float | None = None
    previous_volume_load: float | None = None
    volume_load_delta: float | None = None
    current_max_1rm: float | None = None
    previous_max_1rm: float | None = None
    max_1rm_delta: float | None = None


class AnalyticsDataPoint(BaseModel):
    """Точка часового ряду для побудови лінійного графіка на дашборді (REQ-F-017, BDD-007)."""

    session_id: str
    block_id: str
    performed_at: str
    body_weight_snapshot: float
    block_volume_load: float
    block_max_1rm: float | None = None
    volume_load_delta: float | None = None
    max_1rm_delta: float | None = None


class ExerciseAnalyticsResponse(BaseModel):
    """Дані візуального аналітичного дашборду вправи (REQ-F-015 – REQ-F-018, BDD-005, BDD-007)."""

    exercise_id: str
    exercise_name: str
    exercise_type: ExerciseType
    rm_model: RmModel
    latest_progression: LatestProgressionSummary
    data_points: list[AnalyticsDataPoint]


__all__ = [
    "AnalyticsDataPoint",
    "CreateExerciseBlockRequest",
    "CreateExerciseRequest",
    "CreateSessionRequest",
    "CreateWorkoutSetRequest",
    "CreateWorkoutSetResponse",
    "DeleteWorkoutSetResponse",
    "ErrorCode",
    "ErrorObject",
    "ErrorResponse",
    "Exercise",
    "ExerciseAnalyticsResponse",
    "ExerciseBlock",
    "ExerciseBlockSummary",
    "ExerciseListResponse",
    "ExerciseType",
    "LatestProgressionSummary",
    "RmModel",
    "SessionListResponse",
    "UpdateExerciseModelRequest",
    "UpdateUserProfileRequest",
    "UserProfile",
    "WorkoutSession",
    "WorkoutSessionSummary",
    "WorkoutSet",
]
