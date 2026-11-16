"""
Математичний рушій (Math Engine) системи.

Реалізує розрахунки Етапу 2 / Блоку 2 (`TKT-09`, `TKT-11`):
- Ефективна вага $W_{eff}$ для `STANDARD`, `BODYWEIGHT` та `ASSISTED` (`REQ-F-008` – `REQ-F-010`, `REQ-F-021`);
- Механічна робота підходу `Volume Load` з виключенням розминки (`REQ-F-006`, `REQ-F-007`, `BDD-003`).

Методи Блоків 3-4 (`calculate_1rm`, `calculate_deltas`) залишаються у фазі RED (`NotImplementedError`).
"""

from __future__ import annotations

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
        raise NotImplementedError("TDD Red Phase: math engine method not implemented")

    @staticmethod
    def calculate_deltas(
        current_volume: float,
        current_max_1rm: float | None,
        previous_volume: float | None,
        previous_max_1rm: float | None,
    ) -> tuple[bool, float | None, float | None]:
        raise NotImplementedError("TDD Red Phase: math engine method not implemented")
