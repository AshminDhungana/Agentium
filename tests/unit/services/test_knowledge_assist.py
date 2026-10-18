# tests/unit/services/test_knowledge_assist.py
import pytest
from backend.services.knowledge_assist import _synthesize_web_doc, _format_context


class TestKnowledgeAssistPIIRedaction:
    def test_synthesize_web_doc_redacts_pii(self):
        """Test that _synthesize_web_doc redacts PII from web search results."""
        results = [
            {
                "title": "Contact Us",
                "url": "https://example.com/contact",
                "snippet": "Email us at john@example.com or call +1-555-123-4567"
            },
            {
                "title": "Privacy Policy",
                "url": "https://example.com/privacy",
                "snippet": "We collect SSN 123-45-6789 for verification"
            }
        ]

        result = _synthesize_web_doc("test query", results)

        # PII should be redacted (sanitize_prompt_injection + PII redaction)
        assert "[REDACTED: email]" in result
        assert "[REDACTED: phone]" in result
        assert "[REDACTED: ssn]" in result
        assert "john@example.com" not in result
        assert "+1-555-123-4567" not in result
        assert "123-45-6789" not in result

    def test_format_context_redacts_pii(self):
        """Test that _format_context redacts PII from ChromaDB documents."""
        chroma = {
            "ids": [["doc1", "doc2"]],
            "documents": [
                [
                    "Contact jane@example.com for info",
                    "SSN: 987-65-4321 is on file"
                ]
            ]
        }

        result = _format_context(chroma)

        assert "[REDACTED: email]" in result
        assert "[REDACTED: ssn]" in result
        assert "jane@example.com" not in result
        assert "987-65-4321" not in result