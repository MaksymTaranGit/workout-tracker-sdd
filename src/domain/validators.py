"""
Доменні валідатори та граничні константи предметної області (`spec/srs.tex`, `spec/srs-addendum.md`).

Винесення доменних правил в окремий модуль забезпечує принцип єдиної відповідальності (SRP)
та ізолює інваріанти валідації від оркестрації репозиторіїв у `WorkoutService`.
"""

from __future__ import annotations

import math
from datetime import date, datetime

from src.core.errors import AppError, ErrorCode
from src.domain.schemas import ExerciseType

MIN_BODY_WEIGHT_KG = 30.0
MAX_BODY_WEIGHT_KG = 300.0
MIN_RPE = 6.0
MAX_RPE = 10.0
MAX_BRZYCKI_REPS = 36


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


def parse_and_validate_date_range(
    from_date: str | None, to_date: str | None
) -> tuple[date | None, date | None]:
    """Парсить опціональні межі діапазону дат і перевіряє умову `from_date <= to_date` (`400 ERR_BAD_REQUEST`)."""
    parsed_from = _parse_iso_date(from_date, "from_date") if from_date is not None else None
    parsed_to = _parse_iso_date(to_date, "to_date") if to_date is not None else None
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise AppError(
            ErrorCode.ERR_BAD_REQUEST,
            400,
            "Початкова дата 'from_date' не може перевищувати кінцеву дату 'to_date'.",
            details={"from_date": from_date, "to_date": to_date},
        )
    return parsed_from, parsed_to


def validate_body_weight(
    weight: float,
    error_code: ErrorCode = ErrorCode.ERR_INVALID_BODY_WEIGHT,
) -> float:
    """Перевіряє коректність маси тіла користувача в допустимому діапазоні `[30.0, 300.0]` кг (`REQ-F-019`)."""
    if not math.isfinite(weight) or weight < MIN_BODY_WEIGHT_KG or weight > MAX_BODY_WEIGHT_KG:
        message = (
            f"Маса тіла користувача повинна бути в діапазоні [{MIN_BODY_WEIGHT_KG}, {MAX_BODY_WEIGHT_KG}] кг."
            if error_code == ErrorCode.ERR_INVALID_BODY_WEIGHT
            else "Поточна маса тіла в профілі некоректна або відсутня."
        )
        raise AppError(
            error_code,
            422,
            message,
            details={
                "field": "current_body_weight",
                "value": weight,
                "min": MIN_BODY_WEIGHT_KG,
                "max": MAX_BODY_WEIGHT_KG,
            },
        )
    return float(weight)


def validate_workout_set_inputs(
    exercise_type: str,
    weight: float,
    reps: int,
    rpe: float,
    body_weight_snapshot: float,
) -> None:
    """
    Виконує повну доменну валідацію параметрів силового підходу (`REQ-F-004`, `RSK-02`, `RSK-07`):
    - межі `RPE` у `[6.0, 10.0]` (`422 ERR_RPE_OUT_OF_RANGE`);
    - кількість повторень `[1, 36]` (`422 ERR_INVALID_REPS_COUNT`, `422 ERR_BRZYCKI_MATHEMATICAL_LIMIT`);
    - знак ваги та позитивне ефективне навантаження для `STANDARD`, `BODYWEIGHT`, `ASSISTED`.
    """
    if not math.isfinite(rpe) or rpe < MIN_RPE or rpe > MAX_RPE:
        raise AppError(
            ErrorCode.ERR_RPE_OUT_OF_RANGE,
            422,
            f"Показник RPE повинен бути в межах від {MIN_RPE} до {MAX_RPE}.",
            details={
                "field": "rpe",
                "value": rpe,
                "min": MIN_RPE,
                "max": MAX_RPE,
            },
        )

    if reps <= 0:
        raise AppError(
            ErrorCode.ERR_INVALID_REPS_COUNT,
            422,
            "Кількість повторень повинна бути більшою за 0.",
            details={"field": "reps", "value": reps, "min": 1},
        )

    if reps > MAX_BRZYCKI_REPS:
        raise AppError(
            ErrorCode.ERR_BRZYCKI_MATHEMATICAL_LIMIT,
            422,
            f"Кількість повторень {reps} перевищує математичне обмеження (<= {MAX_BRZYCKI_REPS}) формули Brzycki.",
            details={
                "field": "reps",
                "value": reps,
                "max": MAX_BRZYCKI_REPS,
            },
        )

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
