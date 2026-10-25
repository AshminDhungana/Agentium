"""
Task 4 — PII Scrubbing & Multi-Tenant Session Isolation.

Verifies:
1. All 7 PII types detected correctly (including Luhn validation for credit cards)
2. All 5 redaction modes produce correct output format
3. Nested dict sanitization recurses properly
4. Credentials never appear in plain text in logs
"""

import os
import pytest
import logging
import re
from backend.core.pii_scrubber import (
    PIIScrubber,
    PIIType,
    RedactionMode,
    DetectionResult,
    redact_pii,
    sanitize_dict_pii,
)

os.environ["TESTING"] = "true"


class TestPIIScrubberCore:
    """Core PII scrubber functionality tests."""

    @pytest.fixture
    def scrubber(self):
        """Create a PIIScrubber with all detectors enabled including NAME."""
        return PIIScrubber(
            enabled_types=[
                PIIType.EMAIL,
                PIIType.PHONE,
                PIIType.SSN,
                PIIType.NAME,
                PIIType.API_KEY,
                PIIType.PASSWORD,
                PIIType.CREDIT_CARD,
            ]
        )

    @pytest.mark.parametrize("text,pii_type,should_detect", [
        ("Email me at john.doe@example.com", PIIType.EMAIL, True),
        ("Call me at +1-555-123-4567", PIIType.PHONE, True),
        ("SSN: 123-45-6789", PIIType.SSN, True),
        ("API key: sk-ant-abcdefghijklmnopqrstuvwxyz", PIIType.API_KEY, True),
        ("Password: secret123", PIIType.PASSWORD, True),
        ("Card: 4111 1111 1111 1111", PIIType.CREDIT_CARD, True),  # Valid Luhn
        ("Card: 4111 1111 1111 1112", PIIType.CREDIT_CARD, False),  # Invalid Luhn
        ("John Smith", PIIType.NAME, True),
    ])
    def test_all_pii_types_detected(self, scrubber, text, pii_type, should_detect):
        """All 7 PII types detected correctly; credit card validated via Luhn."""
        result = scrubber.detect(text, types=[pii_type])

        detected = any(m.pii_type == pii_type for m in result.matches)
        assert detected == should_detect, (
            f"{pii_type.value}: expected detect={should_detect}, "
            f"got {detected} in '{text}'"
        )

    def test_credit_card_luhn_validation(self, scrubber):
        """Credit card detector validates via Luhn algorithm."""
        valid_cards = ["4111111111111111", "5555555555554444", "378282246310005"]
        invalid_cards = ["4111111111111112", "5555555555554445", "1234567890123456"]

        for card in valid_cards:
            result = scrubber.detect(f"Card: {card}", types=[PIIType.CREDIT_CARD])
            assert result.has_pii, f"Valid card {card} not detected"

        for card in invalid_cards:
            result = scrubber.detect(f"Card: {card}", types=[PIIType.CREDIT_CARD])
            assert not result.has_pii, f"Invalid card {card} incorrectly detected"

    def test_detect_multiple_pii_in_same_text(self, scrubber):
        """Multiple PII types in same text are all detected."""
        text = "Contact john@example.com or call +1-555-123-4567. SSN: 123-45-6789"
        result = scrubber.detect(text)

        assert result.has_pii
        detected_types = {m.pii_type for m in result.matches}
        assert PIIType.EMAIL in detected_types
        assert PIIType.PHONE in detected_types
        assert PIIType.SSN in detected_types


class TestRedactionModes:
    """Test all 5 redaction modes produce correct output format."""

    @pytest.fixture
    def scrubber(self):
        return PIIScrubber()

    @pytest.mark.parametrize("mode,expected_pattern", [
        (RedactionMode.MASK, r"j\*+\@example\.com"),  # j***@example.com
        (RedactionMode.FULL_REDACT, r"\[REDACTED: email\]"),
        (RedactionMode.HASH, r"\[HASH: [a-f0-9]{8}\]"),
        (RedactionMode.TOKENIZE, r"\[EMAIL_1\]"),
        (RedactionMode.REMOVE, r"Email me at "),  # Empty replacement
    ])
    def test_redaction_modes(self, scrubber, mode, expected_pattern):
        """Each redaction mode produces correct output format."""
        text = "Email me at john@example.com"
        result = scrubber.redact(text, mode=mode, types=[PIIType.EMAIL])

        assert re.search(expected_pattern, result), (
            f"Mode {mode}: expected pattern {expected_pattern} in '{result}'"
        )

    def test_mask_mode_preserves_email_domain(self, scrubber):
        """MASK mode preserves email domain, masks local part."""
        text = "Email: john.doe@example.com"
        result = scrubber.redact(text, mode=RedactionMode.MASK, types=[PIIType.EMAIL])

        assert "example.com" in result
        assert "john.doe" not in result
        assert result.count("*") > 0

    def test_mask_mode_preserves_credit_card_last4(self, scrubber):
        """MASK mode preserves last 4 digits of credit card."""
        text = "Card: 4111 1111 1111 1111"
        result = scrubber.redact(text, mode=RedactionMode.MASK, types=[PIIType.CREDIT_CARD])

        assert "1111" in result
        assert result.count("*") > 0

    def test_hash_mode_produces_consistent_hash(self, scrubber):
        """HASH mode produces consistent hash for same input."""
        text = "API key: sk-ant-abcdefghijklmnopqrstuvwxyz"
        result1 = scrubber.redact(text, mode=RedactionMode.HASH, types=[PIIType.API_KEY])
        result2 = scrubber.redact(text, mode=RedactionMode.HASH, types=[PIIType.API_KEY])

        assert result1 == result2
        assert "[HASH:" in result1

    def test_tokenize_mode_increments_index(self, scrubber):
        """TOKENIZE mode increments index for each occurrence."""
        text = "Email john@example.com and jane@example.com"
        result = scrubber.redact(text, mode=RedactionMode.TOKENIZE, types=[PIIType.EMAIL])

        assert "[EMAIL_1]" in result
        assert "[EMAIL_2]" in result

    def test_remove_mode_removes_entire_match(self, scrubber):
        """REMOVE mode removes the PII entirely."""
        text = "Email me at john@example.com please"
        result = scrubber.redact(text, mode=RedactionMode.REMOVE, types=[PIIType.EMAIL])

        assert "john@example.com" not in result
        assert "Email me at  please" == result  # Double space where email was


class TestSanitizeDictRecursive:
    """Test recursive sanitization of nested dicts and lists."""

    @pytest.fixture
    def scrubber(self):
        return PIIScrubber()

    def test_sanitize_dict_recursive(self, scrubber):
        """sanitize_dict recurses into nested dicts and lists."""
        data = {
            "user": {
                "email": "john@example.com",
                "profile": {
                    "phone": "+1-555-123-4567",
                    "address": "123 Main St"
                }
            },
            "contacts": [
                {"name": "Jane Doe", "email": "jane@example.com"},
                {"name": "Bob Smith", "phone": "555-987-6543"}
            ],
            "metadata": "API key: sk-test-abcdefghijklmnop"
        }

        sanitized = scrubber.sanitize_dict(data, mode=RedactionMode.FULL_REDACT)

        # Verify all string values at all levels redacted
        sanitized_str = str(sanitized)
        assert "john@example.com" not in sanitized_str
        assert "jane@example.com" not in sanitized_str
        assert "+1-555-123-4567" not in sanitized_str
        assert "555-987-6543" not in sanitized_str
        assert "sk-test-abcdefghijklmnop" not in sanitized_str
        assert "[REDACTED:" in sanitized_str

        # Verify structure preserved
        assert "user" in sanitized
        assert "profile" in sanitized["user"]
        assert len(sanitized["contacts"]) == 2
        assert "name" in sanitized["contacts"][0]  # Name not in enabled types by default

    def test_sanitize_dict_preserves_non_string_types(self, scrubber):
        """Non-string values (int, bool, None) are preserved."""
        data = {
            "count": 42,
            "active": True,
            "empty": None,
            "email": "test@example.com"
        }

        sanitized = scrubber.sanitize_dict(data, mode=RedactionMode.FULL_REDACT)

        assert sanitized["count"] == 42
        assert sanitized["active"] is True
        assert sanitized["empty"] is None
        assert "[REDACTED: email]" in sanitized["email"]

    def test_sanitize_dict_with_keys_filter(self, scrubber):
        """keys parameter limits which keys to sanitize."""
        data = {
            "email": "john@example.com",
            "name": "John Doe",
            "internal_id": "secret123"
        }

        # Only sanitize 'email' key
        sanitized = scrubber.sanitize_dict(data, keys=["email"], mode=RedactionMode.FULL_REDACT)

        assert "[REDACTED: email]" in sanitized["email"]
        assert sanitized["name"] == "John Doe"  # Not sanitized
        assert sanitized["internal_id"] == "secret123"  # Not sanitized

    def test_sanitize_list_of_strings(self, scrubber):
        """List of strings gets sanitized."""
        data = {
            "emails": ["john@example.com", "jane@example.com", "bob@example.com"]
        }

        sanitized = scrubber.sanitize_dict(data, mode=RedactionMode.FULL_REDACT)

        assert all("[REDACTED: email]" in e for e in sanitized["emails"])

    def test_sanitize_nested_list_of_dicts(self, scrubber):
        """Deeply nested lists of dicts get sanitized."""
        data = {
            "level1": {
                "level2": [
                    {"level3": {"email": "deep@example.com"}},
                    {"level3": {"phone": "555-1234"}}
                ]
            }
        }

        sanitized = scrubber.sanitize_dict(data, mode=RedactionMode.FULL_REDACT)

        assert "[REDACTED: email]" in str(sanitized["level1"]["level2"][0]["level3"])
        assert "[REDACTED: phone]" in str(sanitized["level1"]["level2"][1]["level3"])

    def test_convenience_function_sanitize_dict_pii(self):
        """sanitize_dict_pii convenience function works."""
        data = {"email": "test@example.com"}
        result = sanitize_dict_pii(data, mode=RedactionMode.FULL_REDACT)

        assert "[REDACTED: email]" in result["email"]


class TestCredentialLoggingRedaction:
    """Test that credentials never appear in plain text in logs."""

    @pytest.fixture
    def scrubber(self):
        return PIIScrubber()

    def test_credentials_never_in_plain_text_logs(self, scrubber, caplog):
        """API keys and passwords never appear in plain text in logs."""
        import logging

        # Simulate logging a dict with credentials
        log_data = {
            "api_key": "sk-ant-abcdefghijklmnopqrstuvwxyz",
            "password": "supersecret123",
            "authorization": "Bearer token123",
            "normal_field": "this is fine"
        }

        # Apply scrubber before logging (as production code should)
        sanitized = scrubber.sanitize_dict(log_data, mode=RedactionMode.FULL_REDACT)

        # Log the sanitized data
        logger = logging.getLogger("test_credential_logging")
        logger.info("Request data: %s", sanitized)

        # Check captured logs
        log_output = caplog.text
        assert "sk-ant-" not in log_output
        assert "supersecret123" not in log_output
        assert "Bearer token123" not in log_output
        assert "[REDACTED:" in log_output or "[HASH:" in log_output
        assert "this is fine" in log_output

    def test_redact_pii_convenience_function(self):
        """redact_pii convenience function works."""
        text = "API key: sk-ant-abcdefghijklmnopqrstuvwxyz"
        result = redact_pii(text, mode=RedactionMode.FULL_REDACT, types=[PIIType.API_KEY])

        assert "sk-ant-" not in result
        assert "[REDACTED: api_key]" in result


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.fixture
    def scrubber(self):
        return PIIScrubber()

    def test_empty_string(self, scrubber):
        """Empty string returns empty result."""
        result = scrubber.detect("")
        assert not result.has_pii
        assert result.matches == []

        redacted = scrubber.redact("", mode=RedactionMode.FULL_REDACT)
        assert redacted == ""

    def test_none_input_to_sanitize_dict(self, scrubber):
        """None input to sanitize_dict returns None."""
        result = scrubber.sanitize_dict(None)
        assert result is None

    def test_non_dict_input_to_sanitize_dict(self, scrubber):
        """Non-dict input to sanitize_dict returns as-is."""
        assert scrubber.sanitize_dict("not a dict") == "not a dict"
        assert scrubber.sanitize_dict([1, 2, 3]) == [1, 2, 3]
        assert scrubber.sanitize_dict(42) == 42

    def test_overlapping_matches_deduplicated(self, scrubber):
        """Overlapping matches are deduplicated keeping highest confidence."""
        # SSN pattern could match part of a longer number
        text = "123-45-6789"  # Exact SSN
        result = scrubber.detect(text, types=[PIIType.SSN])

        # Should only have one match
        ssn_matches = [m for m in result.matches if m.pii_type == PIIType.SSN]
        assert len(ssn_matches) == 1

    def test_unicode_handling(self, scrubber):
        """Unicode text is handled correctly."""
        text = "Email: josé@example.com"
        result = scrubber.redact(text, mode=RedactionMode.FULL_REDACT, types=[PIIType.EMAIL])

        assert "[REDACTED: email]" in result

    def test_custom_replacements(self, scrubber):
        """custom_replacements overrides default redaction."""
        text = "Email: john@example.com"
        result = scrubber.redact(
            text,
            mode=RedactionMode.FULL_REDACT,
            types=[PIIType.EMAIL],
            custom_replacements={PIIType.EMAIL: "[EMAIL_HIDDEN]"}
        )

        assert result == "Email: [EMAIL_HIDDEN]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])