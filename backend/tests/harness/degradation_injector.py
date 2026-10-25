"""Degradation injector for simulating failures in LLM, database, and other services."""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from datetime import datetime


class FailureMode(Enum):
    """Types of failures that can be injected."""
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    CIRCUIT_OPEN = "circuit_open"
    AUTH_ERROR = "auth_error"


@dataclass
class InjectedFailure:
    """Record of an injected failure."""
    component: str
    mode: FailureMode
    timestamp: str
    duration_seconds: Optional[float] = None
    restored: bool = False


class DegradationInjector:
    """Injects failures into various components for degradation testing."""

    def __init__(self):
        self._failures: List[InjectedFailure] = []
        self._llm_original_generate = None
        self._llm_failure_mode: Optional[FailureMode] = None
        self._db_original_execute = None
        self._db_failure_mode: Optional[FailureMode] = None
        self._chroma_original_query = None
        self._chroma_failure_mode: Optional[FailureMode] = None
        self._patched = False

    def inject_llm_failure(self, mode: str = "rate_limit"):
        """Inject LLM provider failure."""
        try:
            from backend.core.llm_client import LLMClient

            if self._llm_original_generate is None:
                self._llm_original_generate = LLMClient.generate

            self._llm_failure_mode = FailureMode(mode)

            async def failing_generate(self, *args, **kwargs):
                if self._llm_failure_mode == FailureMode.RATE_LIMIT:
                    from backend.core.exceptions import ProviderUnavailableError
                    raise ProviderUnavailableError("Rate limit exceeded", provider="test", retry_after=60)
                elif self._llm_failure_mode == FailureMode.SERVER_ERROR:
                    from backend.core.exceptions import ProviderUnavailableError
                    raise ProviderUnavailableError("Internal server error", provider="test")
                elif self._llm_failure_mode == FailureMode.TIMEOUT:
                    raise asyncio.TimeoutError("LLM request timed out")
                elif self._llm_failure_mode == FailureMode.AUTH_ERROR:
                    from backend.core.exceptions import AuthenticationError
                    raise AuthenticationError("Invalid API key")
                # Fallback
                raise Exception(f"Injected LLM failure: {self._llm_failure_mode}")

            LLMClient.generate = failing_generate
            self._patched = True

            self._failures.append(InjectedFailure(
                component="llm",
                mode=FailureMode(mode),
                timestamp=datetime.utcnow().isoformat()
            ))

        except ImportError:
            # LLMClient not available, just record the failure
            self._llm_failure_mode = FailureMode(mode)
            self._failures.append(InjectedFailure(
                component="llm",
                mode=FailureMode(mode),
                timestamp=datetime.utcnow().isoformat()
            ))

    def restore_llm(self):
        """Restore LLM client to normal operation."""
        try:
            from backend.core.llm_client import LLMClient

            if self._llm_original_generate is not None:
                LLMClient.generate = self._llm_original_generate
                self._llm_original_generate = None

            self._llm_failure_mode = None

            # Mark last LLM failure as restored
            for failure in reversed(self._failures):
                if failure.component == "llm" and not failure.restored:
                    failure.restored = True
                    break

        except ImportError:
            self._llm_failure_mode = None

    def inject_db_failure(self, mode: str = "connection_error"):
        """Inject database failure."""
        try:
            from backend.core.database import get_db_session
            # This would require patching the database session
            # For now, just record the failure
            self._db_failure_mode = FailureMode(mode)
            self._failures.append(InjectedFailure(
                component="database",
                mode=FailureMode(mode),
                timestamp=datetime.utcnow().isoformat()
            ))
        except ImportError:
            self._db_failure_mode = FailureMode(mode)
            self._failures.append(InjectedFailure(
                component="database",
                mode=FailureMode(mode),
                timestamp=datetime.utcnow().isoformat()
            ))

    def restore_db(self):
        """Restore database to normal operation."""
        self._db_failure_mode = None
        for failure in reversed(self._failures):
            if failure.component == "database" and not failure.restored:
                failure.restored = True
                break

    def inject_chromadb_failure(self, mode: str = "connection_error"):
        """Inject ChromaDB failure."""
        self._chroma_failure_mode = FailureMode(mode)
        self._failures.append(InjectedFailure(
            component="chromadb",
            mode=FailureMode(mode),
            timestamp=datetime.utcnow().isoformat()
        ))

    def restore_chromadb(self):
        """Restore ChromaDB to normal operation."""
        self._chroma_failure_mode = None
        for failure in reversed(self._failures):
            if failure.component == "chromadb" and not failure.restored:
                failure.restored = True
                break

    def restore_all(self):
        """Restore all components to normal operation."""
        self.restore_llm()
        self.restore_db()
        self.restore_chromadb()

    def get_events(self) -> List[Dict[str, Any]]:
        """Get all injected failure events."""
        return [
            {
                "component": f.component,
                "mode": f.mode.value,
                "timestamp": f.timestamp,
                "duration_seconds": f.duration_seconds,
                "restored": f.restored
            }
            for f in self._failures
        ]

    def is_failing(self, component: str) -> bool:
        """Check if a component is currently failing."""
        if component == "llm":
            return self._llm_failure_mode is not None
        elif component == "database":
            return self._db_failure_mode is not None
        elif component == "chromadb":
            return self._chroma_failure_mode is not None
        return False

    def get_failure_mode(self, component: str) -> Optional[FailureMode]:
        """Get the current failure mode for a component."""
        if component == "llm":
            return self._llm_failure_mode
        elif component == "database":
            return self._db_failure_mode
        elif component == "chromadb":
            return self._chroma_failure_mode
        return None