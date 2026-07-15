"""Tests for the Jarvis-upgrade voice_persona / speaker_id chat fields."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.api.routes import chat as chat_route
from backend.api.routes.chat import ChatMessage


def test_enrich_with_persona_prepends():
    out = chat_route._enrich_with_persona("set a reminder", "You are Jarvis.")
    assert "Jarvis" in out
    assert out.startswith("[Persona: You are Jarvis.]")


def test_enrich_with_persona_noop_when_empty():
    assert chat_route._enrich_with_persona("hi", None) == "hi"
    assert chat_route._enrich_with_persona("hi", "") == "hi"


def test_build_enriched_message_includes_persona():
    out = chat_route._build_enriched_message("turn off the lights", None, "You are Jarvis.")
    assert out.startswith("[Persona: You are Jarvis.]")
    assert "turn off the lights" in out


def test_chat_message_accepts_voice_fields():
    msg = ChatMessage(message="hello", stream=False, voice_persona="Jarvis", speaker_id="s1")
    assert msg.voice_persona == "Jarvis"
    assert msg.speaker_id == "s1"
