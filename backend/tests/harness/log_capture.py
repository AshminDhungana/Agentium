"""Log capture for structured logging verification."""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class CapturedLog:
    """A captured structured log entry."""
    timestamp: str
    level: str
    logger: str
    message: str
    extra: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    step: Optional[str] = None
    duration_ms: Optional[float] = None
    tokens: Optional[int] = None
    status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "extra": self.extra,
            "request_id": self.request_id,
            "step": self.step,
            "duration_ms": self.duration_ms,
            "tokens": self.tokens,
            "status": self.status
        }


class LogCapture:
    """Captures structured logs to memory buffer for assertions."""

    def __init__(self, loggers: Optional[List[str]] = None):
        self._logs: List[CapturedLog] = []
        self._handler = None
        self._loggers = loggers or [
            "backend.services.agent_orchestrator",
            "backend.services.task_executor",
            "backend.core.loop_detector",
            "backend.services.token_optimizer",
            "backend.services.structured_logging"
        ]
        self._original_handlers = {}
        self._started = False

    def start(self):
        """Start capturing logs."""
        if self._started:
            return

        self._handler = _LogCaptureHandler(self)
        self._handler.setLevel(logging.DEBUG)

        # Add handler to target loggers
        for logger_name in self._loggers:
            logger = logging.getLogger(logger_name)
            self._original_handlers[logger_name] = logger.handlers[:]
            logger.addHandler(self._handler)
            logger.setLevel(logging.DEBUG)

        # Also capture root logger
        root_logger = logging.getLogger()
        self._original_handlers["root"] = root_logger.handlers[:]
        root_logger.addHandler(self._handler)

        self._started = True

    def stop(self):
        """Stop capturing logs."""
        if not self._started:
            return

        # Restore original handlers
        for logger_name, handlers in self._original_handlers.items():
            logger = logging.getLogger(logger_name) if logger_name != "root" else logging.getLogger()
            logger.handlers = handlers

        self._handler = None
        self._started = False

    def add_log(self, record: logging.LogRecord):
        """Add a log record from the handler."""
        # Extract structured fields
        extra = getattr(record, '__dict__', {})
        structured_extra = {
            k: v for k, v in extra.items()
            if k not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                        'levelname', 'levelno', 'lineno', 'module', 'msecs',
                        'message', 'msg', 'name', 'pathname', 'process',
                        'processName', 'relativeCreated', 'thread', 'threadName',
                        'exc_info', 'exc_text', 'stack_info']
        }

        log = CapturedLog(
            timestamp=datetime.fromtimestamp(record.created).isoformat(),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            extra=structured_extra,
            request_id=structured_extra.get('request_id'),
            step=structured_extra.get('step'),
            duration_ms=structured_extra.get('duration_ms'),
            tokens=structured_extra.get('tokens'),
            status=structured_extra.get('status')
        )
        self._logs.append(log)

    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all captured logs as dictionaries."""
        return [log.to_dict() for log in self._logs]

    def get_logs_raw(self) -> List[CapturedLog]:
        """Get all captured logs as objects."""
        return self._logs

    def clear(self):
        """Clear captured logs."""
        self._logs.clear()

    def filter_by_request_id(self, request_id: str) -> List[Dict[str, Any]]:
        """Filter logs by correlation ID."""
        return [log.to_dict() for log in self._logs if log.request_id == request_id]

    def filter_by_step(self, step: str) -> List[Dict[str, Any]]:
        """Filter logs by step."""
        return [log.to_dict() for log in self._logs if log.step == step]

    def filter_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Filter logs by status."""
        return [log.to_dict() for log in self._logs if log.status == status]


class _LogCaptureHandler(logging.Handler):
    """Logging handler that captures records to LogCapture."""

    def __init__(self, capture: LogCapture):
        super().__init__()
        self._capture = capture

    def emit(self, record: logging.LogRecord):
        try:
            self._capture.add_log(record)
        except Exception:
            self.handleError(record)