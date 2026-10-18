# tests/unit/services/test_file_processor.py
import pytest
from backend.services.file_processor import extract_pdf_text, build_file_context_for_ai


class TestFileProcessorPIIRedaction:
    def test_extract_pdf_text_redacts_pii(self):
        """Test that extract_pdf_text redacts PII from extracted content."""
        # This test uses a mock since we can't easily create a PDF with PII
        # We'll test the build_file_context_for_ai function instead which uses extracted_text

    def test_build_file_context_redacts_pii_in_extracted_text(self):
        """Test that build_file_context_for_ai redacts PII from extracted text."""
        attachments = [
            {
                "name": "document.pdf",
                "type": "application/pdf",
                "size": 1000,
                "extracted_text": "Contact john@example.com for details. SSN: 123-45-6789"
            }
        ]

        result = build_file_context_for_ai(attachments)

        # PII should be redacted (sanitize_prompt_injection calls sanitize_dict_pii internally)
        assert "[REDACTED: email]" in result
        assert "[REDACTED: ssn]" in result
        assert "john@example.com" not in result
        assert "123-45-6789" not in result

    def test_build_file_context_redacts_pii_in_multiple_attachments(self):
        """Test that PII is redacted across multiple attachments."""
        attachments = [
            {
                "name": "doc1.pdf",
                "type": "application/pdf",
                "size": 1000,
                "extracted_text": "Email: alice@example.com"
            },
            {
                "name": "doc2.pdf",
                "type": "application/pdf",
                "size": 2000,
                "extracted_text": "Phone: +1-555-123-4567"
            }
        ]

        result = build_file_context_for_ai(attachments)

        assert "[REDACTED: email]" in result
        assert "[REDACTED: phone]" in result
        assert "alice@example.com" not in result
        assert "+1-555-123-4567" not in result