"""
Дворівнева система структурованого логування та телеметрії (REQ-NF-009, REQ-NF-010).

Забезпечує:
1. Кастомний рівень логування TRACE = 5 для детального трасування SQL, математичних моделей та HTTP.
2. Запис суворо валідного NDJSON (Newline-Delimited JSON) у файл `logs/system-execution.log`
   із обов'язковими полями: `timestamp`, `level`, `trace_id`, `component`, `operation`, `message`, `context`.
3. Вивід у STDOUT для оперативної діагностики під час виконання автотестів.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

ComponentType = Literal["API", "SERVICE", "DB", "MATH_ENGINE", "TEST_RUNNER"]
VALID_COMPONENTS: set[str] = {"API", "SERVICE", "DB", "MATH_ENGINE", "TEST_RUNNER"}

_trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="trc-system"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE_PATH = LOG_DIR / "system-execution.log"


def generate_trace_id(prefix: str = "trc") -> str:
    """Генерує унікальний ідентифікатор трасування контрольної точки."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def get_trace_id() -> str:
    """Повертає поточний trace_id із контексту виконання запиту або тесту."""
    return _trace_id_ctx.get()


def set_trace_id(trace_id: str) -> contextvars.Token[str]:
    """Встановлює trace_id у поточному контексті виконання."""
    return _trace_id_ctx.set(trace_id)


def reset_trace_id(token: contextvars.Token[str]) -> None:
    """Відновлює попередній trace_id у контексті виконання."""
    _trace_id_ctx.reset(token)


class TraceLogger(logging.Logger):
    """Розширений клас логера з підтримкою методу .trace() (рівень 5)."""

    def trace(
        self,
        msg: object,
        *args: object,
        exc_info: Any = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.isEnabledFor(TRACE_LEVEL_NUM):
            self._log(
                TRACE_LEVEL_NUM,
                msg,
                args,
                exc_info=exc_info,
                extra=extra,
                stack_info=stack_info,
                stacklevel=stacklevel + 1,
            )


logging.setLoggerClass(TraceLogger)


class JsonFormatter(logging.Formatter):
    """
    Форматувальник NDJSON-рядків для `logs/system-execution.log` (REQ-NF-009).
    Гарантує, що кожен запис є одним чистим JSON-об'єктом на рядок без текстових префіксів.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        component = getattr(record, "component", "API")
        if component not in VALID_COMPONENTS:
            component = "API"
        operation = getattr(record, "operation", record.funcName or "unknown")
        context = getattr(record, "context", None)
        if not isinstance(context, dict):
            context = {}

        if record.exc_info:
            context = {
                **context,
                "exception": self.formatException(record.exc_info),
            }

        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "trace_id": str(trace_id),
            "component": component,
            "operation": str(operation),
            "message": record.getMessage(),
            "context": context,
        }
        return json.dumps(payload, ensure_ascii=False)


class StdoutFormatter(logging.Formatter):
    """Форматувальник для оперативного читання у STDOUT (REQ-NF-010)."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        component = getattr(record, "component", "API")
        operation = getattr(record, "operation", record.funcName or "unknown")
        return (
            f"[{timestamp}] [{record.levelname:<8}] [trace_id={trace_id}] "
            f"[{component}:{operation}] {record.getMessage()}"
        )


def setup_logger(name: str = "workout_tracker") -> TraceLogger:
    """Ініціалізує та повертає налаштований екземпляр TraceLogger."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    assert isinstance(logger, TraceLogger)

    if logger.handlers:
        return logger

    logger.setLevel(TRACE_LEVEL_NUM)
    logger.propagate = False

    # 1. FileHandler -> чистий NDJSON у logs/system-execution.log
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(TRACE_LEVEL_NUM)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # 2. StreamHandler -> структурований текстовий вивід у STDOUT
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(TRACE_LEVEL_NUM)
    stdout_handler.setFormatter(StdoutFormatter())
    logger.addHandler(stdout_handler)

    return logger


app_logger: TraceLogger = setup_logger()


def log_event(
    level: int | str,
    component: ComponentType,
    operation: str,
    message: str,
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """
    Уніфікована функція запису структурованої події телеметрії у NDJSON та STDOUT.
    """
    if isinstance(level, str):
        level_num = (
            TRACE_LEVEL_NUM
            if level.upper() == "TRACE"
            else getattr(logging, level.upper(), logging.INFO)
        )
    else:
        level_num = level

    extra_data: dict[str, Any] = {
        "trace_id": trace_id or get_trace_id(),
        "component": component,
        "operation": operation,
        "context": context or {},
    }
    app_logger.log(level_num, message, extra=extra_data, stacklevel=2)
