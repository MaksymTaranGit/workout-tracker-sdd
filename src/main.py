"""
Точка входу FastAPI-застосунку Workout Volume & Progressive Overload Tracker.

Забезпечує:
1. HTTP Middleware для генерації унікального `trace_id` на кожен запит (`REQ-NF-009`).
2. Замір часу обробки запитів у мілісекундах для контролю бюджету продуктивності `< 100 мс` (`REQ-NF-001`).
3. Глобальні обробники помилок у форматі `ErrorResponse` (`spec/openapi.yaml`).
4. Підключення 14 маршрутів `/api/v1/...` (`src/api/routes.py`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from src.api.routes import router as api_v1_router
from src.core.errors import register_exception_handlers
from src.core.logger import (
    TRACE_LEVEL_NUM,
    generate_trace_id,
    log_event,
    reset_trace_id,
    set_trace_id,
)


def create_app() -> FastAPI:
    """Створює та конфігурує екземпляр FastAPI-застосунку."""
    application = FastAPI(
        title="Workout Volume & Progressive Overload Tracker API",
        version="1.0.0",
        description=(
            "Формальна імплементація контракту REST API за методологією SDD та TDD "
            "(`spec/srs.tex`, `spec/srs-addendum.md`, `spec/openapi.yaml`)."
        ),
    )

    @application.middleware("http")
    async def telemetry_and_trace_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_trace_id = request.headers.get("X-Trace-Id")
        trace_id = incoming_trace_id.strip() if incoming_trace_id else generate_trace_id("trc")
        request.state.trace_id = trace_id
        token = set_trace_id(trace_id)

        start_perf = time.perf_counter()
        log_event(
            TRACE_LEVEL_NUM,
            "API",
            "HTTP_REQUEST_START",
            f"Incoming request: {request.method} {request.url.path}",
            context={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
            },
            trace_id=trace_id,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 3)
            log_event(
                logging.ERROR,
                "API",
                "HTTP_REQUEST_UNHANDLED_ERROR",
                f"Unhandled exception during {request.method} {request.url.path}: {exc}",
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
                trace_id=trace_id,
            )
            reset_trace_id(token)
            raise

        duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 3)
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)

        log_event(
            logging.INFO,
            "API",
            "HTTP_REQUEST_END",
            f"Completed {request.method} {request.url.path} -> HTTP {response.status_code} in {duration_ms} ms",
            context={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "sla_100ms_passed": duration_ms <= 100.0,
            },
            trace_id=trace_id,
        )
        reset_trace_id(token)
        return response

    register_exception_handlers(application)
    application.include_router(api_v1_router)
    return application


app = create_app()
