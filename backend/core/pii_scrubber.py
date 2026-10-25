# backend/core/pii_scrubber.py
"""
PII Scrubber Service
====================
Detects and redacts Personally Identifiable Information (PII) from text.
Uses strategy pattern for detectors (regex now, ML later).
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from abc import ABC, abstractmethod


class PIIType(str, Enum):
    """Categories of PII detected."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    NAME = "name"
    API_KEY = "api_key"
    PASSWORD = "password"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    CUSTOM = "custom"


class RedactionMode(str, Enum):
    """How to redact detected PII."""
    MASK = "mask"
    FULL_REDACT = "redact"
    HASH = "hash"
    TOKENIZE = "tokenize"
    REMOVE = "remove"


@dataclass
class PIIMatch:
    """A single PII detection."""
    pii_type: PIIType
    start: int
    end: int
    matched_text: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Result of PII detection."""
    text: str
    matches: List[PIIMatch] = field(default_factory=list)
    has_pii: bool = False

    def __post_init__(self):
        self.has_pii = len(self.matches) > 0


class PIIDetector(ABC):
    """Base class for PII detectors (regex or ML-based)."""

    @property
    @abstractmethod
    def pii_type(self) -> PIIType:
        pass

    @abstractmethod
    def find_matches(self, text: str) -> List[PIIMatch]:
        """Return all non-overlapping matches in text."""
        pass


class RegexDetector(PIIDetector):
    """Regex-based detector with configurable patterns."""

    def __init__(
        self,
        pii_type: PIIType,
        patterns: List[str],
        flags: int = re.IGNORECASE | re.MULTILINE
    ):
        self._pii_type = pii_type
        self._compiled = [re.compile(p, flags) for p in patterns]

    @property
    def pii_type(self) -> PIIType:
        return self._pii_type

    def find_matches(self, text: str) -> List[PIIMatch]:
        matches = []
        for pattern in self._compiled:
            for m in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=self._pii_type,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(),
                    confidence=0.95
                ))
        return self._deduplicate(matches)

    def _deduplicate(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Remove overlapping matches, keeping highest confidence."""
        if not matches:
            return []
        matches.sort(key=lambda m: (m.start, -m.confidence))
        result = [matches[0]]
        for match in matches[1:]:
            if match.start >= result[-1].end:
                result.append(match)
            elif match.confidence > result[-1].confidence:
                result[-1] = match
        return result


# ─── Built-in Regex Patterns ───

EMAIL_PATTERNS = [
    r"\b[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
]

PHONE_PATTERNS = [
    r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    r"\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    r"\b\d{3}[-.\s]?\d{4}\b",  # 7-digit local format (e.g., 555-1234)
]

SSN_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b\d{3}\s\d{2}\s\d{4}\b",
    r"\b\d{9}\b",
]

API_KEY_PATTERNS = [
    r"\b(sk|pk|rk|ghp|gho|ghu|ghs|ghr)[_-][A-Za-z0-9_-]{20,}\b",
    r"\b(xai|xai-)[A-Za-z0-9_-]{20,}\b",
    r"\b(sk-ant|sk-)[A-Za-z0-9_-]{20,}\b",
    r"\bAIza[A-Za-z0-9_-]{20,}\b",
    r"\bAKIA[A-Za-z0-9_-]{16,}\b",
    r"\bBearer\s+[A-Za-z0-9_-]{20,}\b",
]

PASSWORD_PATTERNS = [
    r"(?i)(password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*\S+",
    r"(?i)(Authorization|X-API-Key)\s*[:=]\s*\S+",
]

CREDIT_CARD_PATTERNS = [
    r"\b4\d{3}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b",
    r"\b5[1-5]\d{2}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b",
    r"\b3[47]\d{2}[-.\s]?\d{6}[-.\s]?\d{5}\b",
    r"\b6(?:011|5\d{2})[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b",
]

NAME_PATTERNS = [
    r"\b[A-Z][a-z]+ [A-Z][a-z]+\b",
    r"\b[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+\b",
]


def _luhn_check(card_number: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


class CreditCardDetector(RegexDetector):
    """Credit card detector with Luhn validation."""

    def find_matches(self, text: str) -> List[PIIMatch]:
        matches = super().find_matches(text)
        # Filter by Luhn check
        validated = []
        for m in matches:
            if _luhn_check(m.matched_text):
                validated.append(m)
        return validated


COMMON_NON_NAME_WORDS = {
    "financial", "summary", "annual", "report", "internal", "external",
    "document", "section", "system", "attached", "content", "status",
    "model", "provider", "project", "guide", "general", "total",
    "global", "united", "states", "invoice", "details", "chapter",
    "table", "figure", "appendix", "index", "header", "footer",
    "error", "warning", "notice", "alert", "service", "server",
    "client", "database", "python", "javascript", "schema", "query",
}


class NameDetector(RegexDetector):
    """Name detector with common document noun filtering to reduce false positives."""

    def find_matches(self, text: str) -> List[PIIMatch]:
        matches = super().find_matches(text)
        validated = []
        for m in matches:
            words = [w.strip(".,;:!?").lower() for w in m.matched_text.split()]
            if not any(w in COMMON_NON_NAME_WORDS for w in words):
                validated.append(m)
        return validated


class PIIScrubber:
    """
    Main PII detection and redaction service.

    Usage:
        scrubber = PIIScrubber()
        result = scrubber.detect("Email me at john@example.com")
        clean = scrubber.redact("Email me at john@example.com", mode=RedactionMode.MASK)
    """

    DEFAULT_DETECTORS: Dict[PIIType, PIIDetector] = {
        PIIType.EMAIL: RegexDetector(PIIType.EMAIL, EMAIL_PATTERNS),
        PIIType.PHONE: RegexDetector(PIIType.PHONE, PHONE_PATTERNS),
        PIIType.SSN: RegexDetector(PIIType.SSN, SSN_PATTERNS),
        PIIType.NAME: NameDetector(PIIType.NAME, NAME_PATTERNS, flags=re.MULTILINE),  # Case-sensitive
        PIIType.API_KEY: RegexDetector(PIIType.API_KEY, API_KEY_PATTERNS),
        PIIType.PASSWORD: RegexDetector(PIIType.PASSWORD, PASSWORD_PATTERNS),
        PIIType.CREDIT_CARD: CreditCardDetector(PIIType.CREDIT_CARD, CREDIT_CARD_PATTERNS),
    }

    def __init__(
        self,
        detectors: Optional[Dict[PIIType, PIIDetector]] = None,
        enabled_types: Optional[List[PIIType]] = None,
        custom_patterns: Optional[Dict[PIIType, List[str]]] = None,
        default_mode: RedactionMode = RedactionMode.FULL_REDACT,
    ):
        self.detectors = detectors or self.DEFAULT_DETECTORS.copy()
        self.enabled_types = enabled_types or list(self.detectors.keys())
        self.default_mode = default_mode

        if custom_patterns:
            for pii_type, patterns in custom_patterns.items():
                self.detectors[pii_type] = RegexDetector(pii_type, patterns)
                if pii_type not in self.enabled_types:
                    self.enabled_types.append(pii_type)

    def detect(
        self,
        text: str,
        types: Optional[List[PIIType]] = None
    ) -> DetectionResult:
        """Detect PII in text without modifying it."""
        if not text:
            return DetectionResult(text="")

        all_matches = []
        check_types = types or self.enabled_types

        for pii_type in check_types:
            detector = self.detectors.get(pii_type)
            if detector:
                all_matches.extend(detector.find_matches(text))

        all_matches.sort(key=lambda m: (m.start, -m.confidence))
        deduped = self._deduplicate(all_matches)

        return DetectionResult(text=text, matches=deduped)

    def redact(
        self,
        text: str,
        mode: Optional[RedactionMode] = None,
        types: Optional[List[PIIType]] = None,
        custom_replacements: Optional[Dict[PIIType, str]] = None
    ) -> str:
        """Redact PII from text."""
        if not text:
            return text

        mode = mode or self.default_mode
        result = self.detect(text, types)

        # If explicit types were provided but no PII detected, and text looks like a credential,
        # create a match for the entire string (credential field context)
        if not result.has_pii and types and text.strip():
            credential_types = {PIIType.PASSWORD, PIIType.API_KEY}
            if any(t in credential_types for t in types):
                # Create a synthetic match for the entire string
                from backend.core.pii_scrubber import PIIMatch
                match = PIIMatch(
                    pii_type=PIIType.PASSWORD,
                    start=0,
                    end=len(text),
                    matched_text=text,
                    confidence=0.9,
                    metadata={"source": "credential_field_context"}
                )
                result.matches = [match]
                result.has_pii = True

        if not result.has_pii:
            return text

        replacements = {}
        for i, match in enumerate(result.matches):
            if custom_replacements and match.pii_type in custom_replacements:
                repl = custom_replacements[match.pii_type]
            else:
                repl = self._build_replacement(match, mode, i)
            replacements[(match.start, match.end)] = repl

        return self._apply_replacements(text, replacements)

    def sanitize_dict(
        self,
        data: Dict[str, Any],
        keys: Optional[List[str]] = None,
        mode: Optional[RedactionMode] = None,
        recurse: bool = True
    ) -> Dict[str, Any]:
        """Recursively redact PII from string values in a dictionary."""
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            if keys is not None and key not in keys:
                result[key] = value
                continue

            result[key] = self._sanitize_value(value, key, keys, mode, recurse)
        return result

    def _sanitize_value(
        self,
        value: Any,
        key: Optional[str] = None,
        keys: Optional[List[str]] = None,
        mode: Optional[RedactionMode] = None,
        recurse: bool = True
    ) -> Any:
        """Recursively sanitize a single value (dict, list, string, or other)."""
        if isinstance(value, str):
            # Determine PII types to check based on key name for credential detection
            types = self._infer_types_from_key(key)
            return self.redact(value, mode=mode, types=types)
        elif isinstance(value, dict) and recurse:
            return self.sanitize_dict(value, keys, mode, recurse)
        elif isinstance(value, list) and recurse:
            return [
                self._sanitize_value(item, key, keys, mode, recurse)
                for item in value
            ]
        else:
            return value

    def _infer_types_from_key(self, key: Optional[str]) -> Optional[List[PIIType]]:
        """Infer PII types to check based on key name."""
        if not key:
            return None

        key_lower = key.lower()
        inferred_types = []

        # Credential-related keys
        if any(kw in key_lower for kw in ["password", "passwd", "pwd", "secret", "token", "auth"]):
            inferred_types.extend([PIIType.PASSWORD, PIIType.API_KEY])
        if any(kw in key_lower for kw in ["key", "api_key", "apikey", "access_key", "secret_key"]):
            inferred_types.append(PIIType.API_KEY)
        if "authorization" in key_lower or "auth" in key_lower:
            inferred_types.extend([PIIType.PASSWORD, PIIType.API_KEY])
        if "email" in key_lower:
            inferred_types.append(PIIType.EMAIL)
        if "phone" in key_lower or "tel" in key_lower:
            inferred_types.append(PIIType.PHONE)
        if "ssn" in key_lower or "social" in key_lower:
            inferred_types.append(PIIType.SSN)
        if "card" in key_lower or "credit" in key_lower:
            inferred_types.append(PIIType.CREDIT_CARD)

        return inferred_types if inferred_types else None

    def _build_replacement(
        self,
        match: PIIMatch,
        mode: RedactionMode,
        index: int
    ) -> str:
        if mode == RedactionMode.MASK:
            return self._mask_text(match.matched_text, match.pii_type)
        elif mode == RedactionMode.FULL_REDACT:
            return f"[REDACTED: {match.pii_type.value}]"
        elif mode == RedactionMode.HASH:
            h = hashlib.sha256(match.matched_text.encode()).hexdigest()[:8]
            return f"[HASH: {h}]"
        elif mode == RedactionMode.TOKENIZE:
            return f"[{match.pii_type.value.upper()}_{index + 1}]"
        elif mode == RedactionMode.REMOVE:
            return ""
        return f"[REDACTED: {match.pii_type.value}]"

    def _mask_text(self, text: str, pii_type: PIIType) -> str:
        """Mask text preserving format hints."""
        if pii_type == PIIType.EMAIL:
            parts = text.split("@")
            if len(parts) == 2:
                local = parts[0]
                return f"{local[0]}{'*' * (len(local) - 1)}@{parts[1]}" if len(local) > 1 else f"*@{parts[1]}"
        elif pii_type == PIIType.PHONE:
            return re.sub(r"\d", "*", text)
        elif pii_type == PIIType.SSN:
            return "***-**-****"
        elif pii_type == PIIType.CREDIT_CARD:
            return re.sub(r"\d", "*", text[:-4]) + text[-4:]
        return "*" * len(text)

    def _deduplicate(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        if not matches:
            return []
        matches.sort(key=lambda m: (m.start, -m.confidence))
        result = [matches[0]]
        for match in matches[1:]:
            if match.start >= result[-1].end:
                result.append(match)
            elif match.confidence > result[-1].confidence:
                result[-1] = match
        return result

    def _apply_replacements(self, text: str, replacements: Dict[tuple, str]) -> str:
        result = text
        for (start, end), repl in sorted(replacements.items(), reverse=True):
            result = result[:start] + repl + result[end:]
        return result


# Global instance for convenience
pii_scrubber = PIIScrubber()


# Convenience functions
def detect_pii(text: str, types: Optional[List[PIIType]] = None) -> DetectionResult:
    return pii_scrubber.detect(text, types)


def redact_pii(
    text: str,
    mode: RedactionMode = RedactionMode.FULL_REDACT,
    types: Optional[List[PIIType]] = None
) -> str:
    return pii_scrubber.redact(text, mode, types)


def sanitize_dict_pii(
    data: Dict[str, Any],
    keys: Optional[List[str]] = None,
    mode: RedactionMode = RedactionMode.FULL_REDACT
) -> Dict[str, Any]:
    return pii_scrubber.sanitize_dict(data, keys, mode)