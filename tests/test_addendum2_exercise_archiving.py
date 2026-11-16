"""
Автоматизовані інтеграційні та BDD-тести для SRS Addendum #2 (Тікет TKT-29, фаза RED).

Покриває вимоги:
- REQ-F-022: М'яке видалення (архівація) вправи з каталогу зі збереженням історії тренувань (Soft Delete)
- AC13: Архівація DELETE /api/v1/exercises/{exerciseId}, виключення з GET /api/v1/exercises,
        блокування додавання до нових сесій (422 ERR_EXERCISE_ARCHIVED) та збереження історії/аналітики
- BDD-008: Повний сценарій архівації вправи та перевірки історичної цілісності
- RSK-10: Запобігання каскадній втраті історії та повторному використанню архівованих вправ
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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
    started_at: str,
    notes: str | None = None,
) -> dict:
    payload: dict = {"started_at": started_at}
    if notes is not None:
        payload["notes"] = notes
    resp = client.post("/api/v1/sessions", json=payload)
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


def test_bdd_008_archive_exercise_soft_delete_preserves_history(client: TestClient) -> None:
    """
    TKT-29 (REQ-F-022, AC13, BDD-008, RSK-10):
    М'яке видалення вправи позначає її архівованою, прибирає з активного каталогу,
    блокує додавання до нових сесій (422 ERR_EXERCISE_ARCHIVED),
    але повністю зберігає історичні сесії та аналітику вправи.
    """
    # Крок 1: Підготовка історичної сесії, блоку та робочого підходу
    _seed_profile_weight(client, 80.0)
    exercise = _create_exercise(client, name="Присідання зі штангою", exercise_type="STANDARD")
    exercise_id = exercise["exercise_id"]

    session = _create_session(client, started_at="2026-04-10T10:00:00Z", notes="Сесія до архівації")
    session_id = session["session_id"]

    block = _create_block(client, session_id, exercise_id)
    block_id = block["block_id"]
    _post_set(client, session_id, block_id, weight=100.0, reps=5, rpe=8.0, is_warmup=False)

    # Крок 2: М'яке видалення (архівація) вправи
    delete_resp = client.delete(f"/api/v1/exercises/{exercise_id}")
    assert delete_resp.status_code == 200
    archive_data = delete_resp.json()
    assert archive_data["exercise_id"] == exercise_id
    assert archive_data["name"] == "Присідання зі штангою"
    assert archive_data["is_archived"] is True
    assert isinstance(archive_data.get("archived_at"), str) and len(archive_data["archived_at"]) > 0

    # Крок 3: Виключення архівованої вправи з активного каталогу
    catalog_resp = client.get("/api/v1/exercises")
    assert catalog_resp.status_code == 200
    active_ids = [item["exercise_id"] for item in catalog_resp.json()["items"]]
    assert exercise_id not in active_ids

    # Крок 4: Блокування додавання архівованої вправи до нової тренувальної сесії
    new_session = _create_session(client, started_at="2026-04-12T10:00:00Z")
    blocked_resp = client.post(
        f"/api/v1/sessions/{new_session['session_id']}/blocks",
        json={"exercise_id": exercise_id},
    )
    assert blocked_resp.status_code == 422
    assert blocked_resp.json()["error"]["code"] == "ERR_EXERCISE_ARCHIVED"

    # Крок 5: Перевірка збереження історичної сесії та аналітичного дашборду
    hist_session_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert hist_session_resp.status_code == 200
    session_data = hist_session_resp.json()
    assert len(session_data["blocks"]) == 1
    assert session_data["blocks"][0]["exercise_id"] == exercise_id
    assert session_data["blocks"][0]["block_volume_load"] == 500.0
    assert len(session_data["blocks"][0]["sets"]) == 1

    analytics_resp = client.get(f"/api/v1/exercises/{exercise_id}/analytics")
    assert analytics_resp.status_code == 200
    analytics_data = analytics_resp.json()
    assert analytics_data["exercise_id"] == exercise_id
    assert analytics_data["latest_progression"]["current_block_id"] == block_id
    assert analytics_data["latest_progression"]["current_volume_load"] == 500.0
    assert len(analytics_data["data_points"]) == 1
    assert analytics_data["data_points"][0]["block_volume_load"] == 500.0


def test_delete_nonexistent_exercise_returns_404(client: TestClient) -> None:
    """REQ-F-022 (Negative case): Архівація неіснуючого exerciseId повертає 404 ERR_RESOURCE_NOT_FOUND."""
    resp = client.delete("/api/v1/exercises/ex-nonexistent-999")
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "ERR_RESOURCE_NOT_FOUND"
    assert err["http_status"] == 404


def test_delete_already_archived_exercise_returns_404(client: TestClient) -> None:
    """REQ-F-022 (Boundary case): Повторне видалення вже архівованої вправи повертає 404 ERR_RESOURCE_NOT_FOUND."""
    exercise = _create_exercise(client, name="Тяга штанги в нахилі", exercise_type="STANDARD")
    exercise_id = exercise["exercise_id"]

    first_resp = client.delete(f"/api/v1/exercises/{exercise_id}")
    assert first_resp.status_code == 200
    assert first_resp.json()["is_archived"] is True

    second_resp = client.delete(f"/api/v1/exercises/{exercise_id}")
    assert second_resp.status_code == 404
    err = second_resp.json()["error"]
    assert err["code"] == "ERR_RESOURCE_NOT_FOUND"
