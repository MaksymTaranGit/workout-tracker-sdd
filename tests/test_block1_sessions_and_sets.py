"""
Автоматизовані інтеграційні та BDD-тести для Блоку 1 (Тікети TKT-01, TKT-03).

Покриває вимоги:
- REQ-F-001, REQ-F-002 (Створення сесій, незмінність body_weight_snapshot)
- REQ-F-003, REQ-F-004, REQ-F-005 (Додавання ізольованих блоків, фіксація підходів, RPE, is_warmup)
- REQ-F-019, REQ-F-020 (Профіль користувача 30.0..300.0 кг, каталог вправ з дефолтом EPLEY)
- AC1, AC2, AC10, AC11
- BDD-001, BDD-003 (фіксація розминочних підходів)
- Ризики: RSK-06 (історична цілісність снапшоту), RSK-09 (ізоляція дубльованих вправ), RSK-02 (межі reps)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# =====================================================================
# Допоміжні функції налаштування (без прихованої бізнес-логіки)
# =====================================================================


def _seed_profile_weight(client: TestClient, weight: float = 80.0) -> dict:
    resp = client.put("/api/v1/profile", json={"current_body_weight": weight})
    assert resp.status_code == 200, f"Expected 200 when setting profile weight, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_exercise(
    client: TestClient,
    name: str = "Присідання зі штангою",
    exercise_type: str = "STANDARD",
) -> dict:
    resp = client.post(
        "/api/v1/exercises",
        json={"name": name, "exercise_type": exercise_type},
    )
    assert resp.status_code == 201, f"Expected 201 when creating exercise, got {resp.status_code}: {resp.text}"
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
    assert resp.status_code == 201, f"Expected 201 when creating session, got {resp.status_code}: {resp.text}"
    return resp.json()


def _create_block(client: TestClient, session_id: str, exercise_id: str) -> dict:
    resp = client.post(
        f"/api/v1/sessions/{session_id}/blocks",
        json={"exercise_id": exercise_id},
    )
    assert resp.status_code == 201, f"Expected 201 when creating block, got {resp.status_code}: {resp.text}"
    return resp.json()


# =====================================================================
# 1. Профіль користувача (REQ-F-019, AC10)
# =====================================================================


def test_get_and_update_user_profile_valid(client: TestClient) -> None:
    """REQ-F-019, AC10: Читання профілю та валідне оновлення маси тіла (включно з межами 30.0 і 300.0 кг)."""
    put_80 = client.put("/api/v1/profile", json={"current_body_weight": 80.0})
    assert put_80.status_code == 200
    data_80 = put_80.json()
    assert data_80["current_body_weight"] == 80.0
    assert data_80["unit"] == "kg"
    assert data_80["user_id"]
    assert data_80["updated_at"]

    get_resp = client.get("/api/v1/profile")
    assert get_resp.status_code == 200
    assert get_resp.json()["current_body_weight"] == 80.0
    assert get_resp.json()["unit"] == "kg"

    # Гранично допустимий мінімум: 30.0 кг
    put_min = client.put("/api/v1/profile", json={"current_body_weight": 30.0})
    assert put_min.status_code == 200
    assert put_min.json()["current_body_weight"] == 30.0
    assert client.get("/api/v1/profile").json()["current_body_weight"] == 30.0

    # Гранично допустимий максимум: 300.0 кг
    put_max = client.put("/api/v1/profile", json={"current_body_weight": 300.0})
    assert put_max.status_code == 200
    assert put_max.json()["current_body_weight"] == 300.0
    assert client.get("/api/v1/profile").json()["current_body_weight"] == 300.0


@pytest.mark.parametrize("invalid_weight", [29.9, 300.1, 0.0, -50.0])
def test_update_user_profile_out_of_range_422(client: TestClient, invalid_weight: float) -> None:
    """REQ-F-019, AC10: Значення маси тіла поза діапазоном [30.0, 300.0] кг відхиляються з 422 ERR_INVALID_BODY_WEIGHT."""
    resp = client.put("/api/v1/profile", json={"current_body_weight": invalid_weight})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_INVALID_BODY_WEIGHT"
    assert err["http_status"] == 422
    assert err["trace_id"]


def test_update_user_profile_bad_request_400(client: TestClient) -> None:
    """Структурні та типові помилки при оновленні профілю повертають 400 ERR_BAD_REQUEST."""
    missing_field = client.put("/api/v1/profile", json={})
    assert missing_field.status_code == 400
    assert missing_field.json()["error"]["code"] == "ERR_BAD_REQUEST"
    assert missing_field.json()["error"]["http_status"] == 400

    wrong_type = client.put("/api/v1/profile", json={"current_body_weight": "eighty"})
    assert wrong_type.status_code == 400
    assert wrong_type.json()["error"]["code"] == "ERR_BAD_REQUEST"


# =====================================================================
# 2. Каталог вправ (REQ-F-020, REQ-F-013, AC11)
# =====================================================================


def test_create_and_get_exercises_all_types(client: TestClient) -> None:
    """REQ-F-020, REQ-F-013, AC11: Створення STANDARD/BODYWEIGHT/ASSISTED з дефолтом EPLEY, список із фільтром та деталі."""
    ex_std = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    assert ex_std["exercise_type"] == "STANDARD"
    assert ex_std["rm_model"] == "EPLEY"
    assert ex_std["exercise_id"]
    assert ex_std["created_at"]

    ex_bw = _create_exercise(client, name="Підтягування на турніку", exercise_type="BODYWEIGHT")
    assert ex_bw["exercise_type"] == "BODYWEIGHT"
    assert ex_bw["rm_model"] == "EPLEY"

    ex_ast = _create_exercise(client, name="Підтягування у гравітроні", exercise_type="ASSISTED")
    assert ex_ast["exercise_type"] == "ASSISTED"
    assert ex_ast["rm_model"] == "EPLEY"

    # Повний список вправ
    list_all = client.get("/api/v1/exercises")
    assert list_all.status_code == 200
    all_body = list_all.json()
    assert all_body["total"] == 3
    assert len(all_body["items"]) == 3

    # Фільтрація за exercise_type=ASSISTED
    list_assisted = client.get("/api/v1/exercises", params={"exercise_type": "ASSISTED"})
    assert list_assisted.status_code == 200
    assisted_body = list_assisted.json()
    assert assisted_body["total"] == 1
    assert len(assisted_body["items"]) == 1
    assert assisted_body["items"][0]["exercise_id"] == ex_ast["exercise_id"]
    assert assisted_body["items"][0]["exercise_type"] == "ASSISTED"

    # Отримання конкретної вправи за ID
    detail_resp = client.get(f"/api/v1/exercises/{ex_std['exercise_id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["exercise_id"] == ex_std["exercise_id"]
    assert detail["name"] == "Присідання зі штангою"
    assert detail["rm_model"] == "EPLEY"


def test_create_exercise_duplicate_name_422(client: TestClient) -> None:
    """REQ-F-020: Повторне створення вправи з вже існуючою назвою повертає 422 ERR_DUPLICATE_EXERCISE_NAME."""
    _create_exercise(client, name="Жим штанги лежачи", exercise_type="STANDARD")
    dup_resp = client.post(
        "/api/v1/exercises",
        json={"name": "Жим штанги лежачи", "exercise_type": "STANDARD"},
    )
    assert dup_resp.status_code == 422
    err = dup_resp.json()["error"]
    assert err["code"] == "ERR_DUPLICATE_EXERCISE_NAME"
    assert err["http_status"] == 422


def test_exercise_bad_request_and_not_found(client: TestClient) -> None:
    """Невалідні дані вправи дають 400 ERR_BAD_REQUEST, неіснуючий ID — 404 ERR_RESOURCE_NOT_FOUND."""
    empty_name = client.post(
        "/api/v1/exercises",
        json={"name": "", "exercise_type": "STANDARD"},
    )
    assert empty_name.status_code == 400
    assert empty_name.json()["error"]["code"] == "ERR_BAD_REQUEST"

    short_name = client.post(
        "/api/v1/exercises",
        json={"name": "A", "exercise_type": "STANDARD"},
    )
    assert short_name.status_code == 400
    assert short_name.json()["error"]["code"] == "ERR_BAD_REQUEST"

    unknown_type = client.post(
        "/api/v1/exercises",
        json={"name": "Велотренажер", "exercise_type": "CARDIO"},
    )
    assert unknown_type.status_code == 400
    assert unknown_type.json()["error"]["code"] == "ERR_BAD_REQUEST"

    not_found = client.get("/api/v1/exercises/ex-unknown-999999")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"
    assert not_found.json()["error"]["http_status"] == 404


# =====================================================================
# 3. Тренувальні сесії та снапшот ваги (REQ-F-001, REQ-F-002, BDD-001, RSK-06)
# =====================================================================


def test_create_list_and_get_sessions(client: TestClient) -> None:
    """REQ-F-001, REQ-F-002, AC1: Створення, пагінація списку та детальне читання сесій; 404 для неіснуючої."""
    _seed_profile_weight(client, 78.5)

    s1 = _create_session(client, started_at="2026-09-01T18:00:00Z", notes="Перша сесія")
    assert s1["session_id"]
    assert s1["started_at"] == "2026-09-01T18:00:00Z"
    assert s1["body_weight_snapshot"] == 78.5
    assert s1["notes"] == "Перша сесія"
    assert s1["blocks"] == []

    s2 = _create_session(client, started_at="2026-09-08T18:00:00Z", notes="Друга сесія")
    assert s2["session_id"] != s1["session_id"]
    assert s2["body_weight_snapshot"] == 78.5

    # Пагінація: limit=1, offset=0 та offset=1
    page_0 = client.get("/api/v1/sessions", params={"limit": 1, "offset": 0})
    assert page_0.status_code == 200
    p0 = page_0.json()
    assert p0["total"] == 2
    assert p0["limit"] == 1
    assert p0["offset"] == 0
    assert len(p0["items"]) == 1

    page_1 = client.get("/api/v1/sessions", params={"limit": 1, "offset": 1})
    assert page_1.status_code == 200
    p1 = page_1.json()
    assert p1["total"] == 2
    assert len(p1["items"]) == 1
    assert p1["items"][0]["session_id"] != p0["items"][0]["session_id"]

    # Деталі сесії
    detail = client.get(f"/api/v1/sessions/{s1['session_id']}")
    assert detail.status_code == 200
    assert detail.json()["session_id"] == s1["session_id"]
    assert detail.json()["body_weight_snapshot"] == 78.5

    # Неіснуюча сесія -> 404
    missing = client.get("/api/v1/sessions/unknown-session-id-999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"


def test_bdd_001_body_weight_snapshot_immutability(client: TestClient) -> None:
    """
    BDD-001 (REQ-F-002, REQ-F-019, RSK-06):
    Дано існуючу тренувальну сесію зі снапшотом 80 кг
    Коли користувач оновлює масу тіла в профілі до 85 кг
    Тоді значення снапшоту минулої сесії залишається 80 кг (незмінне), а нова сесія отримує 85 кг.
    """
    _seed_profile_weight(client, 80.0)
    past_session = _create_session(client, started_at="2026-08-15T17:00:00Z", notes="Минула сесія")
    assert past_session["body_weight_snapshot"] == 80.0

    updated_profile = _seed_profile_weight(client, 85.0)
    assert updated_profile["current_body_weight"] == 85.0

    reloaded_past = client.get(f"/api/v1/sessions/{past_session['session_id']}")
    assert reloaded_past.status_code == 200
    assert reloaded_past.json()["body_weight_snapshot"] == 80.0

    new_session = _create_session(client, started_at="2026-09-15T17:00:00Z", notes="Нова сесія")
    assert new_session["body_weight_snapshot"] == 85.0


# =====================================================================
# 4. Блоки вправ та фіксація підходів (REQ-F-003..005, AC2, RSK-09)
# =====================================================================


def test_create_isolated_exercise_blocks_rsk09(client: TestClient) -> None:
    """REQ-F-003, REQ-F-006, RSK-09: Повторне додавання тієї ж вправи створює окремі ізольовані блоки."""
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    session = _create_session(client, started_at="2026-09-15T17:00:00Z")

    block_1 = _create_block(client, session["session_id"], squat["exercise_id"])
    assert block_1["block_id"]
    assert block_1["order_index"] == 1
    assert block_1["exercise_id"] == squat["exercise_id"]
    assert block_1["sets"] == []

    # Додаємо ту саму вправу вдруге у ту саму сесію
    block_2 = _create_block(client, session["session_id"], squat["exercise_id"])
    assert block_2["block_id"] != block_1["block_id"]
    assert block_2["order_index"] == 2
    assert block_2["sets"] == []

    # Перевірка читання окремого блоку та всієї сесії
    get_b1 = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/{block_1['block_id']}")
    assert get_b1.status_code == 200
    assert get_b1.json()["order_index"] == 1

    get_ses = client.get(f"/api/v1/sessions/{session['session_id']}")
    assert get_ses.status_code == 200
    blocks = get_ses.json()["blocks"]
    assert len(blocks) == 2
    assert {b["block_id"] for b in blocks} == {block_1["block_id"], block_2["block_id"]}


def test_create_and_delete_workout_sets_working_and_warmup(client: TestClient) -> None:
    """REQ-F-004, REQ-F-005, AC2, BDD-003: Запис розминочних і робочих підходів (межі RPE та reps) та видалення."""
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    session = _create_session(client, started_at="2026-09-15T17:00:00Z")
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    sets_url = f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets"

    # 1. Розминочний підхід (is_warmup=True), нижня межа RPE=6.0
    warmup_resp = client.post(
        sets_url,
        json={"weight": 60.0, "reps": 10, "rpe": 6.0, "is_warmup": True},
    )
    assert warmup_resp.status_code == 201
    warmup_set = warmup_resp.json()["set"]
    assert warmup_set["set_number"] == 1
    assert warmup_set["is_warmup"] is True
    assert warmup_set["weight"] == 60.0
    assert warmup_set["reps"] == 10
    assert warmup_set["rpe"] == 6.0

    # 2. Робочий підхід (is_warmup=False), верхня межа RPE=10.0, нижня межа reps=1
    work_resp = client.post(
        sets_url,
        json={"weight": 120.0, "reps": 1, "rpe": 10.0, "is_warmup": False},
    )
    assert work_resp.status_code == 201
    work_set = work_resp.json()["set"]
    assert work_set["set_number"] == 2
    assert work_set["is_warmup"] is False
    assert work_set["reps"] == 1
    assert work_set["rpe"] == 10.0

    # 3. Гранично допустиме значення для формули Brzycki: reps=36
    edge_reps_resp = client.post(
        sets_url,
        json={"weight": 50.0, "reps": 36, "rpe": 9.0, "is_warmup": False},
    )
    assert edge_reps_resp.status_code == 201
    edge_set = edge_reps_resp.json()["set"]
    assert edge_set["reps"] == 36
    assert edge_set["set_number"] == 3

    # 4. Видалення підходу DELETE .../sets/{setId}
    del_resp = client.delete(f"{sets_url}/{edge_set['set_id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_set_id"] == edge_set["set_id"]

    # Перевірка, що у блоці залишилися лише 2 перші підходи
    blk_after = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}")
    assert blk_after.status_code == 200
    remaining_ids = [s["set_id"] for s in blk_after.json()["sets"]]
    assert edge_set["set_id"] not in remaining_ids
    assert len(remaining_ids) == 2


@pytest.mark.parametrize("invalid_rpe", [5.9, 5.5, 10.1, 0.0, -1.0])
def test_create_workout_set_rpe_out_of_range_422(client: TestClient, invalid_rpe: float) -> None:
    """REQ-F-004: Показник RPE поза діапазоном [6.0, 10.0] повертає 422 ERR_RPE_OUT_OF_RANGE."""
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Жим ногами", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], squat["exercise_id"])

    resp = client.post(
        f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets",
        json={"weight": 100.0, "reps": 8, "rpe": invalid_rpe, "is_warmup": False},
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "ERR_RPE_OUT_OF_RANGE"
    assert err["http_status"] == 422


def test_create_workout_set_invalid_reps_422(client: TestClient) -> None:
    """REQ-F-004, RSK-02: reps <= 0 -> 422 ERR_INVALID_REPS_COUNT; reps >= 37 -> 422 ERR_BRZYCKI_MATHEMATICAL_LIMIT."""
    _seed_profile_weight(client, 80.0)
    squat = _create_exercise(client, name="Жим штанги стоячи", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], squat["exercise_id"])
    sets_url = f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets"

    for bad_reps in (0, -3):
        resp_zero = client.post(
            sets_url,
            json={"weight": 60.0, "reps": bad_reps, "rpe": 8.0, "is_warmup": False},
        )
        assert resp_zero.status_code == 422
        assert resp_zero.json()["error"]["code"] == "ERR_INVALID_REPS_COUNT"
        assert resp_zero.json()["error"]["http_status"] == 422

    for over_limit_reps in (37, 50):
        resp_brzycki = client.post(
            sets_url,
            json={"weight": 40.0, "reps": over_limit_reps, "rpe": 9.5, "is_warmup": False},
        )
        assert resp_brzycki.status_code == 422
        assert resp_brzycki.json()["error"]["code"] == "ERR_BRZYCKI_MATHEMATICAL_LIMIT"
        assert resp_brzycki.json()["error"]["http_status"] == 422


def test_blocks_and_sets_not_found_and_bad_request(client: TestClient) -> None:
    """Перевірка 404 ERR_RESOURCE_NOT_FOUND для неіснуючих ID та 400 ERR_BAD_REQUEST для структурних помилок."""
    _seed_profile_weight(client, 80.0)
    ex = _create_exercise(client, name="Тяга штанги в нахилі", exercise_type="STANDARD")
    session = _create_session(client)
    block = _create_block(client, session["session_id"], ex["exercise_id"])

    # 404: Неіснуюча сесія при створенні блоку
    r_missing_ses = client.post(
        "/api/v1/sessions/unknown-ses-999/blocks",
        json={"exercise_id": ex["exercise_id"]},
    )
    assert r_missing_ses.status_code == 404
    assert r_missing_ses.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    # 404: Неіснуюча вправа при створенні блоку
    r_missing_ex = client.post(
        f"/api/v1/sessions/{session['session_id']}/blocks",
        json={"exercise_id": "unknown-ex-999"},
    )
    assert r_missing_ex.status_code == 404
    assert r_missing_ex.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    # 404: Неіснуючий блок при GET / POST set / DELETE set
    r_get_blk = client.get(f"/api/v1/sessions/{session['session_id']}/blocks/unknown-blk-999")
    assert r_get_blk.status_code == 404
    assert r_get_blk.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    r_post_set = client.post(
        f"/api/v1/sessions/{session['session_id']}/blocks/unknown-blk-999/sets",
        json={"weight": 80.0, "reps": 8, "rpe": 8.0, "is_warmup": False},
    )
    assert r_post_set.status_code == 404
    assert r_post_set.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    r_del_set = client.delete(
        f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets/unknown-set-999"
    )
    assert r_del_set.status_code == 404
    assert r_del_set.json()["error"]["code"] == "ERR_RESOURCE_NOT_FOUND"

    # 400: Невірний тип reps="five" та відсутнє поле rpe
    sets_url = f"/api/v1/sessions/{session['session_id']}/blocks/{block['block_id']}/sets"
    r_bad_type = client.post(
        sets_url,
        json={"weight": 100.0, "reps": "five", "rpe": 8.5, "is_warmup": False},
    )
    assert r_bad_type.status_code == 400
    assert r_bad_type.json()["error"]["code"] == "ERR_BAD_REQUEST"

    r_missing_rpe = client.post(
        sets_url,
        json={"weight": 100.0, "reps": 5},
    )
    assert r_missing_rpe.status_code == 400
    assert r_missing_rpe.json()["error"]["code"] == "ERR_BAD_REQUEST"
