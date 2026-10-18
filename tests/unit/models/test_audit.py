# tests/unit/models/test_audit.py
import pytest
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory


class TestAuditLogPIIRedaction:
    def test_audit_log_redacts_pii_in_metadata(self):
        """Test that AuditLog.log() redacts PII from meta_data before persistence."""
        meta_data = {
            "user_email": "john@example.com",
            "api_key": "sk-1234567890abcdef1234",
            "normal_field": "value"
        }

        entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.DATA_ACCESS,
            actor_type="agent",
            actor_id="A12345678",
            action="data_access",
            meta_data=meta_data
        )

        # meta_data should be JSON string with PII redacted (FULL_REDACT mode for audit logs)
        import json
        stored_meta = json.loads(entry.metadata_json)
        assert stored_meta["user_email"] == "[REDACTED: email]"
        assert stored_meta["api_key"] == "[REDACTED: api_key]"
        assert stored_meta["normal_field"] == "value"

    def test_audit_log_redacts_pii_in_before_state(self):
        """Test that AuditLog.log() redacts PII from before_state."""
        before_state = {
            "email": "jane@example.com",
            "ssn": "123-45-6789",
            "name": "Jane Doe"
        }

        entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.DATA_ACCESS,
            actor_type="agent",
            actor_id="A12345678",
            action="data_update",
            before_state=before_state
        )

        import json
        stored_before = json.loads(entry.before_state)
        assert stored_before["email"] == "[REDACTED: email]"
        assert stored_before["ssn"] == "[REDACTED: ssn]"
        # Name detection is disabled by default (high false positive rate)
        # When enabled via custom_patterns, it would be "[REDACTED: name]"
        assert stored_before["name"] == "Jane Doe"

    def test_audit_log_redacts_pii_in_after_state(self):
        """Test that AuditLog.log() redacts PII from after_state."""
        after_state = {
            "phone": "+1-555-123-4567",
            "credit_card": "4111 1111 1111 1111",
            "status": "updated"
        }

        entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.DATA_ACCESS,
            actor_type="agent",
            actor_id="A12345678",
            action="data_update",
            after_state=after_state
        )

        import json
        stored_after = json.loads(entry.after_state)
        assert stored_after["phone"] == "[REDACTED: phone]"
        assert stored_after["credit_card"] == "[REDACTED: credit_card]"
        assert stored_after["status"] == "updated"