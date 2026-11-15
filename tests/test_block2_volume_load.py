"""
Автоматизовані модульні (MathEngine) та інтеграційні BDD-тести для Блоку 2 (Тікети TKT-08, TKT-10).

Покриває вимоги:
- REQ-F-006, REQ-F-007, REQ-F-008 (Volume Load для STANDARD, ізоляція блоків, ігнорування розминки)
- REQ-F-009, REQ-F-010, REQ-F-021 (Ефективна вага W_eff та Volume Load для BODYWEIGHT і ASSISTED)
- AC3, AC4, AC5
- BDD-001 (повна незмінність розрахунків Volume Load при зміні маси тіла в профілі)
- BDD-002 (Вправи з компенсацією ваги — гравітрон)
- BDD-003 (Ігнорування розминочних підходів у Volume Load)
- Ризики: RSK-06 (цілісність снапшота), RSK-07 (знак ваги для трьох типів вправ), RSK-09 (ізоляція блоків)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.services.math_engine import MathEngine


# =====================================================================
# Допоміжні функції налаштування (ізольовані для Блоку 2)
# =====================================================================


def _seed_profile_weight(client: TestClient, weight: float = 80.0) -> dict:
    resp = client.put("/api/v1/profile", json={"current_body_weight": weight})
    assert resp.status_code == 200, f"Expected 200 setting profile weight, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_exercise(
    client: TestClient,
    name: str,
    exercise_type: str = "STANDARD",
) -> dict:
    resp = client.post(
        "/api/v1/exercises",
        json={"name": name, "exercise_type": exercise_type},
    )
    assert resp.status_code == 201, f"Expected 201 creating exercise, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_session(
    client: TestClient,
    started_at: str | None = None,
    notes: str | None = None,
) -> dict:
    body: dict = {}
    if started_at is not None:
        body["started_at"] = started_at
    if notes is not None:
        body["notes"] = notes
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
    rpe: float = 8.0,
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
# 1. Прямі модульні тести MathEngine (TKT-08, TKT-10)
# =====================================================================


def test_math_engine_unit_standard_and_warmup() -> None:
    """TKT-08 (REQ-F-006..008, REQ-F-021): Прямий розрахунок W_eff = W та Volume Load з урахуванням розминки."""
    w_eff = MathEngine.calculate_effective_weight("STANDARD", 100.0, 80.0)
    assert w_eff == pytest.approx(100.0)

    vl_working = MathEngine.calculate_set_volume_load(w_eff, 5, is_warmup=False)
    assert vl_working == pytest.approx(500.0)

    vl_warmup = MathEngine.calculate_set_volume_load(60.0, 10, is_warmup=True)
    assert vl_warmup == pytest.approx(0.0)


def test_math_engine_unit_bodyweight_and_assisted() -> None:
    """TKT-10 (REQ-F-009, REQ-F-010, REQ-F-021): Розрахунок W_eff та Volume Load для BODYWEIGHT і ASSISTED."""
    # BODYWEIGHT з додатковою вагою (+15 кг) при масі тіла 80 кг -> 95 * 8 = 760
    w_eff_bw_weighted = MathEngine.calculate_effective_weight("BODYWEIGHT", 15.0, 80.0)
    assert w_eff_bw_weighted == pytest.approx(95.0)
    assert MathEngine.calculate_set_volume_load(w_eff_bw_weighted, 8, is_warmup=False) == pytest.approx(760.0)

    # BODYWEIGHT без додаткової ваги (0 кг) при масі тіла 80 кг -> 80 * 10 = 800
    w_eff_bw_plain = MathEngine.calculate_effective_weight("BODYWEIGHT", 0.0, 80.0)
    assert w_eff_bw_plain == pytest.approx(80.0)
    assert MathEngine.calculate_set_volume_load(w_eff_bw_plain, 10, is_warmup=False) == pytest.approx(800.0)

    # ASSISTED (компенсація -20 кг) при масі тіла 80 кг -> 60 * 10 = 600
    w_eff_assisted = MathEngine.calculate_effective_weight("ASSISTED", -20.0, 80.0)
    assert w_eff_assisted == pytest.approx(60.0)
    assert MathEngine.calculate_set_volume_load(w_eff_assisted, 10, is_warmup=False) == pytest.approx(600.0)

    # Розминка в ASSISTED повертає 0.0
    assert MathEngine.calculate_set_volume_load(50.0, 8, is_warmup=True) == pytest.approx(0.0)


# =====================================================================
# 2. STANDARD Volume Load, BDD-003 та ізоляція блоків RSK-09 (TKT-08)
# =====================================================================


def test_bdd_003_standard_volume_load_ignores_warmup(client: TestClient) -> None:
    """
    BDD-003 (REQ-F-007, REQ-F-008, AC3, AC4):
    Розминочний підхід (60 кг × 10, is_warmup=True) дає set_volume_load == 0.0;
    робочий підхід (100 кг × 5, is_warmup=False) дає 500.0;
    сумарний block_volume_load == 500.0 кг.
    """
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    session = _create_session(client, started_at="2026-09-10T18:00:00Z")
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    warmup_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=60.0,
        reps=10,
        rpe=6.0,
        is_warmup=True,
    )
    assert warmup_resp.status_code == 201
    warmup_body = warmup_resp.json()
    assert warmup_body["set"]["effective_weight"] == pytest.approx(60.0)
    assert warmup_body["set"]["set_volume_load"] == pytest.approx(0.0)
    assert warmup_body["block_summary"]["block_volume_load"] == pytest.approx(0.0)

    working_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=100.0,
        reps=5,
        rpe=8.5,
        is_warmup=False,
    )
    assert working_resp.status_code == 201
    working_body = working_resp.json()
    assert working_body["set"]["effective_weight"] == pytest.approx(100.0)
    assert working_body["set"]["set_volume_load"] == pytest.approx(500.0)
    assert working_body["block_summary"]["block_volume_load"] == pytest.approx(500.0)

    # Перевірка консистентності через GET block та GET session
    blk_detail = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}").json()
    assert blk_detail["block_volume_load"] == pytest.approx(500.0)
    assert blk_detail["sets"][0]["set_volume_load"] == pytest.approx(0.0)
    assert blk_detail["sets"][1]["set_volume_load"] == pytest.approx(500.0)

    ses_detail = client.get(f"/api/v1/sessions/{session['session_id']}").json()
    assert ses_detail["blocks"][0]["block_volume_load"] == pytest.approx(500.0)


def test_isolated_blocks_volume_load_and_set_deletion(client: TestClient) -> None:
    """
    REQ-F-006, AC3, RSK-09:
    Два блоки тієї самої вправи в одній сесії агрегують Volume Load незалежно;
    видалення підходу перераховує block_volume_load тільки відповідного блоку.
    """
    _seed_profile_weight(client, 80.0)
    bench = _create_exercise(client, name="Жим штанги лежачи", exercise_type="STANDARD")
    session = _create_session(client, started_at="2026-09-11T18:00:00Z")

    blk_1 = _create_block(client, session["session_id"], bench["exercise_id"])
    blk_2 = _create_block(client, session["session_id"], bench["exercise_id"])

    # Блок 1: 80×10 (800.0) + 90×5 (450.0) -> 1250.0
    s1 = _post_set(client, session["session_id"], blk_1["block_id"], weight=80.0, reps=10, rpe=8.0)
    assert s1.status_code == 201
    assert s1.json()["set"]["set_volume_load"] == pytest.approx(800.0)
    assert s1.json()["block_summary"]["block_volume_load"] == pytest.approx(800.0)

    s2 = _post_set(client, session["session_id"], blk_1["block_id"], weight=90.0, reps=5, rpe=9.0)
    assert s2.status_code == 201
    assert s2.json()["set"]["set_volume_load"] == pytest.approx(450.0)
    assert s2.json()["block_summary"]["block_volume_load"] == pytest.approx(1250.0)
    s2_id = s2.json()["set"]["set_id"]

    # Блок 2 (та сама вправа): 60×10 (600.0), не додається до блоку 1
    s3 = _post_set(client, session["session_id"], blk_2["block_id"], weight=60.0, reps=10, rpe=7.5)
    assert s3.status_code == 201
    assert s3.json()["block_summary"]["block_volume_load"] == pytest.approx(600.0)

    # Видаляємо s2 з blk_1 -> blk_1 стає 800.0, blk_2 лишається 600.0
    del_resp = client.delete(f"/api/v1/sessions/{session['session_id']}/blocks/{blk_1['block_id']}/sets/{s2_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["block_summary"]["block_volume_load"] == pytest.approx(800.0)

    ses_detail = client.get(f"/api/v1/sessions/{session['session_id']}").json()
    blocks_by_id = {b["block_id"]: b for b in ses_detail["blocks"]}
    assert blocks_by_id[blk_1["block_id"]]["block_volume_load"] == pytest.approx(800.0)
    assert blocks_by_id[blk_2["block_id"]]["block_volume_load"] == pytest.approx(600.0)


# =====================================================================
# 3. BODYWEIGHT & ASSISTED Volume Load, BDD-001, BDD-002, RSK-07 (TKT-10)
# =====================================================================


def test_bdd_002_assisted_gravitron_volume_load(client: TestClient) -> None:
    """
    BDD-002 (REQ-F-010, REQ-F-021, AC5):
    Снапшот 80.0 кг, ASSISTED (гравітрон), weight=-20.0, reps=10 -> W_eff=60.0, VL=600.0.
    Розминочний підхід із weight=-30.0 дає W_eff=50.0 та VL=0.0.
    """
    _seed_profile_weight(client, 80.0)
    gravitron = _create_exercise(client, name="Підтягування у гравітроні", exercise_type="ASSISTED")
    session = _create_session(client, started_at="2026-09-12T18:00:00Z")
    block = _create_block(client, session["session_id"], gravitron["exercise_id"])

    work_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=-20.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert work_resp.status_code == 201
    work_body = work_resp.json()
    assert work_body["set"]["effective_weight"] == pytest.approx(60.0)
    assert work_body["set"]["set_volume_load"] == pytest.approx(600.0)
    assert work_body["block_summary"]["block_volume_load"] == pytest.approx(600.0)

    warmup_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=-30.0,
        reps=8,
        rpe=6.5,
        is_warmup=True,
    )
    assert warmup_resp.status_code == 201
    warmup_body = warmup_resp.json()
    assert warmup_body["set"]["effective_weight"] == pytest.approx(50.0)
    assert warmup_body["set"]["set_volume_load"] == pytest.approx(0.0)
    assert warmup_body["block_summary"]["block_volume_load"] == pytest.approx(600.0)


def test_bodyweight_with_and_without_extra_weight(client: TestClient) -> None:
    """
    REQ-F-009, REQ-F-021, AC5:
    BODYWEIGHT при снапшоті 80.0 кг:
    - із додатковою вагою +15.0 × 8 -> W_eff=95.0, set_volume_load=760.0;
    - без додаткової ваги 0.0 × 10 -> W_eff=80.0, set_volume_load=800.0;
    - сумарний block_volume_load == 1560.0.
    """
    _seed_profile_weight(client, 80.0)
    pullups = _create_exercise(client, name="Підтягування на турніку", exercise_type="BODYWEIGHT")
    session = _create_session(client, started_at="2026-09-13T18:00:00Z")
    block = _create_block(client, session["session_id"], pullups["exercise_id"])

    weighted_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=15.0,
        reps=8,
        rpe=8.5,
        is_warmup=False,
    )
    assert weighted_resp.status_code == 201
    w_body = weighted_resp.json()
    assert w_body["set"]["effective_weight"] == pytest.approx(95.0)
    assert w_body["set"]["set_volume_load"] == pytest.approx(760.0)
    assert w_body["block_summary"]["block_volume_load"] == pytest.approx(760.0)

    plain_resp = _post_set(
        client,
        session["session_id"],
        block["block_id"],
        weight=0.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert plain_resp.status_code == 201
    p_body = plain_resp.json()
    assert p_body["set"]["effective_weight"] == pytest.approx(80.0)
    assert p_body["set"]["set_volume_load"] == pytest.approx(800.0)
    assert p_body["block_summary"]["block_volume_load"] == pytest.approx(1560.0)


def test_bdd_001_full_volume_load_immutability_after_profile_update(client: TestClient) -> None:
    """
    BDD-001 (REQ-F-002, REQ-F-009, REQ-F-019, RSK-06):
    Стара сесія зі снапшотом 80.0 кг та новими підходами в ній завжди рахує W_eff від 80.0 кг,
    навіть після оновлення current_body_weight у профілі до 85.0 кг.
    Нова сесія використовує новий снапшот 85.0 кг.
    """
    _seed_profile_weight(client, 80.0)
    dips = _create_exercise(client, name="Віджимання на брусах", exercise_type="BODYWEIGHT")

    old_session = _create_session(client, started_at="2026-09-01T18:00:00Z", notes="Минула сесія")
    old_block = _create_block(client, old_session["session_id"], dips["exercise_id"])

    old_set1 = _post_set(
        client,
        old_session["session_id"],
        old_block["block_id"],
        weight=10.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert old_set1.status_code == 201
    assert old_set1.json()["set"]["effective_weight"] == pytest.approx(90.0)
    assert old_set1.json()["set"]["set_volume_load"] == pytest.approx(900.0)

    # Оновлюємо масу тіла в профілі до 85.0 кг
    _seed_profile_weight(client, 85.0)

    # Існуюча сесія не змінилася
    reloaded_old = client.get(f"/api/v1/sessions/{old_session['session_id']}").json()
    assert reloaded_old["body_weight_snapshot"] == pytest.approx(80.0)
    assert reloaded_old["blocks"][0]["block_volume_load"] == pytest.approx(900.0)

    # Додавання ще одного підходу в стару сесію все одно бере її снапшот 80.0 кг
    old_set2 = _post_set(
        client,
        old_session["session_id"],
        old_block["block_id"],
        weight=0.0,
        reps=10,
        rpe=8.5,
        is_warmup=False,
    )
    assert old_set2.status_code == 201
    assert old_set2.json()["set"]["effective_weight"] == pytest.approx(80.0)
    assert old_set2.json()["set"]["set_volume_load"] == pytest.approx(800.0)
    assert old_set2.json()["block_summary"]["block_volume_load"] == pytest.approx(1700.0)

    # Нова сесія бере новий снапшот 85.0 кг
    new_session = _create_session(client, started_at="2026-09-15T18:00:00Z", notes="Нова сесія")
    new_block = _create_block(client, new_session["session_id"], dips["exercise_id"])
    new_set = _post_set(
        client,
        new_session["session_id"],
        new_block["block_id"],
        weight=0.0,
        reps=10,
        rpe=8.0,
        is_warmup=False,
    )
    assert new_set.status_code == 201
    assert new_set.json()["set"]["effective_weight"] == pytest.approx(85.0)
    assert new_set.json()["set"]["set_volume_load"] == pytest.approx(850.0)


# =====================================================================
# 4. Негативні доменні сценарії знака ваги 422 (RSK-07, spec/openapi.yaml)
# =====================================================================


@pytest.mark.parametrize("invalid_weight", [0.0, -10.0])
def test_standard_non_positive_weight_rejected_422(client: TestClient, invalid_weight: float) -> None:
    """RSK-07: Для STANDARD значення weight <= 0 повертає 422 ERR_NEGATIVE_WEIGHT_NOT_ALLOWED."""
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Станова тяга", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    resp = _post_set(client, session["session_id"], block["block_id"], weight=invalid_weight, reps=5, rpe=8.0)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_NEGATIVE_WEIGHT_NOT_ALLOWED"
    assert err["http_status"] == 422


def test_bodyweight_negative_weight_rejected_422(client: TestClient) -> None:
    """RSK-07: Для BODYWEIGHT від'ємна вага (-5.0) повертає 422 ERR_NEGATIVE_WEIGHT_NOT_ALLOWED."""
    _seed_profile_weight(client, 80.0)
    pullups = _create_exercise(client, name="Підтягування широким хватом", exercise_type="BODYWEIGHT")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], pullups["exercise_id"])

    resp = _post_set(client, session["session_id"], block["block_id"], weight=-5.0, reps=8, rpe=8.0)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_NEGATIVE_WEIGHT_NOT_ALLOWED"
    assert err["http_status"] == 422


def test_assisted_positive_weight_rejected_422(client: TestClient) -> None:
    """RSK-07: Для ASSISTED додатна вага (+10.0) повертає 422 ERR_POSITIVE_WEIGHT_IN_ASSISTED."""
    _seed_profile_weight(client, 80.0)
    gravitron = _create_exercise(client, name="Бруси у гравітроні", exercise_type="ASSISTED")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], gravitron["exercise_id"])

    resp = _post_set(client, session["session_id"], block["block_id"], weight=10.0, reps=8, rpe=8.0)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_POSITIVE_WEIGHT_IN_ASSISTED"
    assert err["http_status"] == 422


@pytest.mark.parametrize("invalid_assist", [-80.0, -85.0])
def test_assisted_non_positive_effective_load_rejected_422(client: TestClient, invalid_assist: float) -> None:
    """RSK-07: Для ASSISTED компенсація >= маси тіла (W_eff <= 0) повертає 422 ERR_NON_POSITIVE_EFFECTIVE_LOAD."""
    _seed_profile_weight(client, 80.0)
    gravitron = _create_exercise(client, name="Гравітрон зворотній хват", exercise_type="ASSISTED")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], gravitron["exercise_id"])

    resp = _post_set(client, session["session_id"], block["block_id"], weight=invalid_assist, reps=8, rpe=8.0)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_NON_POSITIVE_EFFECTIVE_LOAD"
    assert err["http_status"] == 422
