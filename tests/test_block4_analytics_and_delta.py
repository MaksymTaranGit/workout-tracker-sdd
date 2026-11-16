"""
Автоматизовані модульні (MathEngine) та інтеграційні BDD-тести для Блоку 4 (Тікети TKT-22, TKT-24).

Покриває вимоги:
- REQ-F-015, REQ-F-016, REQ-F-018, REQ-F-021 (Дельта Volume Load та 1RM відносно останнього
  хронологічного блоку з щонайменше одним робочим підходом, відсутність дельти для першого виконання)
- REQ-F-017, REQ-NF-002 (Аналітичний дашборд вправи з часовим рядом data_points, фільтри та продуктивність < 1 с)
- AC8, AC9, AC12
- BDD-005 (Розрахунок Дельти за 3 хронологічними сесіями: 3000 -> 3200 -> 3300 кг)
- BDD-007 (Побудова аналітичного графіка прогресії за даними GET /api/v1/exercises/{exerciseId}/analytics)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.services.math_engine import MathEngine


# =====================================================================
# Допоміжні функції налаштування (ізольовані для Блоку 4)
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


def _create_session(client: TestClient, started_at: str) -> dict:
    resp = client.post("/api/v1/sessions", json={"started_at": started_at})
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
) -> dict:
    resp = client.post(
        f"/api/v1/sessions/{session_id}/blocks/{block_id}/sets",
        json={
            "weight": weight,
            "reps": reps,
            "rpe": rpe,
            "is_warmup": is_warmup,
        },
    )
    assert resp.status_code == 201, f"Expected 201 creating set, got {resp.status_code}: {resp.text}"
    return resp.json()


# =====================================================================
# 1. Модульні та інтеграційні тести Дельти (TKT-22)
# =====================================================================


def test_math_engine_unit_calculate_deltas() -> None:
    """TKT-22 (REQ-F-015, REQ-F-016, REQ-F-018): Прямі обчислення Дельти через MathEngine."""
    # Перше виконання (попередня база відсутня) -> (False, None, None)
    assert MathEngine.calculate_deltas(3000.0, 250.0, None, None) == (False, None, None)

    # Позитивна прогресія -> (True, +100.0, +5.0)
    assert MathEngine.calculate_deltas(3300.0, 195.0, 3200.0, 190.0) == (True, 100.0, 5.0)

    # Від'ємна прогресія з Decimal-точністю без float-артефактів
    has_base, vl_delta, rm_delta = MathEngine.calculate_deltas(
        1150.3, 112.1, 1200.2, 116.66
    )
    assert has_base is True
    assert vl_delta == -49.9
    assert rm_delta == -4.56

    # Поточний блок без робочих підходів (current_max_1rm is None) -> не формує дельту
    assert MathEngine.calculate_deltas(0.0, None, 3000.0, 250.0) == (False, None, None)


def test_bdd_005_three_chronological_sessions_delta(client: TestClient) -> None:
    """
    BDD-005 (REQ-F-015, REQ-F-016, REQ-F-018, AC8):
    Станова тяга за 3 хронологічними сесіями:
    - 1 вересня: VL=3000.0, 1RM=250.0 -> has_previous_baseline=False, deltas=None;
    - 8 вересня: VL=3200.0, 1RM=266.66 -> vl_delta=+200.0, max_1rm_delta=+16.66;
    - 15 вересня: VL=3300.0, 1RM=275.0 -> vl_delta=+100.0 (суворо відносно 8 вересня), max_1rm_delta=+8.34.
    """
    _seed_profile_weight(client, 80.0)
    deadlift = _create_exercise(client, name="Станова тяга", exercise_type="STANDARD")

    # Сесія 1 (2026-09-01): 150 × 20 -> VL=3000.0, 1RM=250.0
    s1 = _create_session(client, "2026-09-01T18:00:00Z")
    b1 = _create_block(client, s1["session_id"], deadlift["exercise_id"])
    r1 = _post_set(client, s1["session_id"], b1["block_id"], weight=150.0, reps=20, rpe=8.0)
    assert r1["block_summary"]["block_volume_load"] == 3000.0
    assert r1["block_summary"]["block_max_1rm"] == 250.0
    assert r1["block_summary"]["has_previous_baseline"] is False
    assert r1["block_summary"]["volume_load_delta"] is None
    assert r1["block_summary"]["max_1rm_delta"] is None

    # Сесія 2 (2026-09-08): 160 × 20 -> VL=3200.0, 1RM=266.66
    s2 = _create_session(client, "2026-09-08T18:00:00Z")
    b2 = _create_block(client, s2["session_id"], deadlift["exercise_id"])
    r2 = _post_set(client, s2["session_id"], b2["block_id"], weight=160.0, reps=20, rpe=8.5)
    assert r2["block_summary"]["block_volume_load"] == 3200.0
    assert r2["block_summary"]["block_max_1rm"] == 266.66
    assert r2["block_summary"]["has_previous_baseline"] is True
    assert r2["block_summary"]["volume_load_delta"] == 200.0
    assert r2["block_summary"]["max_1rm_delta"] == 16.66

    # Сесія 3 (2026-09-15): 165 × 20 -> VL=3300.0, 1RM=275.0
    s3 = _create_session(client, "2026-09-15T18:00:00Z")
    b3 = _create_block(client, s3["session_id"], deadlift["exercise_id"])
    r3 = _post_set(client, s3["session_id"], b3["block_id"], weight=165.0, reps=20, rpe=9.0)
    assert r3["block_summary"]["block_volume_load"] == 3300.0
    assert r3["block_summary"]["block_max_1rm"] == 275.0
    assert r3["block_summary"]["has_previous_baseline"] is True
    assert r3["block_summary"]["volume_load_delta"] == 100.0
    assert r3["block_summary"]["max_1rm_delta"] == 8.34

    # Консистентність через GET block і GET session
    blk3_get = client.get(f"/api/v1/sessions/{s3['session_id']}/blocks/{b3['block_id']}").json()
    assert blk3_get["has_previous_baseline"] is True
    assert blk3_get["volume_load_delta"] == 100.0
    assert blk3_get["max_1rm_delta"] == 8.34

    ses3_get = client.get(f"/api/v1/sessions/{s3['session_id']}").json()
    assert ses3_get["blocks"][0]["volume_load_delta"] == 100.0
    assert ses3_get["blocks"][0]["max_1rm_delta"] == 8.34


def test_ac12_chronological_baseline_ignores_warmup_only_and_empty_blocks(client: TestClient) -> None:
    """
    REQ-F-021, AC12:
    Порожній блок та блок лише з розминочними підходами (is_warmup=True) НЕ стають базою порівняння.
    Наступний робочий блок порівнюється з останнім попереднім блоком, що мав робочі підходи.
    """
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")

    # Сесія 1 (2026-09-01): робочий блок 100 × 10 -> VL=1000.0, 1RM=133.33
    s1 = _create_session(client, "2026-09-01T18:00:00Z")
    b1 = _create_block(client, s1["session_id"], squat["exercise_id"])
    _post_set(client, s1["session_id"], b1["block_id"], weight=100.0, reps=10, rpe=8.0, is_warmup=False)

    # Сесія 2 (2026-09-05): блок лише з розминкою + порожній блок
    s2 = _create_session(client, "2026-09-05T18:00:00Z")
    b_warm = _create_block(client, s2["session_id"], squat["exercise_id"])
    r_warm = _post_set(
        client, s2["session_id"], b_warm["block_id"], weight=60.0, reps=10, rpe=6.0, is_warmup=True
    )
    assert r_warm["block_summary"]["has_previous_baseline"] is False
    assert r_warm["block_summary"]["volume_load_delta"] is None
    assert r_warm["block_summary"]["max_1rm_delta"] is None

    b_empty = _create_block(client, s2["session_id"], squat["exercise_id"])
    b_empty_get = client.get(f"/api/v1/sessions/{s2['session_id']}/blocks/{b_empty['block_id']}").json()
    assert b_empty_get["has_previous_baseline"] is False
    assert b_empty_get["volume_load_delta"] is None

    # Сесія 3 (2026-09-10): робочий блок 110 × 10 -> VL=1100.0, 1RM=146.66
    # Повинен порівнюватись із Сесією 1, ігноруючи розминочний та порожній блоки Сесії 2
    s3 = _create_session(client, "2026-09-10T18:00:00Z")
    b3 = _create_block(client, s3["session_id"], squat["exercise_id"])
    r3 = _post_set(client, s3["session_id"], b3["block_id"], weight=110.0, reps=10, rpe=8.5, is_warmup=False)
    assert r3["block_summary"]["has_previous_baseline"] is True
    assert r3["block_summary"]["volume_load_delta"] == 100.0
    assert r3["block_summary"]["max_1rm_delta"] == 13.33


def test_same_session_multiple_blocks_order_index_and_delete_recalculation(client: TestClient) -> None:
    """
    REQ-F-015, REQ-F-021, AC8, AC12, RSK-09:
    Хронологія в межах однієї сесії визначається за order_index;
    DELETE .../sets/{setId} перераховує volume_load_delta та max_1rm_delta.
    """
    _seed_profile_weight(client, 80.0)
    bench = _create_exercise(client, name="Жим штанги лежачи", exercise_type="STANDARD")
    session = _create_session(client, "2026-09-18T18:00:00Z")

    # Блок 1 (order_index=1): 100 × 5 -> VL=500.0, 1RM=116.66
    b1 = _create_block(client, session["session_id"], bench["exercise_id"])
    r1 = _post_set(client, session["session_id"], b1["block_id"], weight=100.0, reps=5, rpe=8.5)
    assert r1["block_summary"]["has_previous_baseline"] is False
    assert r1["block_summary"]["volume_load_delta"] is None

    # Блок 2 (order_index=2) тієї самої вправи в тій самій сесії -> база: Блок 1
    b2 = _create_block(client, session["session_id"], bench["exercise_id"])
    r2_1 = _post_set(client, session["session_id"], b2["block_id"], weight=100.0, reps=6, rpe=8.5)
    assert r2_1["block_summary"]["block_volume_load"] == 600.0
    assert r2_1["block_summary"]["block_max_1rm"] == 120.0
    assert r2_1["block_summary"]["has_previous_baseline"] is True
    assert r2_1["block_summary"]["volume_load_delta"] == 100.0
    assert r2_1["block_summary"]["max_1rm_delta"] == 3.34

    # Другий підхід у Блок 2: +100 × 4 -> VL=1000.0 -> Дельта стає +500.0
    r2_2 = _post_set(client, session["session_id"], b2["block_id"], weight=100.0, reps=4, rpe=9.0)
    assert r2_2["block_summary"]["block_volume_load"] == 1000.0
    assert r2_2["block_summary"]["volume_load_delta"] == 500.0
    set2_id = r2_2["set"]["set_id"]

    # Видалення підходу 2 повертає Дельту до +100.0
    del_resp = client.delete(
        f"/api/v1/sessions/{session['session_id']}/blocks/{b2['block_id']}/sets/{set2_id}"
    )
    assert del_resp.status_code == 200
    del_summary = del_resp.json()["block_summary"]
    assert del_summary["block_volume_load"] == 600.0
    assert del_summary["has_previous_baseline"] is True
    assert del_summary["volume_load_delta"] == 100.0
    assert del_summary["max_1rm_delta"] == 3.34


# =====================================================================
# 2. Тести аналітичного дашборду (TKT-24, BDD-007)
# =====================================================================


def test_bdd_007_exercise_analytics_dashboard_progression_and_series(client: TestClient) -> None:
    """
    BDD-007 (REQ-F-017, REQ-NF-002, AC9):
    GET /api/v1/exercises/{exerciseId}/analytics повертає метадані вправи,
    latest_progression та хронологічно впорядкований ряд data_points.
    """
    _seed_profile_weight(client, 80.0)
    deadlift = _create_exercise(client, name="Станова тяга", exercise_type="STANDARD")

    s1 = _create_session(client, "2026-09-01T18:00:00Z")
    b1 = _create_block(client, s1["session_id"], deadlift["exercise_id"])
    _post_set(client, s1["session_id"], b1["block_id"], weight=150.0, reps=20, rpe=8.0)

    s2 = _create_session(client, "2026-09-08T18:00:00Z")
    b2 = _create_block(client, s2["session_id"], deadlift["exercise_id"])
    _post_set(client, s2["session_id"], b2["block_id"], weight=160.0, reps=20, rpe=8.5)

    s3 = _create_session(client, "2026-09-15T18:00:00Z")
    b3 = _create_block(client, s3["session_id"], deadlift["exercise_id"])
    _post_set(client, s3["session_id"], b3["block_id"], weight=165.0, reps=20, rpe=9.0)

    resp = client.get(f"/api/v1/exercises/{deadlift['exercise_id']}/analytics")
    assert resp.status_code == 200
    data = resp.json()

    assert data["exercise_id"] == deadlift["exercise_id"]
    assert data["exercise_name"] == "Станова тяга"
    assert data["exercise_type"] == "STANDARD"
    assert data["rm_model"] == "EPLEY"

    prog = data["latest_progression"]
    assert prog["has_previous_baseline"] is True
    assert prog["current_block_id"] == b3["block_id"]
    assert prog["previous_block_id"] == b2["block_id"]
    assert prog["current_volume_load"] == 3300.0
    assert prog["previous_volume_load"] == 3200.0
    assert prog["volume_load_delta"] == 100.0
    assert prog["current_max_1rm"] == 275.0
    assert prog["previous_max_1rm"] == 266.66
    assert prog["max_1rm_delta"] == 8.34

    points = data["data_points"]
    assert len(points) == 3
    assert [p["performed_at"] for p in points] == [
        "2026-09-01T18:00:00Z",
        "2026-09-08T18:00:00Z",
        "2026-09-15T18:00:00Z",
    ]
    assert points[0]["block_volume_load"] == 3000.0
    assert points[0]["volume_load_delta"] is None
    assert points[1]["block_volume_load"] == 3200.0
    assert points[1]["volume_load_delta"] == 200.0
    assert points[2]["block_volume_load"] == 3300.0
    assert points[2]["volume_load_delta"] == 100.0
    assert points[2]["body_weight_snapshot"] == 80.0


def test_analytics_single_execution_and_empty_exercise(client: TestClient) -> None:
    """
    REQ-F-017, REQ-F-018, AC9:
    Перевірка дашборду для вправи без історії (data_points=[]) та з 1 виконанням (has_previous_baseline=False).
    """
    _seed_profile_weight(client, 80.0)
    ex_empty = _create_exercise(client, name="Нова вправа без історії", exercise_type="STANDARD")
    empty_resp = client.get(f"/api/v1/exercises/{ex_empty['exercise_id']}/analytics")
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["latest_progression"]["has_previous_baseline"] is False
    assert empty_data["latest_progression"]["current_block_id"] is None
    assert empty_data["latest_progression"]["volume_load_delta"] is None
    assert empty_data["data_points"] == []

    # Вправа з 1 робочим виконанням
    ex_one = _create_exercise(client, name="Армійський жим", exercise_type="STANDARD")
    s1 = _create_session(client, "2026-09-01T18:00:00Z")
    b1 = _create_block(client, s1["session_id"], ex_one["exercise_id"])
    _post_set(client, s1["session_id"], b1["block_id"], weight=50.0, reps=10, rpe=8.0)

    one_resp = client.get(f"/api/v1/exercises/{ex_one['exercise_id']}/analytics")
    assert one_resp.status_code == 200
    one_data = one_resp.json()
    assert one_data["latest_progression"]["has_previous_baseline"] is False
    assert one_data["latest_progression"]["current_block_id"] == b1["block_id"]
    assert one_data["latest_progression"]["previous_block_id"] is None
    assert one_data["latest_progression"]["current_volume_load"] == 500.0
    assert one_data["latest_progression"]["previous_volume_load"] is None
    assert one_data["latest_progression"]["volume_load_delta"] is None
    assert len(one_data["data_points"]) == 1


def test_analytics_query_filters_from_date_to_date_and_limit(client: TestClient) -> None:
    """REQ-F-017: Фільтрація точок часового ряду дашборду за from_date, to_date та limit."""
    _seed_profile_weight(client, 80.0)
    row = _create_exercise(client, name="Тяга Т-грифа", exercise_type="STANDARD")

    for dt, wt in (
        ("2026-09-01T18:00:00Z", 60.0),
        ("2026-09-08T18:00:00Z", 70.0),
        ("2026-09-15T18:00:00Z", 80.0),
    ):
        ses = _create_session(client, dt)
        blk = _create_block(client, ses["session_id"], row["exercise_id"])
        _post_set(client, ses["session_id"], blk["block_id"], weight=wt, reps=10, rpe=8.0)

    filtered = client.get(
        f"/api/v1/exercises/{row['exercise_id']}/analytics",
        params={"from_date": "2026-09-05", "to_date": "2026-09-12"},
    )
    assert filtered.status_code == 200
    f_points = filtered.json()["data_points"]
    assert len(f_points) == 1
    assert f_points[0]["performed_at"] == "2026-09-08T18:00:00Z"
    assert f_points[0]["block_volume_load"] == 700.0

    limited = client.get(
        f"/api/v1/exercises/{row['exercise_id']}/analytics",
        params={"limit": 2},
    )
    assert limited.status_code == 200
    l_points = limited.json()["data_points"]
    assert len(l_points) == 2
    assert [p["performed_at"] for p in l_points] == [
        "2026-09-08T18:00:00Z",
        "2026-09-15T18:00:00Z",
    ]


def test_analytics_not_found_and_bad_date_range_400(client: TestClient) -> None:
    """REQ-F-017: Неіснуючий exerciseId -> 404 ERR_RESOURCE_NOT_FOUND; from_date > to_date -> 400 ERR_BAD_REQUEST."""
    missing = client.get("/api/v1/exercises/ex-nonexistent-999/analytics")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    ex = _create_exercise(client, name="Підйоми на біцепс", exercise_type="STANDARD")
    bad_range = client.get(
        f"/api/v1/exercises/{ex['exercise_id']}/analytics",
        params={"from_date": "2026-09-20", "to_date": "2026-09-01"},
    )
    assert bad_range.status_code == 400
    assert bad_range.json()["error"]["code"] == "ERR_BAD_REQUEST"
