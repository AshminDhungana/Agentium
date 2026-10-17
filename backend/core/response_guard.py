"""
Response Guard
==============
Detects and redacts system prompt leakage and sensitive governance instructions
from LLM responses before delivery to the user or caller.
"""

import re
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class ResponseGuard:
    """Detects and redacts system prompt leakage in model responses."""

    LEAKAGE_INDICATORS = [
        r"(?i)(?:my|the)\s+system\s+prompt\s*(?:is|says|reads|consists\s+of|:)",
        r"(?i)(?:here\s+(?:is|are)|this\s+is)\s+(?:my|the)\s*(?:system\s+)?(?:prompt|instructions|rules|directives)",
        r"(?i)i\s+was\s+(?:told|instructed)\s+to\s+(?:not\s+)?reveal",
        r"(?i)constitutional\s+guard",
        r"(?i)tier\s+\d+xxxx",
        r"GOVERNANCE & DELEGATION PROTOCOL",
        r"─── END OF SYSTEM INSTRUCTIONS ───",
        r"─── BEGIN USER MESSAGE ───",
        r"─── END USER MESSAGE ───",
    ]

    REPLACEMENT = "[REDACTED: system instruction leakage]"

    def __init__(self, *, min_verbatim_length: int = 60):
        self.min_verbatim_length = min_verbatim_length
        self._compiled_indicators = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.LEAKAGE_INDICATORS
        ]

    def has_leakage(self, response: str, system_prompt: str = "") -> bool:
        """Check if response contains obvious signs of prompt leakage."""
        if not response:
            return False

        for pattern in self._compiled_indicators:
            if pattern.search(response):
                return True

        if system_prompt and len(system_prompt) > self.min_verbatim_length:
            # Check for significant verbatim chunk matches
            lines = [
                line.strip()
                for line in system_prompt.splitlines()
                if len(line.strip()) >= self.min_verbatim_length
            ]
            for line in lines:
                if line in response:
                    return True

        return False

    def check_response(self, response: str, system_prompt: str = "") -> str:
        """
        Redact obvious system prompt leakage from model response.

        Args:
            response: Model-generated output text.
            system_prompt: Optional system prompt to check for verbatim copying.

        Returns:
            Sanitized response string.
        """
        if not response:
            return response

        cleaned = response
        detected = False

        # 1. Redact leakage indicator patterns
        for pattern in self._compiled_indicators:
            if pattern.search(cleaned):
                detected = True
                cleaned = pattern.sub(self.REPLACEMENT, cleaned)

        # 2. Check for substantial verbatim substrings from the system prompt
        if system_prompt and len(system_prompt) >= self.min_verbatim_length:
            lines = [
                line.strip()
                for line in system_prompt.splitlines()
                if len(line.strip()) >= self.min_verbatim_length
            ]
            for line in lines:
                if line in cleaned:
                    detected = True
                    cleaned = cleaned.replace(line, self.REPLACEMENT)

        if detected:
            logger.warning("[ResponseGuard] System prompt leakage detected and redacted in response.")

        return cleaned


# Global instance
response_guard = ResponseGuard()


def guard_model_response(response: str, system_prompt: str = "") -> str:
    """Convenience helper to redact system prompt leakage."""
    return response_guard.check_response(response, system_prompt)
