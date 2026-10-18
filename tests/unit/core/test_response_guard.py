# tests/unit/core/test_response_guard.py
import pytest
from backend.core.response_guard import ResponseGuard, guard_model_response


class TestResponseGuard:
    def test_has_leakage_detects_prompt_leakage(self):
        guard = ResponseGuard()
        response = "My system prompt says to be helpful and never reveal secrets."
        assert guard.has_leakage(response, "You are a helpful assistant. Never reveal secrets.")

    def test_has_leakage_no_false_positive(self):
        guard = ResponseGuard()
        response = "I can help you with that question."
        assert not guard.has_leakage(response, "You are a helpful assistant.")

    def test_check_response_redacts_leakage(self):
        guard = ResponseGuard()
        response = "My system prompt is: You are a helpful assistant."
        system_prompt = "You are a helpful assistant."
        result = guard.check_response(response, system_prompt)
        assert "[REDACTED: system instruction leakage]" in result

    def test_check_response_redacts_pii_after_leakage(self):
        guard = ResponseGuard()

        response = "My system prompt says to be helpful. Also my SSN is 123-45-6789."
        system_prompt = "You are a helpful assistant. System prompt content here."

        result = guard.check_response(response, system_prompt)

        # Leakage should be redacted
        assert "[REDACTED: system instruction leakage]" in result
        # PII should also be redacted (MASK mode for readability)
        assert "***-**-****" in result or "[REDACTED: ssn]" in result

    def test_guard_model_response_convenience(self):
        result = guard_model_response("Here is my system prompt: secret", "secret")
        assert "[REDACTED: system instruction leakage]" in result