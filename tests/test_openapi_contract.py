"""
Автоматизовані тести контрактної відповідності між формальною специфікацією
`spec/openapi.yaml` (SSoT) та фактичною реалізацією FastAPI (`src.main.app`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.main import app

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "spec" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _load_openapi_spec() -> dict[str, Any]:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def _assert_matches_schema(
    payload: dict[str, Any], schema_name: str, schemas: dict[str, Any]
) -> None:
    """Перевіряє наявність усіх `required`-полів та відсутність позаконтрактних ключів."""
    schema = schemas[schema_name]
    required_fields = set(schema.get("required", []))
    allowed_fields = set(schema.get("properties", {}).keys())
    actual_fields = set(payload.keys())

    missing = required_fields - actual_fields
    extra = actual_fields - allowed_fields
    assert not missing, f"Schema '{schema_name}' missing required fields: {sorted(missing)}"
    assert not extra, f"Schema '{schema_name}' has unexpected fields: {sorted(extra)}"


def _iter_api_routes(routes: Any) -> list[APIRoute]:
    """Рекурсивно збирає всі `APIRoute` із `app.routes`, включно з підключеними роутерами FastAPI."""
    collected: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            collected.append(route)
        elif hasattr(route, "original_router"):
            collected.extend(_iter_api_routes(route.original_router.routes))
        elif hasattr(route, "routes"):
            collected.extend(_iter_api_routes(route.routes))
    return collected


def test_openapi_all_14_routes_and_operation_ids_match_fastapi() -> None:
    """Верифікує повну відповідність 14 шляхів, HTTP-методів і `operationId` у `spec/openapi.yaml` та FastAPI."""
    spec = _load_openapi_spec()

    spec_operations: dict[tuple[str, str], str] = {}
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS:
                spec_operations[(path, method.upper())] = operation["operationId"]

    assert len(spec_operations) == 14

    fastapi_operations: dict[tuple[str, str], str] = {}
    for route in _iter_api_routes(app.routes):
        if route.path.startswith("/api/v1"):
            for method in route.methods:
                if method.lower() in HTTP_METHODS:
                    fastapi_operations[(route.path, method.upper())] = route.operation_id

    assert fastapi_operations == spec_operations

    # Додаткова перевірка runtime OpenAPI-схеми, згенерованої FastAPI
    generated = app.openapi()
    generated_operations: dict[tuple[str, str], str] = {}
    for path, path_item in generated["paths"].items():
        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS:
                generated_operations[(path, method.upper())] = operation["operationId"]

    assert generated_operations == spec_operations


def test_openapi_response_schemas_required_fields_compliance(client: TestClient) -> None:
    """Перевіряє структуру всіх основних JSON-відповідей та `ErrorResponse` на відповідність `components/schemas`."""
    spec = _load_openapi_spec()
    schemas = spec["components"]["schemas"]

    # 1. UserProfile (PUT & GET)
    put_profile = client.put("/api/v1/profile", json={"current_body_weight": 80.0})
    assert put_profile.status_code == 200
    _assert_matches_schema(put_profile.json(), "UserProfile", schemas)

    get_profile = client.get("/api/v1/profile")
    assert get_profile.status_code == 200
    _assert_matches_schema(get_profile.json(), "UserProfile", schemas)

    # 2. Exercise, ExerciseListResponse, PATCH model
    create_ex = client.post(
        "/api/v1/exercises",
        json={"name": "Присідання контракт", "exercise_type": "STANDARD"},
    )
    assert create_ex.status_code == 201
    ex_data = create_ex.json()
    _assert_matches_schema(ex_data, "Exercise", schemas)

    get_ex = client.get(f"/api/v1/exercises/{ex_data['exercise_id']}")
    assert get_ex.status_code == 200
    _assert_matches_schema(get_ex.json(), "Exercise", schemas)

    patch_ex = client.patch(
        f"/api/v1/exercises/{ex_data['exercise_id']}",
        json={"rm_model": "BRZYCKI"},
    )
    assert patch_ex.status_code == 200
    _assert_matches_schema(patch_ex.json(), "Exercise", schemas)

    list_ex = client.get("/api/v1/exercises")
    assert list_ex.status_code == 200
    list_ex_data = list_ex.json()
    _assert_matches_schema(list_ex_data, "ExerciseListResponse", schemas)
    _assert_matches_schema(list_ex_data["items"][0], "Exercise", schemas)

    # 3. WorkoutSession, SessionListResponse, ExerciseBlock
    s1 = client.post("/api/v1/sessions", json={"started_at": "2026-09-01T18:00:00Z"})
    assert s1.status_code == 201
    s1_data = s1.json()
    _assert_matches_schema(s1_data, "WorkoutSession", schemas)

    s2 = client.post("/api/v1/sessions", json={"started_at": "2026-09-08T18:00:00Z"})
    assert s2.status_code == 201
    s2_data = s2.json()

    list_ses = client.get("/api/v1/sessions")
    assert list_ses.status_code == 200
    list_ses_data = list_ses.json()
    _assert_matches_schema(list_ses_data, "SessionListResponse", schemas)
    _assert_matches_schema(list_ses_data["items"][0], "WorkoutSessionSummary", schemas)

    b1 = client.post(
        f"/api/v1/sessions/{s1_data['session_id']}/blocks",
        json={"exercise_id": ex_data["exercise_id"]},
    )
    assert b1.status_code == 201
    b1_data = b1.json()
    _assert_matches_schema(b1_data, "ExerciseBlock", schemas)

    b2 = client.post(
        f"/api/v1/sessions/{s2_data['session_id']}/blocks",
        json={"exercise_id": ex_data["exercise_id"]},
    )
    assert b2.status_code == 201
    b2_data = b2.json()

    # 4. CreateWorkoutSetResponse, WorkoutSet, ExerciseBlockSummary
    set1 = client.post(
        f"/api/v1/sessions/{s1_data['session_id']}/blocks/{b1_data['block_id']}/sets",
        json={"weight": 100.0, "reps": 5, "rpe": 8.5, "is_warmup": False},
    )
    assert set1.status_code == 201

    set2 = client.post(
        f"/api/v1/sessions/{s2_data['session_id']}/blocks/{b2_data['block_id']}/sets",
        json={"weight": 105.0, "reps": 5, "rpe": 9.0, "is_warmup": False},
    )
    assert set2.status_code == 201
    set2_data = set2.json()
    _assert_matches_schema(set2_data, "CreateWorkoutSetResponse", schemas)
    _assert_matches_schema(set2_data["set"], "WorkoutSet", schemas)
    _assert_matches_schema(set2_data["block_summary"], "ExerciseBlockSummary", schemas)

    get_blk = client.get(
        f"/api/v1/sessions/{s2_data['session_id']}/blocks/{b2_data['block_id']}"
    )
    assert get_blk.status_code == 200
    get_blk_data = get_blk.json()
    _assert_matches_schema(get_blk_data, "ExerciseBlock", schemas)
    _assert_matches_schema(get_blk_data["sets"][0], "WorkoutSet", schemas)

    get_ses = client.get(f"/api/v1/sessions/{s2_data['session_id']}")
    assert get_ses.status_code == 200
    get_ses_data = get_ses.json()
    _assert_matches_schema(get_ses_data, "WorkoutSession", schemas)
    _assert_matches_schema(get_ses_data["blocks"][0], "ExerciseBlock", schemas)

    # 5. ExerciseAnalyticsResponse, LatestProgressionSummary, AnalyticsDataPoint
    analytics = client.get(f"/api/v1/exercises/{ex_data['exercise_id']}/analytics")
    assert analytics.status_code == 200
    analytics_data = analytics.json()
    _assert_matches_schema(analytics_data, "ExerciseAnalyticsResponse", schemas)
    _assert_matches_schema(
        analytics_data["latest_progression"], "LatestProgressionSummary", schemas
    )
    _assert_matches_schema(
        analytics_data["data_points"][0], "AnalyticsDataPoint", schemas
    )

    # 6. DeleteWorkoutSetResponse
    del_set = client.delete(
        f"/api/v1/sessions/{s2_data['session_id']}/blocks/{b2_data['block_id']}/sets/{set2_data['set']['set_id']}"
    )
    assert del_set.status_code == 200
    del_data = del_set.json()
    _assert_matches_schema(del_data, "DeleteWorkoutSetResponse", schemas)
    _assert_matches_schema(del_data["block_summary"], "ExerciseBlockSummary", schemas)

    # 7. ErrorResponse & ErrorObject (400, 404, 422)
    for err_resp in (
        client.put("/api/v1/profile", json={}),
        client.get("/api/v1/sessions/unknown-session-contract"),
        client.put("/api/v1/profile", json={"current_body_weight": 20.0}),
    ):
        assert err_resp.status_code in (400, 404, 422)
        err_body = err_resp.json()
        _assert_matches_schema(err_body, "ErrorResponse", schemas)
        _assert_matches_schema(err_body["error"], "ErrorObject", schemas)
