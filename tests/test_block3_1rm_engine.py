"""
Автоматизовані модульні (MathEngine) та інтеграційні BDD-тести для Блоку 3 (Тікети TKT-15, TKT-17).

Покриває вимоги:
- REQ-F-011, REQ-F-012, REQ-F-013, REQ-F-021 (Розрахунок 1RM за моделями Epley/Brzycki, дефолт EPLEY, використання W_eff)
- REQ-F-014 (Попередження Soft Constraint при кількості повторень > 10)
- AC6, AC7, AC12
- BDD-004 (Soft Constraint при R=12 > 10)
- BDD-006 (Числовий еталон Epley: 100 кг × 5 повторень -> 116.66 кг через Decimal ROUND_DOWN)
- Ризики: RSK-01 (збереження точності округлення), RSK-02 (граничне значення Brzycki R=36)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.services.math_engine import MathEngine


# =====================================================================
# Допоміжні функції налаштування (ізольовані для Блоку 3)
# =====================================================================


def _seed_profile_weight(client: TestClient, weight: float = 80.0) -> dict:
    resp = client.put("/api/v1/profile", json={"current_body_weight": weight})
    assert resp.status_code == 200, f"Expected 200 setting profile weight, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_exercise(
    client: TestClient,
    name: str,
    exercise_type: str = "STANDARD",
    rm_model: str | None = None,
) -> dict:
    body: dict = {"name": name, "exercise_type": exercise_type}
    if rm_model is not None:
        body["rm_model"] = rm_model
    resp = client.post("/api/v1/exercises", json=body)
    assert resp.status_code == 201, f"Expected 201 creating exercise, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_session(client: TestClient, started_at: str | None = None) -> dict:
    body: dict = {}
    if started_at is not None:
        body["started_at"] = started_at
    resp = client.post("/api/v1/sessions", json=body)
    assert resp.status_code == 201, f"Expected 201 creating session, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_block(client: TestClient, session_id: str, exercise_id: str) -> dict:
    resp = client.post(
        f"/api/v1/sessions/{session_id}/blocks",
        json={"exercise_id": exercise_id},
    )
    assert resp.status_code == 201, f"Expected 201 creating block, got {resp.status_code}: {resp.text}"
    return resp.json()


def _post_set(
    client: TestClient,
    session_id: str,
    block_id: str,
    weight: float,
    reps: int,
    rpe: float = 8.5,
    is_warmup: bool = False,
):
    return client.post(
        f"/api/v1/sessions/{session_id}/blocks/{block_id}/sets",
        json={
            "weight": weight,
            "reps": reps,
            "rpe": rpe,
            "is_warmup": is_warmup,
        },
    )


# =====================================================================
# 1. Прямі модульні тести MathEngine.calculate_1rm (TKT-15, TKT-17)
# =====================================================================


def test_math_engine_unit_1rm_epley_and_brzycki() -> None:
    """TKT-15 (REQ-F-011..013, BDD-006, RSK-01, RSK-02): Прямі обчислення Epley і Brzycki з ROUND_DOWN."""
    # BDD-006: 100 кг × 5 повт. (Epley) -> 116.66 кг (не 116.67!)
    est_bdd, warn_bdd, msg_bdd = MathEngine.calculate_1rm(100.0, 5, "EPLEY", is_warmup=False)
    assert est_bdd == 116.66
    assert warn_bdd is False
    assert msg_bdd is None

    # Epley для гравітрона W_eff=60 кг, R=10 -> 80.0 кг
    est_grav, warn_grav, msg_grav = MathEngine.calculate_1rm(60.0, 10, "EPLEY", is_warmup=False)
    assert est_grav == 80.0
    assert warn_grav is False
    assert msg_grav is None

    # Brzycki: R=1 -> 100 * (36 / 36) = 100.0
    est_brz_1, warn_brz_1, msg_brz_1 = MathEngine.calculate_1rm(100.0, 1, "BRZYCKI", is_warmup=False)
    assert est_brz_1 == 100.0
    assert warn_brz_1 is False
    assert msg_brz_1 is None

    # Brzycki: 90 * (36 / (37 - 7)) = 90 * (36 / 30) = 108.0
    est_brz_7, warn_brz_7, msg_brz_7 = MathEngine.calculate_1rm(90.0, 7, "BRZYCKI", is_warmup=False)
    assert est_brz_7 == 108.0
    assert warn_brz_7 is False
    assert msg_brz_7 is None

    # Граничне значення Brzycki R=36 (RSK-02): 50 * 36 = 1800.0 + Soft Constraint (> 10)
    est_brz_36, warn_brz_36, msg_brz_36 = MathEngine.calculate_1rm(50.0, 36, "BRZYCKI", is_warmup=False)
    assert est_brz_36 == 1800.0
    assert warn_brz_36 is True
    assert isinstance(msg_brz_36, str) and "REQ-F-014" in msg_brz_36

    # Розминка не обчислює 1RM і не активує попередження
    est_warm, warn_warm, msg_warm = MathEngine.calculate_1rm(100.0, 12, "EPLEY", is_warmup=True)
    assert est_warm is None
    assert warn_warm is False
    assert msg_warm is None


def test_math_engine_unit_soft_constraint_warning() -> None:
    """TKT-17 (REQ-F-014, AC7, BDD-004): Межа reps == 10 (False) vs reps > 10 (True) і точність ROUND_DOWN."""
    # Межа R=10 -> попередження відсутнє, 100 * (1 + 10/30) = 133.33 (ROUND_DOWN)
    est_10, warn_10, msg_10 = MathEngine.calculate_1rm(100.0, 10, "EPLEY", is_warmup=False)
    assert est_10 == 133.33
    assert warn_10 is False
    assert msg_10 is None

    # BDD-004: R=12 (Epley) -> 140.0 + Soft Constraint
    est_12, warn_12, msg_12 = MathEngine.calculate_1rm(100.0, 12, "EPLEY", is_warmup=False)
    assert est_12 == 140.0
    assert warn_12 is True
    assert isinstance(msg_12, str) and "REQ-F-014" in msg_12

    # Brzycki при R=11: 80 * (36 / 26) = 110.76923... -> ROUND_DOWN = 110.76 + Soft Constraint
    est_11, warn_11, msg_11 = MathEngine.calculate_1rm(80.0, 11, "BRZYCKI", is_warmup=False)
    assert est_11 == 110.76
    assert warn_11 is True
    assert isinstance(msg_11, str) and "REQ-F-014" in msg_11


# =====================================================================
# 2. Інтеграційні тести Epley / Brzycki / AC12 / PATCH (TKT-15)
# =====================================================================


def test_bdd_006_epley_1rm_benchmark_100kg_5reps(client: TestClient) -> None:
    """
    BDD-006 (REQ-F-011, REQ-F-013, AC6, RSK-01):
    Стандартна вправа з моделлю за замовчуванням EPLEY: 100 кг × 5 повт. -> 116.66 кг.
    """
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    assert squat["rm_model"] == "EPLEY"

    session = _create_session(client, started_at="2026-09-15T18:00:00Z")
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=100.0,
        reps=5,
        rpe=8.5,
        is_warmup=False,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["set"]["estimated_1rm"] == 116.66
    assert body["set"]["soft_constraint_warning"] is False
    assert body["set"]["warning_message"] is None
    assert body["block_summary"]["block_max_1rm"] == 116.66

    # Перевірка через GET block та GET session
    blk_detail = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}").json()
    assert blk_detail["block_max_1rm"] == 116.66
    assert blk_detail["sets"][0]["estimated_1rm"] == 116.66

    ses_detail = client.get(f"/api/v1/sessions/{session['session_id']}").json()
    assert ses_detail["blocks"][0]["block_max_1rm"] == 116.66
    assert ses_detail["blocks"][0]["sets"][0]["estimated_1rm"] == 116.66


def test_ac12_effective_weight_in_1rm_for_assisted_and_bodyweight(client: TestClient) -> None:
    """
    AC12 (REQ-F-021):
    У розрахунку 1RM використовується ефективна вага W_eff:
    - ASSISTED (снапшот 80, weight=-20, reps=10, EPLEY) -> W_eff=60.0 -> 1RM=80.0;
    - BODYWEIGHT (снапшот 80, weight=+10, reps=6, EPLEY) -> W_eff=90.0 -> 1RM=108.0.
    """
    _seed_profile_weight(client, 80.0)
    gravitron = _create_exercise(client, name="Підтягування у гравітроні", exercise_type="ASSISTED")
    dips = _create_exercise(client, name="Віджимання на брусах", exercise_type="BODYWEIGHT")
    session = _create_session(client, started_at="2026-09-16T18:00:00Z")

    blk_ast = _create_block(client, session["session_id"], gravitron["exercise_id"])
    resp_ast = _post_set(
        client,
        session["session_id"],
        blk_ast["block_id"],
        weight=-20.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert resp_ast.status_code == 201
    ast_body = resp_ast.json()
    assert ast_body["set"]["effective_weight"] == 60.0
    assert ast_body["set"]["estimated_1rm"] == 80.0
    assert ast_body["block_summary"]["block_max_1rm"] == 80.0

    blk_bw = _create_block(client, session["session_id"], dips["exercise_id"])
    resp_bw = _post_set(
        client,
        session["session_id"],
        blk_bw["block_id"],
        weight=10.0,
        reps=6,
        rpe=8.5,
        is_warmup=False,
    )
    assert resp_bw.status_code == 201
    bw_body = resp_bw.json()
    assert bw_body["set"]["effective_weight"] == 90.0
    assert bw_body["set"]["estimated_1rm"] == 108.0
    assert bw_body["block_summary"]["block_max_1rm"] == 108.0


def test_update_exercise_model_patch_and_brzycki_calculation(client: TestClient) -> None:
    """
    REQ-F-012, AC6, RSK-02:
    PATCH /api/v1/exercises/{exerciseId} перемикає модель на BRZYCKI,
    після чого підходи рахуються за формулою Brzycki, включно з R=1 і R=36.
    """
    _seed_profile_weight(client, 80.0)
    bench = _create_exercise(client, name="Жим штанги лежачи", exercise_type="STANDARD")
    assert bench["rm_model"] == "EPLEY"

    patch_resp = client.patch(
        f"/api/v1/exercises/{bench['exercise_id']}",
        json={"rm_model": "BRZYCKI"},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["exercise_id"] == bench["exercise_id"]
    assert patched["rm_model"] == "BRZYCKI"
    assert patched["updated_at"] is not None

    get_ex = client.get(f"/api/v1/exercises/{bench['exercise_id']}")
    assert get_ex.status_code == 200
    assert get_ex.json()["rm_model"] == "BRZYCKI"

    session = _create_session(client, started_at="2026-09-17T18:00:00Z")
    block = _create_block(client, session["session_id"], bench["exercise_id"])
    assert block["rm_model"] == "BRZYCKI"

    # R=1 -> 100 * (36 / 36) = 100.0
    s1 = _post_set(client, session["session_id"], block["block_id"], weight=100.0, reps=1, rpe=9.5)
    assert s1.status_code == 201
    assert s1.json()["set"]["estimated_1rm"] == 100.0
    assert s1.json()["block_summary"]["block_max_1rm"] == 100.0

    # R=7 -> 90 * (36 / 30) = 108.0
    s2 = _post_set(client, session["session_id"], block["block_id"], weight=90.0, reps=7, rpe=8.5)
    assert s2.status_code == 201
    assert s2.json()["set"]["estimated_1rm"] == 108.0
    assert s2.json()["block_summary"]["block_max_1rm"] == 108.0

    # Граничний R=36 -> 50 * (36 / 1) = 1800.0 + Soft Constraint
    s3 = _post_set(client, session["session_id"], block["block_id"], weight=50.0, reps=36, rpe=9.5)
    assert s3.status_code == 201
    s3_body = s3.json()
    assert s3_body["set"]["estimated_1rm"] == 1800.0
    assert s3_body["set"]["soft_constraint_warning"] is True
    assert s3_body["block_summary"]["block_max_1rm"] == 1800.0


def test_update_exercise_model_not_found_and_bad_request(client: TestClient) -> None:
    """REQ-F-012: Невалідний enum rm_model -> 400 ERR_BAD_REQUEST; неіснуюча вправа -> 404 ERR_RESOURCE_NOT_FOUND."""
    ex = _create_exercise(client, name="Тяга гантелі", exercise_type="STANDARD")

    bad_model = client.patch(
        f"/api/v1/exercises/{ex['exercise_id']}",
        json={"rm_model": "LOMBARDI"},
    )
    assert bad_model.status_code == 400
    assert bad_model.json()["error"]["code"] == "ERR_BAD_REQUEST"

    missing_ex = client.patch(
        "/api/v1/exercises/ex-nonexistent-999",
        json={"rm_model": "BRZYCKI"},
    )
    assert missing_ex.status_code == 404
    assert missing_ex.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"


def test_warmup_ignored_and_block_max_1rm_recalculation_on_delete(client: TestClient) -> None:
    """
    REQ-F-011, AC6:
    Розминочний підхід дає estimated_1rm = null (block_max_1rm = null);
    block_max_1rm відповідає максимуму серед робочих підходів і перераховується після DELETE.
    """
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання фронтальні", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    # Розминка на 12 повт. -> 1RM не рахується, попередження Soft Constraint не спрацьовує
    warm = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=60.0,
        reps=12,
        rpe=6.5,
        is_warmup=True,
    )
    assert warm.status_code == 201
    warm_body = warm.json()
    assert warm_body["set"]["estimated_1rm"] is None
    assert warm_body["set"]["soft_constraint_warning"] is False
    assert warm_body["set"]["warning_message"] is None
    assert warm_body["block_summary"]["block_max_1rm"] is None

    # Робочий підхід 1: 100 × 5 -> 116.66
    s1 = _post_set(client, session["session_id"], block["block_id"], weight=100.0, reps=5, rpe=8.0)
    assert s1.status_code == 201
    assert s1.json()["set"]["estimated_1rm"] == 116.66
    assert s1.json()["block_summary"]["block_max_1rm"] == 116.66
    s1_id = s1.json()["set"]["set_id"]

    # Робочий підхід 2: 110 × 5 -> 128.33 (новий максимум блоку)
    s2 = _post_set(client, session["session_id"], block["block_id"], weight=110.0, reps=5, rpe=9.0)
    assert s2.status_code == 201
    assert s2.json()["set"]["estimated_1rm"] == 128.33
    assert s2.json()["block_summary"]["block_max_1rm"] == 128.33
    s2_id = s2.json()["set"]["set_id"]

    # Видаляємо s2 -> максимум блоку повертається до 116.66
    del_2 = client.delete(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets/{s2_id}")
    assert del_2.status_code == 200
    assert del_2.json()["block_summary"]["block_max_1rm"] == 116.66

    # Видаляємо s1 -> лишається лише розминка, block_max_1rm стає null
    del_1 = client.delete(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets/{s1_id}")
    assert del_1.status_code == 200
    assert del_1.json()["block_summary"]["block_max_1rm"] is None


# =====================================================================
# 3. Інтеграційні тести Soft Constraint Warning (TKT-17, BDD-004)
# =====================================================================


def test_bdd_004_soft_constraint_warning_reps_over_10(client: TestClient) -> None:
    """
    BDD-004 (REQ-F-014, AC7):
    При reps=10 прапорець soft_constraint_warning=False (warning_message=None);
    при reps=12 (> 10) система обчислює estimated_1rm=140.0 і повертає
    soft_constraint_warning=True з інформативним warning_message (REQ-F-014).
    """
    _seed_profile_weight(client, 80.0)
    leg_press = _create_exercise(client, name="Жим ногами в тренажері", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], leg_press["exercise_id"])

    # R=10 -> немає попередження
    s_10 = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=90.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert s_10.status_code == 201
    b_10 = s_10.json()
    assert b_10["set"]["estimated_1rm"] == 120.0
    assert b_10["set"]["soft_constraint_warning"] is False
    assert b_10["set"]["warning_message"] is None

    # R=12 (BDD-004) -> 100 * (1 + 12/30) = 140.0 + soft_constraint_warning=True
    s_12 = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=100.0,
        reps=12,
        rpe=9.0,
        is_warmup=False,
    )
    assert s_12.status_code == 201
    b_12 = s_12.json()
    assert b_12["set"]["estimated_1rm"] == 140.0
    assert b_12["set"]["soft_constraint_warning"] is True
    assert isinstance(b_12["set"]["warning_message"], str)
    assert "REQ-F-014" in b_12["set"]["warning_message"]
    assert b_12["block_summary"]["block_max_1rm"] == 140.0

    # Повторне читання блоку зберігає soft_constraint_warning та warning_message
    blk_after = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}").json()
    assert blk_after["sets"][0]["soft_constraint_warning"] is False
    assert blk_after["sets"][1]["soft_constraint_warning"] is True
    assert "REQ-F-014" in blk_after["sets"][1]["warning_message"]
