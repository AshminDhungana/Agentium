import pytest
from backend.core.persona import build_persona_directive, FALLBACK_PERSONA


def _sample_constitution():
    return {
        "version": "v2.0.0",
        "version_number": 2,
        "agentium_id": "C00002",
        "preamble": "We the Agents establish this Constitution.",
        "articles": {
            "agent_persona_and_conduct": {
                "title": "Agent Persona & Conduct",
                "content": "MARKER_PERSONA_CLAUSE speak calmly and helpfully.",
            },
            "article_1": {"title": "Prime Directive", "content": "Safety first."},
        },
        "prohibited_actions": ["Never impersonate a higher tier"],
        "sovereign_preferences": {
            "communication_style": "Be concise.",
        },
    }


def test_build_persona_includes_preamble_and_persona_article():
    text = build_persona_directive(_sample_constitution())
    assert "We the Agents establish this Constitution." in text
    assert "MARKER_PERSONA_CLAUSE" in text


def test_build_persona_voice_channel_adds_spoken_adaptation():
    text = build_persona_directive(_sample_constitution(), channel="voice")
    assert "text-to-speech" in text
    assert "Be concise." in text


def test_build_persona_tier_emphasis_and_citations():
    text = build_persona_directive(_sample_constitution(), tier=3)
    assert "Task Agent" in text
    assert "In-Effect Constitutional Clauses" in text
    assert "agent_persona_and_conduct" in text


def test_build_persona_provenance_footer():
    text = build_persona_directive(_sample_constitution())
    assert "<!-- persona built from Constitution v2.0.0 (C00002) -->" in text


def test_build_persona_none_returns_fallback():
    assert build_persona_directive(None) == FALLBACK_PERSONA
