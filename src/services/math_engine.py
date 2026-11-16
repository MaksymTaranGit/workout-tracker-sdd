"""
Математичний рушій (Math Engine) системи.

Реалізує розрахунки всіх чотирьох етапів SDD/TDD:
- Ефективна вага $W_{eff}$ для `STANDARD`, `BODYWEIGHT` та `ASSISTED` (`REQ-F-008` – `REQ-F-010`, `REQ-F-021`);
- Механічна робота підходу `Volume Load` з виключенням розминки (`REQ-F-006`, `REQ-F-007`, `BDD-003`);
- Розрахунок одноповторного максимуму `1RM` за моделями `EPLEY` і `BRZYCKI` з високоточною
  арифметикою `Decimal` (`ROUND_DOWN`) та попередженням Soft Constraint (`REQ-F-011` – `REQ-F-014`, `RSK-01`, `RSK-02`);
- Обчислення Дельти прогресії відносно останнього хронологічного блоку (`REQ-F-015`, `REQ-F-016`, `REQ-F-018`).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from src.core.logger import TRACE_LEVEL_NUM, log_event


class MathEngine:
    """Математичне ядро розрахунку тренувальних метрик із трасуванням на рівні TRACE."""

    @staticmethod
    def calculate_effective_weight(
        exercise_type: str, weight: float, body_weight_snapshot: float
    ) -> float:
        """Обчислює ефективне навантаження $W_{eff}$ у кг із точністю до 2 знаків."""
        if exercise_type == "STANDARD":
            effective_weight = round(float(weight), 2)
        elif exercise_type in ("BODYWEIGHT", "ASSISTED"):
            effective_weight = round(float(body_weight_snapshot) + float(weight), 2)
        else:
            raise ValueError(f"Unsupported exercise_type: {exercise_type}")

        log_event(
            TRACE_LEVEL_NUM,
            "MATH_ENGINE",
            "calculate_effective_weight",
            "Calculated effective weight W_eff",
            context={
                "exercise_type": exercise_type,
                "weight": float(weight),
                "body_weight_snapshot": float(body_weight_snapshot),
                "effective_weight": effective_weight,
            },
        )
        return effective_weight

    @staticmethod
    def calculate_set_volume_load(
        effective_weight: float, reps: int, is_warmup: bool
    ) -> float:
        """Обчислює Volume Load підходу (`0.0` для розминочних підходів)."""
        if is_warmup:
            volume_load = 0.0
        else:
            volume_load = round(float(effective_weight) * int(reps), 2)

        log_event(
            TRACE_LEVEL_NUM,
            "MATH_ENGINE",
            "calculate_set_volume_load",
            "Calculated set volume load",
            context={
                "effective_weight": float(effective_weight),
                "reps": int(reps),
                "is_warmup": bool(is_warmup),
                "set_volume_load": volume_load,
            },
        )
        return volume_load

    @staticmethod
    def calculate_1rm(
        effective_weight: float, reps: int, rm_model: str, is_warmup: bool
    ) -> tuple[float | None, bool, str | None]:
        """
        Обчислює оціночний 1RM за моделями EPLEY або BRZYCKI (`Decimal`, `ROUND_DOWN` до 0.01)
        та формує попередження Soft Constraint при кількості повторень > 10 (`REQ-F-014`).
        """
        if is_warmup:
            log_event(
                TRACE_LEVEL_NUM,
                "MATH_ENGINE",
                "calculate_1rm",
                "Skipped 1RM calculation for warmup set",
                context={
                    "effective_weight": float(effective_weight),
                    "reps": int(reps),
                    "rm_model": rm_model,
                    "is_warmup": True,
                    "estimated_1rm": None,
                    "soft_constraint_warning": False,
                },
            )
            return None, False, None

        w_dec = Decimal(str(effective_weight))
        r_int = int(reps)
        r_dec = Decimal(r_int)

        if rm_model == "EPLEY":
            raw_1rm = (w_dec * (Decimal(30) + r_dec)) / Decimal(30)
        elif rm_model == "BRZYCKI":
            if r_int < 1 or r_int > 36:
                raise ValueError(f"Brzycki reps must be in [1, 36], got {r_int}")
            raw_1rm = (w_dec * Decimal(36)) / (Decimal(37) - r_dec)
        else:
            raise ValueError(f"Unsupported rm_model: {rm_model}")

        estimated_1rm = float(raw_1rm.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        soft_constraint_warning = r_int > 10
        warning_message = (
            f"Кількість повторень перевищує 10 (R={r_int}). Розрахункове значення 1RM має знижену точність (REQ-F-014)."
            if soft_constraint_warning
            else None
        )

        log_event(
            TRACE_LEVEL_NUM,
            "MATH_ENGINE",
            "calculate_1rm",
            "Calculated estimated 1RM",
            context={
                "effective_weight": float(effective_weight),
                "reps": r_int,
                "rm_model": rm_model,
                "is_warmup": False,
                "estimated_1rm": estimated_1rm,
                "soft_constraint_warning": soft_constraint_warning,
            },
        )
        return estimated_1rm, soft_constraint_warning, warning_message

    @staticmethod
    def calculate_deltas(
        current_volume: float,
        current_max_1rm: float | None,
        previous_volume: float | None,
        previous_max_1rm: float | None,
    ) -> tuple[bool, float | None, float | None]:
        """
        Обчислює Дельту Volume Load та 1RM відносно попереднього хронологічного виконання
        з точністю `Decimal` без похибок IEEE 754 `float` (`REQ-F-015`, `REQ-F-016`, `REQ-F-018`).
        """
        if previous_volume is None or current_max_1rm is None:
            log_event(
                TRACE_LEVEL_NUM,
                "MATH_ENGINE",
                "calculate_deltas",
                "Skipped delta calculation without baseline or working sets",
                context={
                    "current_volume": float(current_volume),
                    "current_max_1rm": current_max_1rm,
                    "previous_volume": previous_volume,
                    "previous_max_1rm": previous_max_1rm,
                    "has_previous_baseline": False,
                },
            )
            return False, None, None

        volume_delta = float(
            (Decimal(str(current_volume)) - Decimal(str(previous_volume))).quantize(
                Decimal("0.01")
            )
        )
        max_1rm_delta = (
            float(
                (Decimal(str(current_max_1rm)) - Decimal(str(previous_max_1rm))).quantize(
                    Decimal("0.01")
                )
            )
            if previous_max_1rm is not None
            else None
        )

        log_event(
            TRACE_LEVEL_NUM,
            "MATH_ENGINE",
            "calculate_deltas",
            "Calculated progression deltas",
            context={
                "current_volume": float(current_volume),
                "previous_volume": float(previous_volume),
                "volume_load_delta": volume_delta,
                "current_max_1rm": float(current_max_1rm),
                "previous_max_1rm": float(previous_max_1rm)
                if previous_max_1rm is not None
                else None,
                "max_1rm_delta": max_1rm_delta,
                "has_previous_baseline": True,
            },
        )
        return True, volume_delta, max_1rm_delta
