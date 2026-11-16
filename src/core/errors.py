"""
Єдиний конверт помилок REST API та глобальні обробники винятків FastAPI.

Відповідає `components/schemas/ErrorResponse` та `components/schemas/ErrorObject`
із формальної специфікації `spec/openapi.yaml` (REQ-NF-009, REQ-NF-010).
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.logger import TRACE_LEVEL_NUM, get_trace_id, log_event


class ErrorCode(str, Enum):
    """Машиночитані коди помилок згідно зі `spec/openapi.yaml`."""

    ERR_BAD_REQUEST = "ERR_BAD_REQUEST"
    ERR_RESOURCE_NOT_FOUND = "ERR_RESOURCE_NOT_FOUND"
    ERR_RPE_OUT_OF_RANGE = "ERR_RPE_OUT_OF_RANGE"
    ERR_INVALID_REPS_COUNT = "ERR_INVALID_REPS_COUNT"
    ERR_BRZYCKI_MATHEMATICAL_LIMIT = "ERR_BRZYCKI_MATHEMATICAL_LIMIT"
    ERR_NEGATIVE_WEIGHT_NOT_ALLOWED = "ERR_NEGATIVE_WEIGHT_NOT_ALLOWED"
    ERR_POSITIVE_WEIGHT_IN_ASSISTED = "ERR_POSITIVE_WEIGHT_IN_ASSISTED"
    ERR_NON_POSITIVE_EFFECTIVE_LOAD = "ERR_NON_POSITIVE_EFFECTIVE_LOAD"
    ERR_INVALID_BODY_WEIGHT = "ERR_INVALID_BODY_WEIGHT"
    ERR_PROFILE_WEIGHT_MISSING = "ERR_PROFILE_WEIGHT_MISSING"
    ERR_DUPLICATE_EXERCISE_NAME = "ERR_DUPLICATE_EXERCISE_NAME"
    ERR_EXERCISE_ARCHIVED = "ERR_EXERCISE_ARCHIVED"
    ERR_NOT_IMPLEMENTED = "ERR_NOT_IMPLEMENTED"


class ErrorObject(BaseModel):
    """Структурований опис помилки для автоматизованої верифікації (REQ-NF-009, REQ-NF-010)."""

    code: str = Field(..., description="Машиночитаний код помилки")
    http_status: int = Field(..., description="HTTP статус-код відповіді (400, 404, 422, 501)")
    message: str = Field(..., description="Людиночитане повідомлення про причину помилки")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Додатковий контекст помилки (назва поля, відхилене значення, допустимі межі)",
    )
    trace_id: str = Field(..., description="Ідентифікатор трасування контрольної точки (REQ-NF-009)")


class ErrorResponse(BaseModel):
    """Єдиний конверт помилки REST API (`spec/openapi.yaml`)."""

    error: ErrorObject


class AppError(Exception):
    """Доменний або інфраструктурний виняток із фіксованим кодом помилки контракту."""

    def __init__(
        self,
        code: ErrorCode | str,
        http_status: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.http_status = http_status
        self.message = message
        self.details = details


def build_error_response(
    code: ErrorCode | str,
    http_status: int,
    message: str,
    details: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> JSONResponse:
    """Формує стандартизований JSONResponse у конверті `ErrorResponse`."""
    resolved_trace_id = trace_id or get_trace_id()
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    payload = ErrorResponse(
        error=ErrorObject(
            code=code_str,
            http_status=http_status,
            message=message,
            details=details,
            trace_id=resolved_trace_id,
        )
    )
    return JSONResponse(
        status_code=http_status,
        content=payload.model_dump(mode="json"),
        headers={"X-Trace-Id": resolved_trace_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Реєструє глобальні обробники винятків FastAPI:
    - `RequestValidationError` та `JSONDecodeError` -> HTTP 400 Bad Request (`ERR_BAD_REQUEST`)
    - `AppError` -> відповідний HTTP-статус (400 / 404 / 422 / 501) та код доменної помилки
    - `StarletteHTTPException` (зокрема 404) -> конверт `ErrorResponse`
    """

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
        log_event(
            logging.WARNING,
            "API",
            "APP_ERROR_HANDLER",
            f"Application error [{exc.code}]: {exc.message}",
            context={
                "code": exc.code,
                "http_status": exc.http_status,
                "path": request.url.path,
                "details": exc.details,
            },
            trace_id=trace_id,
        )
        return build_error_response(
            code=exc.code,
            http_status=exc.http_status,
            message=exc.message,
            details=exc.details,
            trace_id=trace_id,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
        raw_errors = exc.errors()
        first_error = raw_errors[0] if raw_errors else {}
        loc = first_error.get("loc", ())
        field_name = str(loc[-1]) if loc else "body"
        issue_msg = str(first_error.get("msg", "Invalid request structure"))

        details: dict[str, Any] = {
            "field": field_name,
            "issue": issue_msg,
            "validation_errors": [
                {
                    "loc": [str(part) for part in err.get("loc", ())],
                    "type": str(err.get("type", "")),
                    "msg": str(err.get("msg", "")),
                }
                for err in raw_errors
            ],
        }

        log_event(
            logging.WARNING,
            "API",
            "REQUEST_VALIDATION_400",
            f"Structural/syntax validation failed on field '{field_name}': {issue_msg}",
            context={"path": request.url.path, "details": details},
            trace_id=trace_id,
        )
        return build_error_response(
            code=ErrorCode.ERR_BAD_REQUEST,
            http_status=400,
            message="Некоректна структура запиту: відсутнє обов'язкове поле або передано невірний тип даних.",
            details=details,
            trace_id=trace_id,
        )

    @app.exception_handler(json.JSONDecodeError)
    async def handle_json_decode_error(
        request: Request, exc: json.JSONDecodeError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
        details = {"issue": f"Malformed JSON at line {exc.lineno} col {exc.colno}: {exc.msg}"}
        log_event(
            logging.WARNING,
            "API",
            "JSON_DECODE_400",
            "Malformed JSON payload received",
            context={"path": request.url.path, "details": details},
            trace_id=trace_id,
        )
        return build_error_response(
            code=ErrorCode.ERR_BAD_REQUEST,
            http_status=400,
            message="Синтаксична помилка JSON у тілі запиту.",
            details=details,
            trace_id=trace_id,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
        status_code = exc.status_code
        if status_code == 404:
            code = ErrorCode.ERR_RESOURCE_NOT_FOUND
            message = (
                str(exc.detail)
                if exc.detail and exc.detail != "Not Found"
                else "Запитуваний ресурс не знайдено у базі даних."
            )
        elif status_code == 400:
            code = ErrorCode.ERR_BAD_REQUEST
            message = str(exc.detail) if exc.detail else "Некоректний HTTP-запит."
        else:
            code = f"ERR_HTTP_{status_code}"
            message = str(exc.detail) if exc.detail else "HTTP error occurred."

        log_event(
            TRACE_LEVEL_NUM,
            "API",
            "HTTP_EXCEPTION_HANDLER",
            f"HTTPException {status_code}: {message}",
            context={"path": request.url.path, "status_code": status_code},
            trace_id=trace_id,
        )
        return build_error_response(
            code=code,
            http_status=status_code,
            message=message,
            details={"path": request.url.path},
            trace_id=trace_id,
        )
