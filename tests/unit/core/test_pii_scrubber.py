# tests/unit/core/test_pii_scrubber.py
import pytest
from backend.core.pii_scrubber import (
    PIIScrubber, PIIType, RedactionMode, detect_pii, redact_pii, sanitize_dict_pii,
    EMAIL_PATTERNS, PHONE_PATTERNS, SSN_PATTERNS, API_KEY_PATTERNS,
    PASSWORD_PATTERNS, CREDIT_CARD_PATTERNS
)

class TestEmailDetector:
    def test_valid_emails_detected(self):
        scrubber = PIIScrubber()
        text = "Contact me at john.doe@example.com or jane_smith@company.org"
        result = scrubber.detect(text, types=[PIIType.EMAIL])
        assert result.has_pii
        assert len(result.matches) == 2
        assert result.matches[0].pii_type == PIIType.EMAIL
        assert result.matches[0].matched_text == "john.doe@example.com"
        assert result.matches[1].matched_text == "jane_smith@company.org"

    def test_invalid_emails_not_detected(self):
        scrubber = PIIScrubber()
        text = "not-an-email or @no-domain.com or spaces in email.com"
        result = scrubber.detect(text, types=[PIIType.EMAIL])
        assert not result.has_pii or len(result.matches) == 0

class TestPhoneDetector:
    def test_us_phone_formats(self):
        scrubber = PIIScrubber()
        texts = [
            "Call 555-123-4567",
            "Call (555) 123-4567",
            "Call 555.123.4567",
            "Call +1 555 123 4567",
            "Call 5551234567",
        ]
        for text in texts:
            result = scrubber.detect(text, types=[PIIType.PHONE])
            assert result.has_pii, f"Failed for: {text}"

class TestSSNDetector:
    def test_ssn_formats(self):
        scrubber = PIIScrubber()
        texts = ["SSN: 123-45-6789", "SSN: 123 45 6789", "SSN: 123456789"]
        for text in texts:
            result = scrubber.detect(text, types=[PIIType.SSN])
            assert result.has_pii, f"Failed for: {text}"

class TestAPIKeyDetector:
    def test_common_prefixes(self):
        scrubber = PIIScrubber()
        keys = [
            "sk-abcdefghijklmnopqrst",
            "pk_live_abcdefghijklmnopqrstuvwx",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "xai-abcdefghijklmnopqrstuvwxyz",
            "sk-ant-abcdefghijklmnopqrstuvwxyz",
            "AIzaSyAbcdefghijklmnopqrstuvwxyz123456",
            "AKIAIOSFODNN7EXAMPLE",
            "Bearer sk-abcdefghijklmnopqrst",
        ]
        for key in keys:
            text = f"API key: {key}"
            result = scrubber.detect(text, types=[PIIType.API_KEY])
            assert result.has_pii, f"Failed for: {key}"

class TestPasswordDetector:
    def test_password_patterns(self):
        scrubber = PIIScrubber()
        texts = [
            'password="secret123"',
            'password=secret123',
            'api_key=sk-1234567890abcdef',
            'Authorization: Bearer token123',
            'secret: mysecret',
        ]
        for text in texts:
            result = scrubber.detect(text, types=[PIIType.PASSWORD])
            assert result.has_pii, f"Failed for: {text}"

class TestCreditCardDetector:
    def test_visa_mastercard_amex(self):
        scrubber = PIIScrubber()
        # Valid Luhn numbers (test numbers that pass Luhn check)
        texts = [
            "Card: 4111 1111 1111 1111",  # Visa test (passes Luhn)
            "Card: 5105 1051 0510 5100",  # Mastercard test (passes Luhn)
            "Card: 378282246310005",      # Amex test (passes Luhn)
        ]
        for text in texts:
            result = scrubber.detect(text, types=[PIIType.CREDIT_CARD])
            assert result.has_pii, f"Failed for: {text}"

class TestRedactionModes:
    def test_full_redact_mode(self):
        scrubber = PIIScrubber()
        text = "Email: john@example.com"
        result = scrubber.redact(text, mode=RedactionMode.FULL_REDACT)
        assert result == "Email: [REDACTED: email]"

    def test_mask_mode(self):
        scrubber = PIIScrubber()
        text = "Email: john@example.com"
        result = scrubber.redact(text, mode=RedactionMode.MASK)
        assert result == "Email: j***@example.com"

    def test_hash_mode(self):
        scrubber = PIIScrubber()
        text = "Email: john@example.com"
        result = scrubber.redact(text, mode=RedactionMode.HASH)
        assert result.startswith("Email: [HASH: ")
        assert result.endswith("]")

    def test_tokenize_mode(self):
        scrubber = PIIScrubber()
        text = "Email: john@example.com and jane@example.com"
        result = scrubber.redact(text, mode=RedactionMode.TOKENIZE)
        assert "[EMAIL_1]" in result
        assert "[EMAIL_2]" in result

    def test_remove_mode(self):
        scrubber = PIIScrubber()
        text = "Email: john@example.com"
        result = scrubber.redact(text, mode=RedactionMode.REMOVE)
        assert result == "Email: "

class TestSanitizeDict:
    def test_nested_dict(self):
        scrubber = PIIScrubber()
        data = {
            "user": {"email": "john@example.com"},
            "items": [{"secret": "sk-1234567890abcdef1234"}],  # 22 chars after sk-
            "meta": "no pii here"
        }
        result = scrubber.sanitize_dict(data, mode=RedactionMode.FULL_REDACT)
        assert result["user"]["email"] == "[REDACTED: email]"
        assert result["items"][0]["secret"] == "[REDACTED: api_key]"
        assert result["meta"] == "no pii here"

    def test_key_filter(self):
        scrubber = PIIScrubber()
        data = {"email": "john@example.com", "name": "John Doe"}
        result = scrubber.sanitize_dict(data, keys=["email"], mode=RedactionMode.FULL_REDACT)
        assert result["email"] == "[REDACTED: email]"
        assert result["name"] == "John Doe"  # Not redacted (not in keys)

class TestConvenienceFunctions:
    def test_detect_pii_function(self):
        result = detect_pii("Email: john@example.com")
        assert result.has_pii
        assert result.matches[0].pii_type == PIIType.EMAIL

    def test_redact_pii_function(self):
        result = redact_pii("Email: john@example.com", mode=RedactionMode.MASK)
        assert result == "Email: j***@example.com"

    def test_sanitize_dict_pii_function(self):
        result = sanitize_dict_pii({"email": "john@example.com"}, mode=RedactionMode.FULL_REDACT)
        assert result["email"] == "[REDACTED: email]"