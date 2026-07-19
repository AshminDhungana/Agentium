import pytest
from services.model_provider import _resolve_thinking_kwargs, PROVIDER_THINKING


class _Cfg:
    def __init__(self, provider, model, effort="none"):
        self.provider = provider
        self.default_model = model
        self.effort = effort


def test_none_is_noop():
    assert _resolve_thinking_kwargs(_Cfg("OPENAI", "gpt-4o", "none")) == {}


def test_unsupported_provider_hidden():
    # Cohere is not in the registry
    assert "COHERE" not in PROVIDER_THINKING
    assert _resolve_thinking_kwargs(_Cfg("COHERE", "command-r", "high")) == {}


def test_openai_effort():
    kw = _resolve_thinking_kwargs(_Cfg("OPENAI", "o4-mini", "high"))
    assert kw == {"extra_body": {"reasoning_effort": "high"}}


def test_openai_model_hint_misses():
    # gpt-4o is not a reasoning model
    assert _resolve_thinking_kwargs(_Cfg("OPENAI", "gpt-4o", "high")) == {}


def test_anthropic_budget_and_temp():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-5", "xhigh"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 32000}
    assert kw["temperature"] == 1


def test_deepseek_both_params():
    kw = _resolve_thinking_kwargs(_Cfg("DEEPSEEK", "deepseek-reasoner", "medium"))
    assert kw["extra_body"]["thinking"] == {"type": "enabled"}
    assert kw["extra_body"]["reasoning_effort"] == "medium"


def test_gemini_thinking_config():
    kw = _resolve_thinking_kwargs(_Cfg("GEMINI", "gemini-2.5-pro", "low"))
    assert kw["extra_body"]["thinkingConfig"]["thinkingBudget"] == 1024
    assert kw["extra_body"]["thinkingConfig"]["includeThoughts"] is True


def test_local_hint_misses():
    assert _resolve_thinking_kwargs(_Cfg("LOCAL", "llama3.1", "high")) == {}
