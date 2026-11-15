"""
Каркас математичного рушія (Math Engine) для розрахунку:
- Volume Load (REQ-F-006 – REQ-F-010, REQ-F-021)
- 1RM за формулами Epley та Brzycki (REQ-F-011 – REQ-F-014, REQ-F-021)
- Аналітичної Дельти прогресії (REQ-F-015 – REQ-F-018, REQ-F-021)

ВАЖЛИВО (SDD / TDD Red Phase Skeleton):
Реалізація формул суворо заборонена до написання та проходження TEST-GATE.
Усі методи є суворими заглушками, що піднімають `NotImplementedError`.
"""

from __future__ import annotations


class MathEngine:
    """Заглушка математичного ядра системи (TDD Red Phase)."""

    @staticmethod
    def calculate_effective_weight(
        exercise_type: str, weight: float, body_weight_snapshot: float
    ) -> float:
        raise NotImplementedError("TDD Red Phase: math engine method not implemented")

    @staticmethod
    def calculate_set_volume_load(
        effective_weight: float, reps: int, is_warmup: bool
    ) -> float:
        raise NotImplementedError("TDD Red Phase: math engine method not implemented")

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
