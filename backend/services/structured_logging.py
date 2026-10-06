"""
Structured Logging for Agentium - Section 14.6
Provides JSON-structured logging with request_id correlation across HTTP → Celery → WebSocket.
"""

import json
import logging
import uuid
import time
import contextvars
from datetime import datetime
from typing import Any, Dict, Optional
from contextlib import contextmanager
from functools import wraps

# Context variables for request correlation
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
step_name_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("step_name", default=None)
agent_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agent_id", default=None)
task_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("task_id", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation IDs from context
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        step_name = step_name_var.get()
        if step_name:
            log_data["step"] = step_name

        agent_id = agent_id_var.get()
        if agent_id:
            log_data["agent_id"] = agent_id

        task_id = task_id_var.get()
        if task_id:
            log_data["task_id"] = task_id

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "msecs",
                          "message", "msg", "name", "pathname", "process",
                          "processName", "relativeCreated", "thread", "threadName",
                          "exc_info", "exc_text", "stack_info"]:
                if not key.startswith("_"):
                    log_data[key] = value

        return json.dumps(log_data, default=str)


def get_request_id() -> str:
    """Get current request ID or generate a new one."""
    rid = request_id_var.get()
    if not rid:
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current context."""
    request_id_var.set(request_id)


def set_step_name(step: str) -> None:
    """Set the current step name for structured logging."""
    step_name_var.set(step)


def set_agent_id(agent_id: str) -> None:
    """Set the current agent ID for structured logging."""
    agent_id_var.set(agent_id)


def set_task_id(task_id: str) -> None:
    """Set the current task ID for structured logging."""
    task_id_var.set(task_id)


def clear_context() -> None:
    """Clear all context variables."""
    request_id_var.set(None)
    step_name_var.set(None)
    agent_id_var.set(None)
    task_id_var.set(None)


@contextmanager
def structured_log_context(
    request_id: Optional[str] = None,
    step: Optional[str] = None,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
):
    """Context manager for structured logging with correlation IDs."""
    old_request_id = request_id_var.get()
    old_step = step_name_var.get()
    old_agent_id = agent_id_var.get()
    old_task_id = task_id_var.get()

    try:
        if request_id:
            request_id_var.set(request_id)
        elif not old_request_id:
            request_id_var.set(str(uuid.uuid4())[:8])

        if step:
            step_name_var.set(step)
        if agent_id:
            agent_id_var.set(agent_id)
        if task_id:
            task_id_var.set(task_id)

        yield
    finally:
        request_id_var.set(old_request_id)
        step_name_var.set(old_step)
        agent_id_var.set(old_agent_id)
        task_id_var.set(old_task_id)


def log_structured(
    logger: logging.Logger,
    level: int,
    message: str,
    step: Optional[str] = None,
    duration_ms: Optional[float] = None,
    tokens: Optional[int] = None,
    status: Optional[str] = None,
    **kwargs
) -> None:
    """Log a structured message with correlation IDs and optional metrics."""
    extra = {}

    # Add context IDs
    request_id = request_id_var.get()
    if request_id:
        extra["request_id"] = request_id

    step_name = step or step_name_var.get()
    if step_name:
        extra["step"] = step_name

    agent_id = agent_id_var.get()
    if agent_id:
        extra["agent_id"] = agent_id

    task_id = task_id_var.get()
    if task_id:
        extra["task_id"] = task_id

    # Add metrics
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if tokens is not None:
        extra["tokens"] = tokens
    if status is not None:
        extra["status"] = status

    # Add any additional kwargs
    extra.update(kwargs)

    logger.log(level, message, extra=extra)


class StructuredLogger:
    """Wrapper for structured logging with automatic context injection."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **kwargs):
        log_structured(self.logger, level, message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


@contextmanager
def timed_step(logger: StructuredLogger, step: str, **kwargs):
    """Context manager that logs step start/end with timing."""
    start = time.perf_counter()
    set_step_name(step)
    logger.info(f"Step started: {step}", step=step, status="started", **kwargs)
    try:
        yield
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"Step completed: {step}", step=step, duration_ms=duration_ms, status="completed", **kwargs)
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(f"Step failed: {step}: {e}", step=step, duration_ms=duration_ms, status="failed", error=str(e), **kwargs)
        raise


def structured_task(logger_name: Optional[str] = None):
    """Decorator for Celery tasks to add structured logging with request_id propagation."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract request_id from kwargs if passed
            request_id = kwargs.pop("_request_id", None)
            task_id = kwargs.pop("_task_id", None)
            agent_id = kwargs.pop("_agent_id", None)

            logger = get_structured_logger(logger_name or func.__module__)

            with structured_log_context(request_id=request_id, task_id=task_id, agent_id=agent_id):
                logger.info(f"Task started: {func.__name__}", step=func.__name__, status="started")
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.info(f"Task completed: {func.__name__}", step=func.__name__, duration_ms=duration_ms, status="completed")
                    return result
                except Exception as e:
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.error(f"Task failed: {func.__name__}: {e}", step=func.__name__, duration_ms=duration_ms, status="failed", error=str(e))
                    raise
        return wrapper
    return decorator


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure root logger with structured JSON formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]

    # Also configure specific loggers to use structured format
    for logger_name in ["backend.services", "backend.api", "backend.tasks"]:
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler]
        logger.setLevel(level)
        logger.propagate = False