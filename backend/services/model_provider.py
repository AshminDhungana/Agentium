"""
Universal Model Provider Service for Agentium 

"""

import asyncio
import os
import re
import time
import json
import uuid
import httpx
from typing import Optional, Dict, Any, AsyncGenerator, List, Callable, Tuple, Awaitable
from abc import ABC, abstractmethod
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from backend.models.database import get_db_context
from backend.models.entities.user_config import UserModelConfig, ProviderType, ModelUsageLog, ConnectionStatus

try:
    from backend.core.config import settings
except ImportError:
    settings = None  # type: ignore

from backend.services.provider_rate_limiter import provider_rate_limiter
from backend.core.tool_runner import (
    run_tool_async,
    ToolCallToken,
    register_tool_run,
    deregister_tool_run,
)


async def _record_provider_headers(config) -> None:
    """Read + clear the headers captured by the SDK httpx hook (Task 17).

    No-op until Task 17 attaches the event hook; afterwards it feeds provider
    rate-limit headers into the limiter so it can tighten effective rate.
    """
    headers = provider_rate_limiter.pop_raw_headers(config.id)
    if headers:
        provider = getattr(config.provider, "value", config.provider)
        await provider_rate_limiter.record_header_insight(config.id, provider, headers)


# ─────────────────────────────────────────────────────────────────────────────
# Task 17 — Reuse a single SDK client per provider config.
#
# Previously every generate()/stream_generate()/generate_with_tools() call
# built a brand-new openai.AsyncOpenAI / anthropic.AsyncAnthropic instance.
# Building a client per request is wasteful (connection pools, retry transport
# and auth setup are recreated each time) and prevents any shared transport
# state. We now construct ONE client per (config_id, api_key) and reuse it for
# the lifetime of the process. The client is also the attachment point for the
# httpx event hook that feeds raw rate-limit headers into the limiter (Task 10).
# ─────────────────────────────────────────────────────────────────────────────

# Cache of SDK clients keyed by (config_id, api_key, base_url, is_anthropic).
# api_key is part of the key so a rotated key transparently yields a fresh
# client on the next request for that same config.
_CLIENT_CACHE: Dict[Tuple, Any] = {}


def _header_capture_hook(config_id: str):
    """Return an httpx response hook that records raw rate-limit headers.

    Appended to each shared SDK client's internal httpx client so that, on
    every provider response, the raw headers are captured for Task 10's
    header-correction logic. The parsed SDK response object carries no headers,
    so the hook is the only reliable capture point.
    """
    async def _hook(response: "httpx.Response") -> None:
        try:
            provider_rate_limiter.record_raw_headers(config_id, dict(response.headers))
        except Exception:
            pass
    return _hook


def _attach_header_hook(client: Any, config_id: str) -> None:
    """Append the rate-limit header capture hook to an SDK client.

    Appends (never replaces) to the SDK's own internal httpx client so the
    built-in retry/event machinery is preserved. The SDK stores its httpx
    client at ``client._client`` (an ``AsyncHttpxClientWrapper``).
    """
    try:
        internal = getattr(client, "_client", None)
        if internal is not None and hasattr(internal, "_event_hooks"):
            internal._event_hooks.setdefault("response", []).append(
                _header_capture_hook(config_id)
            )
    except Exception:
        pass


def _get_cached_sdk_client(
    config,
    *,
    api_key: Optional[str],
    base_url: Optional[str],
    timeout: Optional[float],
    is_anthropic: bool,
) -> Any:
    """Return a reused SDK client for one provider config.

    Builds the client once per (config_id, api_key, base_url) and caches it.
    Subsequent calls for the same config reuse the same instance, satisfying
    Task 17 ("client construction happens once per config, not once per
    request").
    """
    cache_key = (str(config.id), api_key, base_url, is_anthropic)
    cached = _CLIENT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if is_anthropic:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
    else:
        import openai
        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
    # Attach the hook before caching so it is registered exactly once.
    _attach_header_hook(client, config.id)
    _CLIENT_CACHE[cache_key] = client
    return client

# ─────────────────────────────────────────────────────────────────────────────
# Per-model pricing table
# Prices are USD per 1 M tokens (input_rate, output_rate).
# Source: official provider pricing pages as of June 2026.
#   Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
#   OpenAI:    https://openai.com/api/pricing/
#   Google:    https://ai.google.dev/gemini-api/docs/pricing
# NOTE: Anthropic model_used values come back from the API as the canonical
# IDs above (e.g. "claude-sonnet-4-6"). The prefix-match fallback in
# calculate_cost() also covers dated/snapshot variants if Anthropic adds them.
# ─────────────────────────────────────────────────────────────────────────────

# fmt: off
MODEL_PRICES: Dict[str, Tuple[float, float]] = {
    # ── OpenAI ───────────────────────────────────────────────────────────────
    # Current generation (Jun 2026) — see https://openai.com/api/pricing/
    "gpt-5.5":                         (5.00,   30.00),
    "gpt-5.5-pro":                     (30.00, 180.00),
    "gpt-5.4":                         (2.50,   15.00),
    "gpt-5.4-mini":                    (0.75,    4.00),
    "gpt-5.4-nano":                    (0.20,    1.25),
    "gpt-5.3-codex":                   (1.75,   14.00),
    "gpt-4.1":                         (2.00,    8.00),
    "gpt-4.1-mini":                    (0.40,    1.60),
    "gpt-4.1-nano":                    (0.10,    0.40),
    "o4-mini":                         (1.10,    4.40),

    # Legacy (kept so historical usage logs still price correctly)
    "gpt-4o":                          (2.50,   10.00),
    "gpt-4o-2024-11-20":               (2.50,   10.00),
    "gpt-4o-2024-08-06":               (2.50,   10.00),
    "gpt-4o-mini":                     (0.15,    0.60),
    "gpt-4o-mini-2024-07-18":          (0.15,    0.60),
    "gpt-4-turbo":                     (10.00,  30.00),
    "gpt-4-turbo-preview":             (10.00,  30.00),
    "gpt-4-turbo-2024-04-09":          (10.00,  30.00),
    "gpt-4":                           (30.00,  60.00),
    "gpt-4-32k":                       (60.00, 120.00),
    "gpt-3.5-turbo":                   (0.50,    1.50),
    "gpt-3.5-turbo-instruct":          (1.50,    2.00),
    "o1":                              (15.00,  60.00),
    "o1-preview":                      (15.00,  60.00),
    "o1-mini":                         (3.00,   12.00),
    "o3-mini":                         (1.10,    4.40),

    # ── Anthropic ────────────────────────────────────────────────────────────
    # Current generation (Jun 2026) — see https://platform.claude.com/docs/en/about-claude/pricing
    "claude-fable-5":                  (10.00,  50.00),
    "claude-mythos-5":                 (10.00,  50.00),   # limited availability (Project Glasswing)
    "claude-mythos-preview":           (10.00,  50.00),   # limited availability (Project Glasswing)
    "claude-opus-4-8":                 (5.00,   25.00),
    "claude-opus-4-7":                 (5.00,   25.00),
    "claude-opus-4-6":                 (5.00,   25.00),
    "claude-opus-4-5":                 (5.00,   25.00),
    "claude-sonnet-4-6":               (3.00,   15.00),
    "claude-sonnet-4-5":               (3.00,   15.00),
    "claude-haiku-4-5":                (1.00,    5.00),

    # Deprecated / retired (kept so historical usage logs still price correctly)
    "claude-opus-4-1":                 (15.00,  75.00),
    "claude-opus-4":                   (15.00,  75.00),
    "claude-sonnet-4":                 (3.00,   15.00),
    "claude-haiku-3-5":                (0.80,    4.00),
    "claude-3-5-sonnet-20241022":      (3.00,   15.00),
    "claude-3-5-sonnet-20240620":      (3.00,   15.00),
    "claude-3-5-haiku-20241022":       (0.80,    4.00),
    "claude-3-opus-20240229":          (15.00,  75.00),
    "claude-3-sonnet-20240229":        (3.00,   15.00),
    "claude-3-haiku-20240307":         (0.25,    1.25),
    "claude-2.1":                      (8.00,   24.00),
    "claude-2.0":                      (8.00,   24.00),

    # ── Google Gemini ─────────────────────────────────────────────────────────
    # Current generation (Jun 2026), standard ≤200K-token rate — see https://ai.google.dev/gemini-api/docs/pricing
    "gemini-3.1-pro":                  (2.00,   12.00),
    "gemini-3.1-pro-preview":          (2.00,   12.00),
    "gemini-3.5-flash":                (1.50,    9.00),
    "gemini-3-flash-preview":          (0.50,    3.00),
    "gemini-3.1-flash-lite":           (0.25,    1.50),
    "gemini-2.5-pro":                  (1.25,   10.00),
    "gemini-2.5-flash":                (0.30,    2.50),
    "gemini-2.5-flash-lite":           (0.10,    0.40),

    # Legacy (kept so historical usage logs still price correctly)
    "gemini-1.5-pro":                  (1.25,    5.00),
    "gemini-1.5-pro-002":              (1.25,    5.00),
    "gemini-1.5-flash":                (0.075,   0.30),
    "gemini-1.5-flash-002":            (0.075,   0.30),
    "gemini-1.0-pro":                  (0.50,    1.50),
    "gemini-2.0-flash":                (0.10,    0.40),

    # ── Groq ─────────────────────────────────────────────────────────────────
    "llama-3.3-70b-versatile":         (0.59,    0.79),
    "llama-3.1-8b-instant":            (0.05,    0.08),
    "llama-3.1-70b-versatile":         (0.59,    0.79),
    "mixtral-8x7b-32768":              (0.24,    0.24),
    "gemma2-9b-it":                    (0.20,    0.20),

    # ── Mistral ───────────────────────────────────────────────────────────────
    "mistral-large-latest":            (2.00,    6.00),
    "mistral-medium-latest":           (2.75,    8.10),
    "mistral-small-latest":            (0.20,    0.60),
    "open-mistral-7b":                 (0.25,    0.25),
    "open-mixtral-8x7b":               (0.70,    0.70),
    "open-mixtral-8x22b":              (2.00,    6.00),
    "codestral-latest":                (0.20,    0.60),

    # ── Together AI ───────────────────────────────────────────────────────────
    "meta-llama/meta-llama-3.1-70b-instruct-turbo":  (0.88,  0.88),
    "meta-llama/meta-llama-3.1-8b-instruct-turbo":   (0.18,  0.18),
    "meta-llama/meta-llama-3.1-405b-instruct-turbo": (3.50,  3.50),
    "mistralai/mixtral-8x7b-instruct-v0.1":          (0.60,  0.60),
    "qwen/qwen2.5-72b-instruct-turbo":               (1.20,  1.20),

    # ── DeepSeek ──────────────────────────────────────────────────────────────
    "deepseek-chat":                   (0.27,    1.10),
    "deepseek-reasoner":               (0.55,    2.19),
    "deepseek-coder":                  (0.27,    1.10),

    # ── Moonshot (Kimi) ───────────────────────────────────────────────────────
    "moonshot-v1-8k":                  (1.63,    1.63),
    "moonshot-v1-32k":                 (3.26,    3.26),
    "moonshot-v1-128k":                (8.14,    8.14),

    # ── Cohere ────────────────────────────────────────────────────────────────
    "command-r-plus":                  (2.50,   10.00),
    "command-r":                       (0.15,    0.60),
    "command":                         (1.00,    2.00),

    # ── Local / free — all cost $0 ───────────────────────────────────────────
}
# fmt: on

# Fallback blended rates ($/1M tokens) for unknown models, keyed by provider.
_PROVIDER_FALLBACK_RATES: Dict[ProviderType, float] = {
    ProviderType.OPENAI:             5.00,
    ProviderType.ANTHROPIC:          9.00,
    ProviderType.GROQ:               0.30,
    ProviderType.MISTRAL:            1.50,
    ProviderType.TOGETHER:           1.00,
    ProviderType.LOCAL:              0.00,
    ProviderType.CUSTOM:             1.00,
}


def calculate_cost(
    model_name: str,
    provider: ProviderType,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Calculate the USD cost for an API call using per-model prices.

    Looks up the model in MODEL_PRICES (input/output split).
    Falls back to a blended per-provider rate when the model is unknown.
    Always returns 0.0 for LOCAL provider.

    Args:
        model_name:        Exact model identifier returned by the API.
        provider:          ProviderType enum value.
        prompt_tokens:     Number of input/prompt tokens consumed.
        completion_tokens: Number of output/completion tokens generated.

    Returns:
        Estimated cost in USD (float, rounded to 8 decimal places).
    """
    if provider == ProviderType.LOCAL:
        return 0.0

    # Normalise: some APIs return versioned suffixes or capitalisation variants
    normalised = model_name.lower().strip()

    # Try dynamic pricing registry first
    from backend.services.pricing_sync_service import PricingSyncService
    prices = PricingSyncService.get_price(normalised)

    if prices is None:
        # 1. Exact match in hardcoded MODEL_PRICES
        prices = MODEL_PRICES.get(normalised)

    # 2. Prefix match — handles dated/snapshot suffixes, e.g.
    #    "claude-opus-4-8-20260615" → "claude-opus-4-8", "gpt-4o-2024-xx-xx" → "gpt-4o".
    #    Picks the LONGEST matching key (most specific) rather than the first
    #    one found, since dict order can't be relied on to put more specific
    #    prefixes (e.g. "claude-opus-4-8") ahead of shorter ones that are also
    #    real model IDs (e.g. "claude-opus-4").
    if prices is None:
        best_key = ""
        for key, val in MODEL_PRICES.items():
            key_lower = key.lower()
            if normalised.startswith(key_lower) and len(key_lower) > len(best_key):
                best_key = key_lower
                prices = val

    if prices is not None:
        input_rate, output_rate = prices
        cost = (
            (prompt_tokens     / 1_000_000) * input_rate
            + (completion_tokens / 1_000_000) * output_rate
        )
    else:
        blended = _PROVIDER_FALLBACK_RATES.get(provider, 1.00)
        cost = ((prompt_tokens + completion_tokens) / 1_000_000) * blended

    return round(cost, 8)


# ─────────────────────────────────────────────────────────────────────────────

class BaseModelProvider(ABC):
    """Abstract base for all model providers."""

    def __init__(self, config: UserModelConfig):
        """Init."""

        self.config = config
        self.api_key = self._get_api_key() if config.requires_api_key() else None
        self.base_url = config.get_effective_base_url()

        # Safety net: get_effective_base_url() now returns a real default for
        # every provider EXCEPT AI21 / AZURE_OPENAI / CUSTOM / OPENAI_COMPATIBLE,
        # which require the user to supply api_base_url explicitly. Without this
        # check, base_url=None gets passed straight to openai.AsyncOpenAI(),
        # which silently defaults to https://api.openai.com/v1 — i.e. the exact
        # "everything calls OpenAI" bug this is guarding against.
        if self.base_url is None and config.provider != ProviderType.ANTHROPIC:
            raise ValueError(
                f"No base URL configured for provider '{config.provider.value}' "
                f"(config_id={getattr(config, 'id', '?')}). This provider requires "
                f"an explicit api_base_url (or azure_endpoint for Azure) to be set "
                f"on the model config — refusing to fall back to a default endpoint."
            )

    def _get_api_key(self) -> Optional[str]:
        """Decrypt API key."""
        if not self.config.api_key_encrypted:
            return None
        from backend.core.security import decrypt_api_key
        try:
            return decrypt_api_key(self.config.api_key_encrypted)
        except:
            return None

    def _thinking_kwargs(self) -> Dict[str, Any]:
        """Return provider-specific extended-thinking kwargs (or {})."""
        return _resolve_thinking_kwargs(self.config)

    @abstractmethod
    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        """Generate."""

        pass

    @abstractmethod
    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generate."""

        pass

    async def _log_usage(
        self,
        *,
        model_used: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool,
        error: Optional[str] = None,
        agentium_id: str = "system",
        request_type: str = "chat",
    ) -> None:
        """
        Persist a ModelUsageLog row and update the config's rolling counters.

        Uses module-level calculate_cost() for accurate per-model pricing
        based on the prompt/completion token split.
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = calculate_cost(
            model_name=model_used,
            provider=self.config.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        try:
            with get_db_context() as db:
                self.config.increment_usage(total_tokens, cost_usd=cost)
                db.add(ModelUsageLog(
                    config_id=self.config.id,
                    provider=self.config.provider,
                    model_used=model_used,
                    request_type=request_type,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error,
                    cost_usd=cost,
                    request_metadata={"agentium_id": agentium_id},
                    agentium_id=agentium_id,
                ))
                db.commit()
        except Exception as exc:
            # Logging must never crash the main request path
            logger.error(f"⚠️  _log_usage failed: {exc}")


def _normalize_tool_choice(tool_choice: Any) -> Any:
    """
    Collapse the dict form of ``tool_choice`` to its string equivalent.

    OpenAI accepts both ``"auto"`` and ``{"type": "auto"}``, but some
    OpenAI-compatible upstreams (e.g. Novita, which OpenRouter routes certain
    models such as ``tencent/hy3:free`` to) reject the dict form and return
    ``invalid_request_error`` (HTTP 400). The two forms are semantically
    identical for ``auto`` / ``none`` / ``required``, so collapsing them costs
    nothing and makes tool-calling robust across providers.

    Forced function calls (``{"type": "function", "function": {...}}``) are left
    untouched — only the bare-mode dicts are normalized.
    """
    if (
        isinstance(tool_choice, dict)
        and tool_choice.get("type") in ("auto", "none", "required")
    ):
        return tool_choice["type"]
    return tool_choice


# ─────────────────────────────────────────────────────────────────────────────
# Extended-thinking wiring (Task 3).
#
# A single source of truth that maps a UserModelConfig.effort value to the
# provider-specific extended-thinking / reasoning parameter shape. Every create
# call in the provider classes spreads `**self._thinking_kwargs()`; this helper
# guarantees that ONLY valid combinations are ever produced:
#   * effort == "none"            -> {}
#   * unsupported provider        -> {}   (e.g. COHERE is intentionally absent)
#   * model fails the model_hint  -> {}   (e.g. gpt-4o is not a reasoning model)
# so nothing invalid is ever sent upstream.
# ─────────────────────────────────────────────────────────────────────────────

# Per-provider extended-thinking strategy. `kind` selects the param shape;
# `model_hint` (optional regex) gates both UI visibility and param emission.
#
# CROSS-REFERENCE: THINKING_PROVIDERS in
# frontend/src/components/models/ModelConfigForm.tsx is a hand-copied mirror of
# this map. The two MUST stay in sync (same provider keys + matching hints), or
# the UI may show the effort control for a model the backend refuses to gate.
# When editing a hint here, update the frontend copy identically (and vice-versa).
PROVIDER_THINKING = {
    "OPENAI":        {"kind": "openai",   "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)"},
    "AZURE_OPENAI": {"kind": "openai",   "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)"},
    "ANTHROPIC":     {"kind": "anthropic", "model_hint": r"claude-(fable|opus|sonnet|haiku)[- ]?(4|4[-.]5|4-8|5)"},
    "GEMINI":        {"kind": "gemini",    "model_hint": r"gemini-(2\.5|3|3\.5)"},
    "DEEPSEEK":      {"kind": "deepseek", "model_hint": r"reasoner|v4"},
    "GROQ":          {"kind": "openai",   "model_hint": r"gpt-oss|qwen|r1|qwq|reason"},
    "MISTRAL":       {"kind": "openai",   "model_hint": r"magistral|thinking"},
    "TOGETHER":      {"kind": "openai",   "model_hint": r"r1|qwq|reasoner|thinking|gpt-oss"},
    "MOONSHOT":      {"kind": "deepseek", "model_hint": r"k2|kimi"},
    "LOCAL":         {"kind": "openai",   "model_hint": r"qwq|r1|deepseek|thinking|z1|qwen3"},
    "CUSTOM":        {"kind": "openai",
                     "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)|qwq|r1|reasoner|thinking|gpt-oss"},
    # COHERE intentionally omitted -> no thinking
}

_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}
_ANTHROPIC_BUDGET = {"low": 2000, "medium": 8000, "high": 16000, "xhigh": 32000}
_GEMINI_BUDGET = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 24576}


def _resolve_thinking_kwargs(config) -> Dict[str, Any]:
    """Return provider-specific thinking kwargs, or {} when disabled/unsupported.

    This is the single source of truth: any provider/model combo that does
    not support extended thinking yields {}, so nothing is ever sent that the
    upstream would reject.
    """
    effort = (getattr(config, "effort", "none") or "none").lower()
    if effort == "none":
        return {}
    info = PROVIDER_THINKING.get(str(getattr(config, "provider", "")).upper())
    if not info:
        return {}
    model = (getattr(config, "default_model", "") or "").lower()
    hint = info.get("model_hint")
    if hint and not re.search(hint, model):
        return {}
    kind = info["kind"]
    if kind == "anthropic":
        return {
            "thinking": {"type": "enabled", "budget_tokens": _ANTHROPIC_BUDGET[effort]},
            "temperature": 1,
        }
    if kind == "gemini":
        return {"extra_body": {"thinkingConfig": {
            "thinkingBudget": _GEMINI_BUDGET[effort], "includeThoughts": True}}}
    if kind == "deepseek":
        return {"extra_body": {
            "thinking": {"type": "enabled"},
            "reasoning_effort": _OPENAI_EFFORT[effort],
        }}
    # openai-compatible family
    return {"extra_body": {"reasoning_effort": _OPENAI_EFFORT[effort]}}


def is_thinking_config(config) -> bool:
    """True when the config enables extended thinking for a supported model."""
    return _resolve_thinking_kwargs(config) != {}


class OpenAICompatibleProvider(BaseModelProvider):
    """
    Universal provider for ANY OpenAI-compatible API.
    Works with Groq, Mistral, Together, Fireworks, Local models, etc.
    GeminiProvider and LocalProvider inherit generate_with_tools() automatically.
    """

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        """Generate."""

        client = _get_cached_sdk_client(
            self.config,
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
            is_anthropic=False,
        )

        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)
        try:
            rpm = getattr(self.config, "requests_per_minute", 60) or 60
            await provider_rate_limiter.acquire(self.config.id, rpm)
            response = await client.chat.completions.create(
                model=kwargs.get('model', self.config.default_model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                top_p=kwargs.get('top_p', self.config.top_p),
                **self._thinking_kwargs(),
            )

            await _record_provider_headers(self.config)

            latency = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            actual_model      = response.model or kwargs.get('model', self.config.default_model)
            prompt_tokens     = response.usage.prompt_tokens     if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0

            await self._log_usage(
                model_used=actual_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency,
                success=True,
                agentium_id=kwargs.get('agentium_id') or 'system',
            )

            return {
                "content":           content,
                "tokens_used":       prompt_tokens + completion_tokens,
                "prompt_tokens":     prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms":        latency,
                "model":             actual_model,
                "finish_reason":     response.choices[0].finish_reason,
                "cost_usd":          calculate_cost(
                    actual_model, self.config.provider,
                    prompt_tokens, completion_tokens
                ),
            }

        except Exception as e:
            await self._log_usage(
                model_used=kwargs.get('model', self.config.default_model),
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                error=str(e),
                agentium_id=kwargs.get('agentium_id') or 'system',
            )
            raise
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs):
        """Stream generate."""

        client = _get_cached_sdk_client(
            self.config,
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
            is_anthropic=False,
        )

        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)
        try:
            rpm = getattr(self.config, "requests_per_minute", 60) or 60
            await provider_rate_limiter.acquire(self.config.id, rpm)
            stream = await client.chat.completions.create(
                model=kwargs.get('model', self.config.default_model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                stream=True,
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                **self._thinking_kwargs(),
            )

            await _record_provider_headers(self.config)

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

    async def _assemble_stream_turn(
        self,
        stream: Any,
        on_delta: Optional[Callable[[str], Awaitable[None]]],
        cancel_event: Optional[asyncio.Event],
    ) -> Tuple[Dict[str, Any], Any, Optional[str]]:
        """Consume an async OpenAI-style stream into one assistant message.

        Assembles streamed ``tool_calls`` deltas (keyed by index) into a single
        assistant message dict, accumulates prompt/completion usage from the
        trailing usage chunk, and forwards each text delta to ``on_delta`` when
        provided.  ``cancel_event`` is checked every iteration; if set, the
        stream is stopped early and ``finish_reason`` is reported as
        ``"stopped_by_user"``.
        """
        acc_content: List[str] = []
        acc_tool_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        usage = None

        async for chunk in stream:
            if cancel_event is not None and cancel_event.is_set():
                finish_reason = "stopped_by_user"
                break

            if getattr(chunk, "usage", None):
                usage = chunk.usage

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                acc_content.append(delta.content)
                if on_delta is not None:
                    await on_delta(delta.content)

            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in acc_tool_calls:
                        acc_tool_calls[idx] = {
                            "id": getattr(tc, "id", None),
                            "name": getattr(tc.function, "name", None) or "",
                            "arguments": "",
                        }
                    else:
                        if getattr(tc, "id", None):
                            acc_tool_calls[idx]["id"] = tc.id
                        if getattr(tc.function, "name", None):
                            acc_tool_calls[idx]["name"] = tc.function.name
                    if getattr(tc.function, "arguments", None):
                        acc_tool_calls[idx]["arguments"] += tc.function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        tool_calls: List[Dict[str, Any]] = []
        if acc_tool_calls:
            for _idx in sorted(acc_tool_calls.keys()):
                tc = acc_tool_calls[_idx]
                tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                })

        msg: Dict[str, Any] = {
            "role": "assistant",
            "content": "".join(acc_content) or None,
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls

        return msg, usage, finish_reason

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Agentic tool-calling loop for OpenAI-compatible providers.

        Drives a multi-turn conversation until the model stops calling tools
        or max_iterations is reached.  All tool calls in a single response are
        executed in parallel via asyncio.gather for minimal latency.

        Args:
            system_prompt:   System-level instruction for the model.
            messages:        Initial conversation turns (list of role/content dicts).
            tools:           Tool definitions in OpenAI function-calling format
                             (produced by tool_registry.to_openai_tools()).
            tool_executor:   Async callable(name: str, args: dict) -> str.
                             Must be the analytics-wrapped executor so every call
                             is recorded in ToolUsageLog.
            max_iterations:  Safety cap on agentic loop turns (default 10).
            **kwargs:        Forwarded to the API (model, max_tokens, temperature,
                             agentium_id, etc.).

        Returns:
            {
                "content":           final text response,
                "tokens_used":       cumulative token count across all turns,
                "prompt_tokens":     cumulative prompt tokens,
                "completion_tokens": cumulative completion tokens,
                "latency_ms":        wall-clock time for the whole loop,
                "model":             model string echoed by the API,
                "messages":          full conversation history including tool turns,
            }
        """
        actual_model = kwargs.get("model", self.config.default_model)
        client = getattr(self, "_client", None) or _get_cached_sdk_client(
            self.config,
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
            is_anthropic=False,
        )

        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)

        try:
            loop_finish_reason = "stop"

            for _ in range(max_iterations):
                create_kwargs: Dict[str, Any] = dict(
                    model=actual_model,
                    messages=[{"role": "system", "content": system_prompt}] + conversation,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                )
                if tools:
                    create_kwargs["tools"] = tools
                    # Honor an explicit tool_choice from the caller (e.g. the
                    # decision engine forces a specific tool); default to "auto".
                    # Normalize the dict form {"type": "auto"} to the string
                    # "auto" — some upstreams (Novita) reject the dict form.
                    create_kwargs["tool_choice"] = _normalize_tool_choice(
                        kwargs.get("tool_choice", "auto")
                    )

                # ── Prompt caching (Task 2.1) ────────────────────────────────────
                # A stable prefix (system + summary + first message) is identical
                # across turns, so route it to a shared cache via prompt_cache_key.
                # Only meaningful for OpenAI-family providers; others ignore it.
                _pc_key = kwargs.get("prompt_cache_key")
                if _pc_key and str(getattr(self.config, "provider", "")).lower() in (
                    "openai", "azure", "azure_openai",
                ):
                    create_kwargs["prompt_cache_key"] = _pc_key

                # ── Extended thinking (Task 3) ─────────────────────────────────
                # Merge provider-specific reasoning params (extra_body/temperature)
                # into the call kwargs. Works for both the blocking `create` path
                # below and the streaming path (which copies create_kwargs).
                create_kwargs.update(self._thinking_kwargs())

                rpm = getattr(self.config, "requests_per_minute", 60) or 60
                await provider_rate_limiter.acquire(self.config.id, rpm)

                if on_delta is None:
                    # ── Blocking path ──────────────────────────────────────────
                    response = await client.chat.completions.create(**create_kwargs)
                    await _record_provider_headers(self.config)

                    # Defensive: a test double may return an async stream even
                    # for a non-stream request. Consume it WITHOUT on_delta and
                    # run the identical decision logic below. Real providers
                    # return a non-stream object here, so this branch is a no-op
                    # in production (behavior stays byte-for-byte identical).
                    if hasattr(response, "__aiter__"):
                        msg, turn_usage, finish_reason = await self._assemble_stream_turn(
                            response, None, None
                        )
                        msg_tool_calls = msg.get("tool_calls")
                        msg_content = msg.get("content")
                        conversation.append(msg)
                    else:
                        msg = response.choices[0].message
                        turn_usage = response.usage
                        finish_reason = response.choices[0].finish_reason
                        msg_tool_calls = msg.tool_calls
                        msg_content = msg.content
                        # Append raw assistant turn to history so the next
                        # iteration has full context.  model_dump(exclude_none=True)
                        # avoids sending null fields that some providers reject.
                        try:
                            conversation.append(msg.model_dump(exclude_none=True))
                        except Exception:
                            conversation.append({
                                "role": "assistant",
                                "content": msg.content or "",
                                **({"tool_calls": [tc.model_dump() for tc in msg.tool_calls]} if msg.tool_calls else {}),
                            })

                    if turn_usage:
                        total_prompt_tokens     += getattr(turn_usage, "prompt_tokens", 0)     or 0
                        total_completion_tokens += getattr(turn_usage, "completion_tokens", 0) or 0

                    # Normalize tool_calls to dicts so the executor call is
                    # uniform for both Pydantic and assembled-stream messages.
                    norm_tool_calls: List[Dict[str, Any]] = []
                    if msg_tool_calls:
                        for tc in msg_tool_calls:
                            if isinstance(tc, dict):
                                norm_tool_calls.append(tc)
                            else:
                                norm_tool_calls.append({
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                })

                    # Model signalled it is done — no more tool calls
                    if finish_reason == "stop" or not norm_tool_calls:
                        content = msg_content or ""
                        break

                    if finish_reason == "tool_calls" and norm_tool_calls:
                        # Execute ALL tool calls in this response in parallel
                        results = await asyncio.gather(
                            *[
                                tool_executor(
                                    tc["function"]["name"],
                                    json.loads(tc["function"]["arguments"] or "{}"),
                                )
                                for tc in norm_tool_calls
                            ],
                            return_exceptions=True,
                        )

                        # Feed each result back as a separate tool message
                        for tc, result in zip(norm_tool_calls, results):
                            result_str = (
                                str(result) if not isinstance(result, Exception)
                                else f"ERROR: {result}"
                            )
                            conversation.append({
                                "role":         "tool",
                                "tool_call_id": tc["id"],
                                "content":      result_str,
                            })
                    else:
                        # Unexpected finish_reason — return whatever content exists
                        content = msg_content or ""
                        break
                else:
                    # ── Streaming final-turn path ────────────────────────────
                    # The tool-call loop structure is identical to the blocking
                    # path; only the FINAL text turn is streamed token-by-token
                    # and each chunk is forwarded to on_delta.  Tool-call turns
                    # are still read fully (deltas assembled) and executed the
                    # same way as the blocking branch.
                    stream_kwargs: Dict[str, Any] = dict(create_kwargs)
                    stream_kwargs["stream"] = True
                    stream_kwargs["stream_options"] = {"include_usage": True}

                    stream = await client.chat.completions.create(**stream_kwargs)
                    await _record_provider_headers(self.config)

                    msg, turn_usage, finish_reason = await self._assemble_stream_turn(
                        stream, on_delta, cancel_event
                    )

                    if turn_usage:
                        total_prompt_tokens     += getattr(turn_usage, "prompt_tokens", 0)     or 0
                        total_completion_tokens += getattr(turn_usage, "completion_tokens", 0) or 0

                    conversation.append(msg)

                    if cancel_event is not None and cancel_event.is_set():
                        content = msg.get("content") or ""
                        loop_finish_reason = "stopped_by_user"
                        break

                    msg_tool_calls = msg.get("tool_calls")
                    msg_content = msg.get("content")

                    # Model signalled it is done — no more tool calls
                    if finish_reason == "stop" or not msg_tool_calls:
                        content = msg_content or ""
                        break

                    if finish_reason == "tool_calls" and msg_tool_calls:
                        # Execute ALL tool calls in this response in parallel,
                        # mirroring the blocking branch exactly.
                        results = await asyncio.gather(
                            *[
                                tool_executor(
                                    tc["function"]["name"],
                                    json.loads(tc["function"]["arguments"] or "{}"),
                                )
                                for tc in msg_tool_calls
                            ],
                            return_exceptions=True,
                        )

                        # Feed each result back as a separate tool message
                        for tc, result in zip(msg_tool_calls, results):
                            result_str = (
                                str(result) if not isinstance(result, Exception)
                                else f"ERROR: {result}"
                            )
                            conversation.append({
                                "role":         "tool",
                                "tool_call_id": tc["id"],
                                "content":      result_str,
                            })
                    else:
                        # Unexpected finish_reason — return whatever content exists
                        content = msg_content or ""
                        break
            else:
                # max_iterations reached without a clean stop
                content = ""

        except Exception as exc:
            latency = int((time.time() - start_time) * 1000)
            await self._log_usage(
                model_used=actual_model,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                latency_ms=latency,
                success=False,
                error=str(exc),
                agentium_id=kwargs.get("agentium_id") or "system",
            )
            raise
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

        latency = int((time.time() - start_time) * 1000)
        total_tokens = total_prompt_tokens + total_completion_tokens
        await self._log_usage(
            model_used=actual_model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=latency,
            success=True,
            agentium_id=kwargs.get("agentium_id") or "system",
        )

        return {
            "content":           content,
            "tokens_used":       total_tokens,
            "prompt_tokens":     total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "latency_ms":        latency,
            "model":             actual_model,
            "messages":          conversation,
            "finish_reason":     loop_finish_reason,
            "cost_usd":          calculate_cost(
                actual_model, self.config.provider,
                total_prompt_tokens, total_completion_tokens
            ),
        }

class AnthropicProvider(BaseModelProvider):
    """Anthropic Claude API."""

    @staticmethod
    def _anthropic_base_url(config) -> Optional[str]:
        """
        SDK base URL for the Anthropic client.

        The anthropic SDK appends ``/v1`` to whatever base_url it is given, so we
        must NOT pass a URL that already ends in ``/v1``. Defaults to the real
        Anthropic API when no explicit override is configured, but honours
        ``config.api_base_url`` (e.g. a self-hosted / OpenAI-compatible Anthropic
        endpoint, or a local mock server) so users can point Anthropic at a
        custom base. The previously-hardcoded ``None`` ignored ``api_base_url``
        entirely, making custom endpoints impossible.
        """
        if getattr(config, "api_base_url", None):
            base = config.api_base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base.removesuffix("/v1")
            return base
        if getattr(config, "base_url", None):
            base = config.base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base.removesuffix("/v1")
            return base
        return None

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        """Generate."""

        client = _get_cached_sdk_client(
            self.config,
            api_key=self.api_key,
            base_url=self._anthropic_base_url(self.config),
            timeout=None,
            is_anthropic=True,
        )

        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)
        try:
            rpm = getattr(self.config, "requests_per_minute", 60) or 60
            await provider_rate_limiter.acquire(self.config.id, rpm)
            create_kwargs: Dict[str, Any] = {
                "model": kwargs.get('model', self.config.default_model),
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }
            # Extended thinking (Task 3): when active, thinking kwargs already
            # carry temperature=1 (Anthropic requires that) and must win. When
            # inactive, fall back to the configured temperature.
            create_kwargs.update(self._thinking_kwargs())
            if "temperature" not in create_kwargs:
                create_kwargs["temperature"] = kwargs.get('temperature', self.config.temperature)
            response = await client.messages.create(**create_kwargs)

            await _record_provider_headers(self.config)

            latency = int((time.time() - start_time) * 1000)
            content = response.content[0].text if response.content else ""
            actual_model      = response.model or kwargs.get('model', self.config.default_model)
            prompt_tokens     = response.usage.input_tokens  if response.usage else 0
            completion_tokens = response.usage.output_tokens if response.usage else 0

            await self._log_usage(
                model_used=actual_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency,
                success=True,
                agentium_id=kwargs.get('agentium_id') or 'system',
            )

            return {
                "content":           content,
                "tokens_used":       prompt_tokens + completion_tokens,
                "prompt_tokens":     prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms":        latency,
                "model":             actual_model,
                "cost_usd":          calculate_cost(
                    actual_model, self.config.provider,
                    prompt_tokens, completion_tokens
                ),
            }
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs):
        """Stream generate."""

        client = _get_cached_sdk_client(
            self.config,
            api_key=self.api_key,
            base_url=self._anthropic_base_url(self.config),
            timeout=None,
            is_anthropic=True,
        )

        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)
        try:
            rpm = getattr(self.config, "requests_per_minute", 60) or 60
            await provider_rate_limiter.acquire(self.config.id, rpm)
            stream_kwargs: Dict[str, Any] = {
                "model": kwargs.get('model', self.config.default_model),
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }
            # Extended thinking (Task 3): wins over configured temperature when active.
            stream_kwargs.update(self._thinking_kwargs())
            if "temperature" not in stream_kwargs:
                stream_kwargs["temperature"] = kwargs.get('temperature', self.config.temperature)
            async with client.messages.stream(**stream_kwargs) as stream:
                await _record_provider_headers(self.config)
                async for text in stream.text_stream:
                    yield text
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Agentic tool-calling loop for the Anthropic Messages API.

        Handles tool_use content blocks in the assistant turn and builds the
        corresponding tool_result user turn as required by the Anthropic spec.
        All tool calls in one response are executed in parallel.

        When ``on_delta`` is supplied and no tools are requested (the final text
        turn), the final turn is streamed token-by-token and each chunk is
        forwarded to ``on_delta``. The blocking tool-call path is used
        unchanged when ``on_delta`` is None or tools are present.

        Args:
            system_prompt:   System-level instruction.
            messages:        Initial conversation turns.
            tools:           Tool definitions in Anthropic input_schema format
                             (produced by tool_registry.to_anthropic_tools()).
            tool_executor:   Async callable(name: str, args: dict) -> str.
            max_iterations:  Safety cap on loop turns (default 10).
            on_delta:        Optional async callback invoked with each streamed
                             text delta (final text turn only).
            cancel_event:    Optional asyncio.Event; if set mid-stream the turn
                             stops early and finish_reason becomes "stopped_by_user".
            **kwargs:        Forwarded to the API (model, max_tokens, agentium_id).

        Returns:
            Same shape as OpenAICompatibleProvider.generate_with_tools() plus
            ``finish_reason`` ("stop" or "stopped_by_user" if cancelled).
        """
        actual_model = kwargs.get("model", self.config.default_model)
        client = getattr(self, "_client", None) or _get_cached_sdk_client(
            self.config,
            api_key=self.api_key,
            base_url=self._anthropic_base_url(self.config),
            timeout=None,
            is_anthropic=True,
        )
        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)

        try:
            loop_finish_reason = "stop"

            for _ in range(max_iterations):
                create_kwargs: Dict[str, Any] = dict(
                    model=actual_model,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    system=system_prompt,
                    messages=conversation,
                )
                # ── Prompt caching (Task 2.1) ────────────────────────────────────
                # Mark the stable prefix (system prompt + everything up to the last
                # stable turn) as cacheable. The current user turn is the final
                # message, so the boundary is the second-to-last message.
                _pc_key = kwargs.get("prompt_cache_key")
                if _pc_key:
                    create_kwargs["system"] = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                    if len(conversation) >= 2:
                        _last_stable = conversation[-2]
                        if isinstance(_last_stable, dict):
                            _content = _last_stable.get("content")
                            if isinstance(_content, str):
                                _last_stable["content"] = [
                                    {
                                        "type": "text",
                                        "content": _content,
                                        "cache_control": {"type": "ephemeral"},
                                    }
                                ]
                            elif isinstance(_content, list) and _content and isinstance(_content[-1], dict):
                                _content[-1]["cache_control"] = {"type": "ephemeral"}
                if tools:
                    create_kwargs["tools"] = tools

                # ── Extended thinking (Task 3) ─────────────────────────────────
                # Merge provider-specific reasoning params (thinking/temperature
                # for Anthropic, extra_body otherwise) into the call kwargs.
                create_kwargs.update(self._thinking_kwargs())

                rpm = getattr(self.config, "requests_per_minute", 60) or 60
                await provider_rate_limiter.acquire(self.config.id, rpm)

                # ── Streaming final-turn path ─────────────────────────────────
                # Only when on_delta is provided AND there are no tools (i.e. the
                # model is producing its final text reply). Tool-call turns and
                # the on_delta=None case stay on the blocking path below.
                if on_delta is not None and not tools:
                    try:
                        stream = await client.messages.create(
                            stream=True, **create_kwargs
                        )
                        await _record_provider_headers(self.config)

                        content = ""
                        async for chunk in stream:
                            if cancel_event is not None and cancel_event.is_set():
                                loop_finish_reason = "stopped_by_user"
                                break

                            ctype = getattr(chunk, "type", None)
                            if ctype == "message_start":
                                msg = getattr(chunk, "message", None)
                                usage = getattr(msg, "usage", None) if msg else None
                                if usage is not None:
                                    total_prompt_tokens += (
                                        getattr(usage, "input_tokens", 0) or 0
                                    )
                            elif ctype == "content_block_delta":
                                delta = getattr(chunk, "delta", None)
                                if delta is not None and getattr(delta, "text", None):
                                    content += delta.text
                                    await on_delta(delta.text)
                            elif ctype == "message_delta":
                                usage = getattr(chunk, "usage", None)
                                if usage is not None:
                                    total_completion_tokens += (
                                        getattr(usage, "output_tokens", 0) or 0
                                    )

                        conversation.append(
                            {"role": "assistant", "content": content}
                        )

                        if cancel_event is not None and cancel_event.is_set():
                            loop_finish_reason = "stopped_by_user"
                        break
                    except Exception:
                        # Any streaming failure (unsupported endpoint, mock
                        # double, transport error) — fall back to the blocking
                        # create below and reuse the existing result assembly.
                        pass

                response = await client.messages.create(**create_kwargs)
                await _record_provider_headers(self.config)

                if response.usage:
                    total_prompt_tokens     += response.usage.input_tokens  or 0
                    total_completion_tokens += response.usage.output_tokens or 0

                # Anthropic requires the raw content block list in the
                # assistant turn — not a plain string.
                conversation.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    # Extract plain text from content blocks
                    content = next(
                        (b.text for b in response.content if hasattr(b, "text")), ""
                    )
                    break

                if response.stop_reason == "tool_use":
                    tool_blocks = [b for b in response.content if b.type == "tool_use"]

                    # Execute all tool calls in parallel
                    results = await asyncio.gather(
                        *[tool_executor(b.name, b.input) for b in tool_blocks],
                        return_exceptions=True,
                    )

                    # All results go back in a single user turn per Anthropic spec
                    tool_results = []
                    for b, result in zip(tool_blocks, results):
                        result_str = (
                            str(result) if not isinstance(result, Exception)
                            else f"ERROR: {result}"
                        )
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": b.id,
                            "content":     result_str,
                        })
                    conversation.append({"role": "user", "content": tool_results})
                else:
                    # Unexpected stop_reason — return whatever text is available
                    content = next(
                        (b.text for b in response.content if hasattr(b, "text")), ""
                    )
                    break
            else:
                content = ""  # max_iterations exhausted

        except Exception as exc:
            latency = int((time.time() - start_time) * 1000)
            await self._log_usage(
                model_used=actual_model,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                latency_ms=latency,
                success=False,
                error=str(exc),
                agentium_id=kwargs.get("agentium_id") or "system",
            )
            raise
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

        latency = int((time.time() - start_time) * 1000)
        total_tokens = total_prompt_tokens + total_completion_tokens
        await self._log_usage(
            model_used=actual_model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=latency,
            success=True,
            agentium_id=kwargs.get("agentium_id") or "system",
        )

        return {
            "content":           content,
            "tokens_used":       total_tokens,
            "prompt_tokens":     total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "latency_ms":        latency,
            "model":             actual_model,
            "messages":          conversation,
            "finish_reason":     loop_finish_reason,
            "cost_usd":          calculate_cost(
                actual_model, self.config.provider,
                total_prompt_tokens, total_completion_tokens
            ),
        }


class LocalProvider(OpenAICompatibleProvider):
    """Local models via Ollama, llama.cpp, LM Studio, etc."""

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        """Generate."""

        combined_prompt = f"{system_prompt}\n\nUser: {user_message}"

        client = _get_cached_sdk_client(
            self.config,
            api_key="ollama",
            base_url=self.base_url or settings.OLLAMA_BASE_URL,
            timeout=self.config.timeout_seconds,
            is_anthropic=False,
        )

        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)
        try:
            rpm = getattr(self.config, "requests_per_minute", 60) or 60
            await provider_rate_limiter.acquire(self.config.id, rpm)
            response = await client.chat.completions.create(
                model=self.config.default_model,
                messages=[{"role": "user", "content": combined_prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                **self._thinking_kwargs(),
            )

            await _record_provider_headers(self.config)

            latency = int((time.time() - start_time) * 1000)

            return {
                "content": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens if response.usage else len(combined_prompt.split()) + len(response.choices[0].message.content.split()),
                "latency_ms": latency,
                "model": response.model or self.config.default_model
            }
        except Exception as e:
            return await self._fallback_local_generate(system_prompt, user_message, kwargs)
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

    async def _fallback_local_generate(self, system_prompt, user_message, kwargs):
        """Fallback for raw HTTP local servers."""
        import aiohttp

        url = f"{self.base_url}/generate" if self.base_url else settings.OLLAMA_BASE_URL.replace("/v1", "/api/generate")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "model": self.config.default_model,
                "prompt": f"{system_prompt}\n\nUser: {user_message}\nAssistant:",
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', self.config.temperature),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens)
                }
            }) as response:
                data = await response.json()
                return {
                    "content": data.get('response', ''),
                    "tokens_used": data.get('eval_count', 0) + data.get('prompt_eval_count', 0),
                    "latency_ms": 0,
                    "model": self.config.default_model
                }

    # generate_with_tools() is fully inherited from OpenAICompatibleProvider
    # since LocalProvider already delegates to the OpenAI-compat endpoint.


# Provider factory — UNIVERSAL mapping
PROVIDERS = {
    ProviderType.ANTHROPIC:       AnthropicProvider,
    ProviderType.GEMINI:          OpenAICompatibleProvider,
    ProviderType.OPENAI:          OpenAICompatibleProvider,
    ProviderType.GROQ:            OpenAICompatibleProvider,
    ProviderType.MISTRAL:         OpenAICompatibleProvider,
    ProviderType.COHERE:          OpenAICompatibleProvider,
    ProviderType.TOGETHER:        OpenAICompatibleProvider,
    ProviderType.FIREWORKS:       OpenAICompatibleProvider,
    ProviderType.PERPLEXITY:      OpenAICompatibleProvider,
    ProviderType.AI21:            OpenAICompatibleProvider,
    ProviderType.MOONSHOT:        OpenAICompatibleProvider,
    ProviderType.DEEPSEEK:        OpenAICompatibleProvider,
    ProviderType.QIANWEN:         OpenAICompatibleProvider,
    ProviderType.ZHIPU:           OpenAICompatibleProvider,
    ProviderType.AZURE_OPENAI:    OpenAICompatibleProvider,
    ProviderType.CUSTOM:          OpenAICompatibleProvider,
    ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
    ProviderType.LOCAL:           LocalProvider,
}


def build_tool_executor(
    agent_id: str,
    task_id: Optional[str],
    db: Any,
    cancel_event: asyncio.Event,
    run_id: str,
) -> Any:
    """Build the per-turn tool executor used by the agentic loop.

    Routes every call through run_tool_async so each tool gets its own
    timeout (per-tool override or global default) and is cancellable via
    ``cancel_event``. Returns a JSON string (the model's tool_result).
    """
    from backend.core.tool_registry import tool_registry

    async def tool_executor(name: str, args: Dict[str, Any]) -> str:
        result = await run_tool_async(
            name,
            args,
            timeout=tool_registry.get_tool_timeout(name),
            cancel_event=cancel_event,
            called_by=agent_id,
            task_id=task_id,
            db=db,
            use_service=True,
            run_id=run_id,
        )
        return json.dumps(result)

    return tool_executor


class ModelService:
    """Service to manage model interactions with any provider."""

    @staticmethod
    async def get_provider(user_id: str, preferred_config_id: Optional[str] = None) -> Optional[BaseModelProvider]:
        """Get provider."""

        with get_db_context() as db:
            if preferred_config_id:
                config = db.query(UserModelConfig).filter_by(
                    id=preferred_config_id,
                    status=ConnectionStatus.ACTIVE
                ).first()
            else:
                config = db.query(UserModelConfig).filter_by(
                    user_id=user_id,
                    is_default=True,
                    status=ConnectionStatus.ACTIVE
                ).first()

            if not config:
                return None

            provider_class = PROVIDERS.get(config.provider)
            if not provider_class:
                raise ValueError(f"Unknown provider: {config.provider}")

            return provider_class(config)

    @staticmethod
    async def generate_with_agent(
        agent,
        user_message: str,
        user_id: str = "sovereign",
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        # Extra kwargs accepted but not used — kept for call-site compatibility
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate response using agent's ethos and user-selected model.
        UNCHANGED from original — kept for full backward compatibility.
        """
        provider = await ModelService.get_provider(user_id, config_id)

        if not provider:
            raise ValueError("No active model configuration found. Please configure in settings.")

        from backend.services.api_key_manager import api_key_manager

        system_prompt = system_prompt_override or (
            agent.ethos.mission_statement if agent.ethos else "You are an AI assistant."
        )

        if agent.ethos:
            try:
                rules = json.loads(agent.ethos.behavioral_rules) if agent.ethos.behavioral_rules else []
                if rules:
                    system_prompt += "\n\nBehavioral Rules:\n" + "\n".join(f"- {r}" for r in rules[:10])
            except:
                pass

        try:
            result = await provider.generate(system_prompt, user_message, **kwargs)
            api_key_manager.mark_key_success(provider.config.id)
            cost = result.get("cost_usd", 0.0)
            tokens = result.get("tokens_used", 0)
            api_key_manager.record_spend(provider.config.id, cost, tokens)
            return result
        except Exception as e:
            is_rate_limit = "rate limit" in str(e).lower() or "429" in str(e)
            api_key_manager.mark_key_failed(provider.config.id, error=str(e), is_rate_limit=is_rate_limit)
            raise

    @staticmethod
    async def generate_with_agent_tools(
        agent,
        user_message: str,
        db,
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        agent_tier: Optional[str] = None,
        task_id: Optional[str] = None,
        max_tool_iterations: int = 10,
        history: Optional[List[Dict[str, str]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Tool-aware generation entry point — Phase 6.9.

        Selects the correct schema format per provider, builds an analytics-
        and audit-wrapped tool executor (all ToolUsageLog rows preserved), and
        drives the agentic loop until the model stops calling tools or
        max_tool_iterations is exhausted.

        Called by AgentOrchestrator.execute_task() in place of generate_with_agent().
        All other callers of generate_with_agent() are NOT affected.

        Args:
            agent:                  Agent entity with agentium_id, ethos, etc.
            user_message:           The task description / user prompt.
            db:                     SQLAlchemy session (passed in from orchestrator).
            config_id:              Optional ModelConfig ID override.
            system_prompt_override: Use instead of ethos.mission_statement.
            agent_tier:             Tier string like "3xxxx". Inferred from
                                    agent.agentium_id[0] + "xxxx" if not supplied.
            task_id:                Passed to ToolUsageLog for analytics correlation.
            max_tool_iterations:    Safety cap on agentic loop turns (default 10).
            **kwargs:               Forwarded to the provider (model, max_tokens, etc.).

        Returns:
            Same shape as generate_with_agent() plus extra keys:
            {
                "content":           str,
                "tokens_used":       int,
                "prompt_tokens":     int,
                "completion_tokens": int,
                "latency_ms":        int,
                "model":             str,
                "messages":          list,   # full conversation history
            }
        """
        from backend.core.tool_registry import tool_registry

        provider = await ModelService.get_provider("sovereign", config_id)
        if not provider:
            raise ValueError("No active model configuration found.")

        # ── Resolve tier ───────────────────────────────────────────────────────
        tier = agent_tier
        if not tier:
            agent_id_str = getattr(agent, "agentium_id", "") or ""
            tier = (agent_id_str[0] + "xxxx") if agent_id_str else "3xxxx"

        # ── Select schema format based on provider type ────────────────────────
        is_anthropic = isinstance(provider, AnthropicProvider)
        tools = (
            tool_registry.to_anthropic_tools(tier)
            if is_anthropic
            else tool_registry.to_openai_tools(tier)
        )

        # A caller (e.g. LLMClient.decide()) may supply its own ``tools`` and
        # ``tool_choice`` via **kwargs to force a specific tool call. Those must
        # win over the generic registry tool set — but ``tools`` is also passed
        # as an explicit keyword below, so pop them out of kwargs first to avoid
        # a "multiple values for keyword argument 'tools'" TypeError.
        caller_tools = kwargs.pop("tools", None)
        caller_tool_choice = kwargs.pop("tool_choice", None)
        if caller_tools is not None:
            tools = caller_tools

        # ── Analytics-wrapped executor ─────────────────────────────────────────
        # Routes every tool call through run_tool_async() (Task 3/4) so each tool
        # gets its own timeout (per-tool override or global default) and is
        # cancellable via the run's cancel_event. ToolCreationService is invoked
        # inside run_tool_async (use_service=True), so ToolUsageLog rows, version
        # tracking, and audit entries are all written exactly as before.
        agent_id = getattr(agent, "agentium_id", "system")

        # ── Build system prompt ────────────────────────────────────────────────
        system_prompt = system_prompt_override
        if not system_prompt:
            ethos = getattr(agent, "ethos", None)
            system_prompt = (ethos.mission_statement if ethos else None) or "You are an AI assistant."
            if ethos:
                try:
                    rules = json.loads(ethos.behavioral_rules) if ethos.behavioral_rules else []
                    if rules:
                        system_prompt += "\n\nBehavioral Rules:\n" + "\n".join(
                            f"- {r}" for r in rules[:10]
                        )
                except Exception:
                    pass

        # ── Hard response-length enforcement (Gap 3) ──────────────────────────
        # Appended LAST so it cannot be overridden by ethos or caller content.
        system_prompt += (
            "\n\nYour response MUST be 2–3 lines maximum. "
            "Never explain governance mechanics. "
            "Never reference internal architecture."
        )
        # ── end enforcement ───────────────────────────────────────────────────

        # ── Seed with prior conversation history (oldest first) ───────────────
        # Lets the model recall earlier turns so context-dependent follow-ups
        # ("try again", "redo the previous task") work like a normal chat.
        messages: List[Dict[str, str]] = list(history) if history else []
        messages.append({"role": "user", "content": user_message})

        from backend.services.api_key_manager import api_key_manager

        run_id = task_id or f"run_{uuid.uuid4().hex}"
        run_event = cancel_event or asyncio.Event()
        register_tool_run(
            ToolCallToken(run_id=run_id, cancel_event=run_event, started_at=time.time())
        )
        try:
            tool_executor = build_tool_executor(
                agent_id=agent_id, task_id=task_id, db=db,
                cancel_event=run_event, run_id=run_id,
            )
            result = await provider.generate_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                max_iterations=max_tool_iterations,
                agentium_id=agent_id,
                on_delta=on_delta,
                cancel_event=run_event,
                **({"tool_choice": caller_tool_choice} if caller_tool_choice else {}),
                **kwargs,
            )
            api_key_manager.mark_key_success(provider.config.id, db=db)
            cost = result.get("cost_usd", 0.0)
            tokens = result.get("tokens_used", 0)
            api_key_manager.record_spend(provider.config.id, cost, tokens, db=db)
            return result
        except Exception as e:
            is_rate_limit = "rate limit" in str(e).lower() or "429" in str(e)
            api_key_manager.mark_key_failed(provider.config.id, error=str(e), is_rate_limit=is_rate_limit, db=db)
            raise
        finally:
            deregister_tool_run(run_id)

    @staticmethod
    async def test_connection(config: UserModelConfig) -> Dict[str, Any]:
        """Test any provider configuration."""
        try:
            provider_class = PROVIDERS.get(config.provider)
            if not provider_class:
                return {"success": False, "error": f"Unknown provider: {config.provider}"}

            provider = provider_class(config)

            result = await provider.generate(
                "You are a test assistant.",
                "Say 'Connection successful' and nothing else.",
                max_tokens=20
            )

            success = "successful" in result['content'].lower() or len(result['content']) > 0
            config.mark_tested(success)

            return {
                "success": success,
                "latency_ms": result['latency_ms'],
                "model": result['model'],
                "response": result['content'][:100],
                "tokens": result['tokens_used']
            }

        except Exception as e:
            config.mark_tested(False, str(e))
            return {
                "success": False,
                "error": str(e)[:200]
            }

    @staticmethod
    async def list_models_for_provider(
        provider: ProviderType,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ) -> List[str]:
        """
        Fetch available models from provider API.
        Falls back to sensible defaults if API call fails.
        """
        try:
            # Users often paste the full chat endpoint (…/v1/chat/completions).
            # The OpenAI SDK appends /models and /chat/completions to the base
            # itself, so the stored base must be the API root. Strip a trailing
            # /chat/completions so listing (and any reuse of base_url) works.
            if base_url:
                base_url = base_url.rstrip('/')
                if base_url.lower().endswith('/chat/completions'):
                    base_url = base_url[: -len('/chat/completions')]

            # ── OPENAI ──────────────────────────────────────────────────────────
            if provider == ProviderType.OPENAI:
                # For a custom base_url (OpenAI-compatible, e.g. OpenRouter) the
                # /models endpoint is frequently public and needs no key. Only
                # fall back to the curated defaults when we have neither a key
                # nor a custom endpoint to query — otherwise we silently hide the
                # real provider's model list behind 8 hardcoded names.
                if not api_key and not base_url:
                    return ModelService._get_default_models(provider)
                import openai
                # The SDK requires a non-empty key to construct the client. For a
                # custom endpoint that doesn't need auth for listing, use a
                # harmless placeholder so the public /models call still works.
                client = openai.AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url) if base_url \
                    else openai.AsyncOpenAI(api_key=api_key)
                try:
                    models = await client.models.list()
                except Exception:
                    # Native OpenAI: keep the friendly fallback to defaults.
                    # Custom endpoint: surface the real error so the user knows
                    # the URL/key is wrong instead of seeing a stale list.
                    if base_url:
                        raise
                    return ModelService._get_default_models(provider)
                ids = [m.id for m in models.data]
                # For the native OpenAI API, filter to the common chat models to
                # cut clutter. For a custom/base_url endpoint, return everything
                # the provider reports (e.g. OpenRouter exposes hundreds of models).
                if not base_url:
                    ids = [m for m in ids
                           if any(x in m.lower() for x in ['gpt-4o', 'gpt-4', 'gpt-3.5', 'o1', 'o3'])]
                return sorted(ids)

            # ── ANTHROPIC ────────────────────────────────────────────────────────
            # Anthropic now exposes a public GET /v1/models endpoint (added after
            # this integration was first written) — fetch live instead of
            # hardcoding a list that goes stale every time a new Claude ships.
            elif provider == ProviderType.ANTHROPIC:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key)
                try:
                    models = await client.models.list()
                    model_ids = sorted([m.id for m in models.data])
                    return model_ids if model_ids else ModelService._get_default_models(provider)
                except Exception as e:
                    logger.error(f"Anthropic list_models error: {e}")
                    return ModelService._get_default_models(provider)

            # ── GEMINI ────────────────────────────────────────────────────────────
            # Uses Google Discovery REST API (v1beta/models) — NOT the old native SDK
            # path that caused: "models/gemini-1.5-flash is not found for API version v1main"
            elif provider == ProviderType.GEMINI:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import aiohttp
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=100"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = []
                            for m in data.get("models", []):
                                name = m.get("name", "")  # e.g. "models/gemini-2.0-flash"
                                # Only include models that support text generation
                                if "generateContent" in m.get("supportedGenerationMethods", []):
                                    model_id = name.replace("models/", "")
                                    models.append(model_id)
                            return sorted(models) if models else ModelService._get_default_models(provider)
                        else:
                            err = await resp.text()
                            logger.error(f"Gemini list error {resp.status}: {err}")
                            return ModelService._get_default_models(provider)

            # ── GROQ ─────────────────────────────────────────────────────────────
            elif provider == ProviderType.GROQ:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── MISTRAL ───────────────────────────────────────────────────────────
            elif provider == ProviderType.MISTRAL:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── TOGETHER ──────────────────────────────────────────────────────────
            elif provider == ProviderType.TOGETHER:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.together.xyz/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── FIREWORKS ─────────────────────────────────────────────────────────
            elif provider == ProviderType.FIREWORKS:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.fireworks.ai/inference/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── PERPLEXITY ────────────────────────────────────────────────────────
            # Perplexity has no public /models endpoint — return curated list
            elif provider == ProviderType.PERPLEXITY:
                return [
                    "sonar-pro",
                    "sonar",
                    "sonar-reasoning-pro",
                    "sonar-reasoning",
                    "r1-1776",
                ]

            # ── COHERE ────────────────────────────────────────────────────────────
            elif provider == ProviderType.COHERE:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.cohere.com/v2/models?page_size=50",
                        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m["name"] for m in data.get("models", []) if "name" in m]
                            return sorted(models) if models else ModelService._get_default_models(provider)
                        return ModelService._get_default_models(provider)

            # ── AI21 ──────────────────────────────────────────────────────────────
            # AI21 has no standard /models endpoint — return curated list
            elif provider == ProviderType.AI21:
                return [
                    "jamba-1.5-large",
                    "jamba-1.5-mini",
                    "jamba-instruct",
                    "j2-ultra",
                    "j2-mid",
                    "j2-light",
                ]

            # ── DEEPSEEK ──────────────────────────────────────────────────────────
            elif provider == ProviderType.DEEPSEEK:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── MOONSHOT ──────────────────────────────────────────────────────────
            elif provider == ProviderType.MOONSHOT:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            # ── QIANWEN (Alibaba) ─────────────────────────────────────────────────
            # No public /models endpoint — return curated list
            elif provider == ProviderType.QIANWEN:
                return [
                    "qwen-max",
                    "qwen-plus",
                    "qwen-turbo",
                    "qwen-long",
                    "qwen2.5-72b-instruct",
                    "qwen2.5-32b-instruct",
                    "qwen2.5-14b-instruct",
                    "qwen2.5-7b-instruct",
                ]

            # ── ZHIPU (ChatGLM) ───────────────────────────────────────────────────
            # No public /models endpoint — return curated list
            elif provider == ProviderType.ZHIPU:
                return [
                    "glm-4-plus",
                    "glm-4",
                    "glm-4-air",
                    "glm-4-flash",
                    "glm-4-long",
                    "chatglm_turbo",
                ]

            # ── AZURE OPENAI ──────────────────────────────────────────────────────
            # Azure lists deployments, not base models — requires resource-specific URL
            elif provider == ProviderType.AZURE_OPENAI:
                if not api_key or not base_url:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers={"api-key": api_key},
                )
                try:
                    models = await client.models.list()
                    return sorted([m.id for m in models.data])
                except Exception:
                    return ModelService._get_default_models(provider)

            # ── LOCAL (Ollama / LM Studio) ────────────────────────────────────────
            elif provider == ProviderType.LOCAL:
                import aiohttp
                url = base_url or settings.OLLAMA_BASE_URL
                if url.endswith('/v1'):
                    url = url[:-3]
                # Try Ollama native /api/tags first
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                models = [m['name'] for m in data.get('models', [])]
                                return sorted(models) if models else ModelService._get_default_models(provider)
                except Exception:
                    pass
                # Fallback: OpenAI-compat /models (LM Studio)
                try:
                    import openai
                    client = openai.AsyncOpenAI(api_key="not-needed", base_url=f"{url}/v1")
                    models = await client.models.list()
                    return sorted([m.id for m in models.data])
                except Exception:
                    return ModelService._get_default_models(provider)

            # ── CUSTOM / OPENAI_COMPATIBLE ────────────────────────────────────────
            elif provider in [ProviderType.CUSTOM, ProviderType.OPENAI_COMPATIBLE]:
                if not base_url:
                    return ["custom-model-1", "custom-model-2"]
                import openai
                # Public /models endpoints (e.g. OpenRouter) need no key — use a
                # placeholder so the SDK client constructs and the call succeeds.
                client = openai.AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            else:
                return ModelService._get_default_models(provider)

        except Exception as e:
            logger.error(f"Error fetching models for {provider}: {e}")
            return ModelService._get_default_models(provider)

    @staticmethod
    def _normalize_base_url(base_url: Optional[str]) -> Optional[str]:
        """Strip a trailing /chat/completions so the base is the API root."""
        if not base_url:
            return None
        base_url = base_url.rstrip('/')
        if base_url.lower().endswith('/chat/completions'):
            base_url = base_url[: -len('/chat/completions')]
        return base_url

    @staticmethod
    def _parse_openai_pricing(model: dict) -> Optional[tuple]:
        """
        Extract (input_per_1m, output_per_1m) USD from an OpenAI-compatible
        model object, handling the two real-world shapes explicitly:

        1. OpenRouter-style nested `pricing` object — values are STRINGS of
           per-token USD, e.g. {"prompt": "0.000005",
           "completion": "0.000015"}. Multiply by 1e6 for per-1M.
        2. LiteLLM-style flat fields `input_cost_per_token` /
           `output_cost_per_token` (also per-token USD, numeric or string).

        Returns None when the model exposes no pricing (treated as free/unknown).
        """
        pricing = model.get("pricing")
        if isinstance(pricing, dict):
            prompt = pricing.get("prompt")
            completion = pricing.get("completion")
            if prompt is not None and completion is not None:
                try:
                    # round() kills float noise from ×1e6 (e.g. 0.0999999… -> 0.1)
                    return (
                        round(float(prompt) * 1_000_000, 6),
                        round(float(completion) * 1_000_000, 6),
                    )
                except (TypeError, ValueError):
                    pass

        # LiteLLM-style flat fields
        ipt = model.get("input_cost_per_token")
        opt = model.get("output_cost_per_token")
        if ipt is not None and opt is not None:
            try:
                return (
                    round(float(ipt) * 1_000_000, 6),
                    round(float(opt) * 1_000_000, 6),
                )
            except (TypeError, ValueError):
                pass

        return None

    @staticmethod
    async def fetch_model_pricing(
        provider: ProviderType,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Optional[tuple]]:
        """
        Fetch live, per-model pricing from a provider's API.

        Returns a map of ``model_id (lower-cased) -> (input_per_1m,
        output_per_1m) in USD`` when the provider exposes pricing, or
        ``model_id -> None`` when it does not (free / unknown — the caller
        should SUPPRESS the price). Providers that don't expose a model list
        with prices return an empty dict.

        The two schemas are handled explicitly rather than assuming one shape:
          * OpenAI-compatible (OpenAI, OpenRouter, Groq, Mistral, Together,
            Fireworks, DeepSeek, Moonshot, Azure, custom): parse the
            `/models` payload's ``pricing`` (OpenRouter) or
            ``input_cost_per_token`` (LiteLLM) fields.
          * Anthropic: ``/v1/models`` returns model metadata ONLY — no
            pricing fields at all — so every model maps to None.
        """
        base_url = ModelService._normalize_base_url(base_url)

        try:
            import httpx

            # ── ANTHROPIC ────────────────────────────────────────────────
            # /v1/models returns {data:[{id, capabilities, max_input_tokens,
            # display_name, ...}]} — NO pricing. Every model is None (free).
            if provider == ProviderType.ANTHROPIC:
                if not api_key:
                    return {}
                url = (base_url or "https://api.anthropic.com") + "/v1/models"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Accept": "application/json",
                }
                async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return {}
                    data = resp.json()
                result: Dict[str, Optional[tuple]] = {}
                for m in data.get("data", []):
                    mid = (m.get("id") or "").strip().lower()
                    if mid:
                        result[mid] = None
                return result

            # ── LOCAL (Ollama / LM Studio) ──────────────────────────────
            # No published pricing for self-hosted models.
            if provider == ProviderType.LOCAL:
                return {}

            # ── OPENAI (native) ──────────────────────────────────────────
            # Native api.openai.com /models carries no pricing fields, so every
            # listed model resolves to None (free/unknown). Only query when we
            # actually have a key; otherwise there's nothing to fetch.
            if provider == ProviderType.OPENAI and not base_url:
                if not api_key:
                    return {}
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                return await ModelService._fetch_openai_style_pricing(url, headers)

            # ── OPENAI-COMPATIBLE (custom base, Azure, Groq, Mistral,
            #    Together, Fireworks, DeepSeek, Moonshot) ───────────────────
            # All expose an OpenAI-style /models endpoint that MAY include a
            # `pricing` object (e.g. OpenRouter, Azure Marketplace gateways).
            openai_compat_bases = {
                ProviderType.GROQ: "https://api.groq.com/openai/v1",
                ProviderType.MISTRAL: "https://api.mistral.ai/v1",
                ProviderType.TOGETHER: "https://api.together.xyz/v1",
                ProviderType.FIREWORKS: "https://api.fireworks.ai/inference/v1",
                ProviderType.DEEPSEEK: "https://api.deepseek.com/v1",
                ProviderType.MOONSHOT: "https://api.moonshot.cn/v1",
            }
            if provider in openai_compat_bases:
                if not api_key:
                    return {}
                url = openai_compat_bases[provider] + "/models"
                headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                return await ModelService._fetch_openai_style_pricing(url, headers)

            if provider in (ProviderType.CUSTOM, ProviderType.OPENAI_COMPATIBLE):
                if not base_url:
                    return {}
                url = base_url + "/models"
                headers = {"Accept": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                return await ModelService._fetch_openai_style_pricing(url, headers)

            if provider == ProviderType.AZURE_OPENAI:
                if not api_key or not base_url:
                    return {}
                url = base_url.rstrip('/') + "/models"
                headers = {"api-key": api_key, "Accept": "application/json"}
                return await ModelService._fetch_openai_style_pricing(url, headers)

            # ── OTHER PROVIDERS (Gemini, Perplexity, Cohere, AI21, Qwen,
            #    Zhipu) ── no price-bearing /models endpoint ────────────────
            return {}

        except Exception as e:
            logger.error(f"fetch_model_pricing failed for {provider}: {e}")
            return {}

    @staticmethod
    async def _fetch_openai_style_pricing(
        url: str, headers: dict
    ) -> Dict[str, Optional[tuple]]:
        """GET an OpenAI-style /models endpoint and extract per-model pricing."""
        import httpx

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            data = resp.json()

        # OpenRouter wraps in {"data": [...]}; OpenAI returns a bare list.
        models = data.get("data", data) if isinstance(data, dict) else data

        result: Dict[str, Optional[tuple]] = {}
        for m in models:
            if not isinstance(m, dict):
                # The OpenAI SDK serialises Model objects; coerce to dict.
                m = m.model_dump() if hasattr(m, "model_dump") else None
                if not isinstance(m, dict):
                    continue
            mid = (m.get("id") or "").strip().lower()
            if not mid:
                continue
            result[mid] = ModelService._parse_openai_pricing(m)
        return result

    @staticmethod
    def _get_default_models(provider: ProviderType) -> List[str]:
        """Get current curated defaults when live API fetch fails."""
        defaults = {
            ProviderType.OPENAI: [
                "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
                "gpt-5.3-codex", "o4-mini", "gpt-4.1", "gpt-4o",
            ],
            ProviderType.ANTHROPIC: [
                "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5",
                "claude-opus-4-7", "claude-opus-4-5", "claude-sonnet-4-5",
            ],
            ProviderType.GEMINI: [
                "gemini-3.1-pro", "gemini-3.5-flash", "gemini-3.1-flash-lite",
                "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ],
            ProviderType.GROQ: [
                "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
                "mixtral-8x7b-32768", "gemma2-9b-it",
                "deepseek-r1-distill-llama-70b",
            ],
            ProviderType.MISTRAL: [
                "mistral-large-latest", "mistral-small-latest",
                "codestral-latest", "open-mistral-nemo",
            ],
            ProviderType.TOGETHER: [
                "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                "Qwen/Qwen2.5-72B-Instruct-Turbo",
                "deepseek-ai/DeepSeek-R1",
                "mistralai/Mixtral-8x7B-Instruct-v0.1",
            ],
            ProviderType.FIREWORKS: [
                "accounts/fireworks/models/llama-v3p3-70b-instruct",
                "accounts/fireworks/models/llama-v3p1-8b-instruct",
                "accounts/fireworks/models/mixtral-8x7b-instruct",
                "accounts/fireworks/models/deepseek-r1",
            ],
            ProviderType.PERPLEXITY: [
                "sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-reasoning", "r1-1776",
            ],
            ProviderType.COHERE: [
                "command-r-plus", "command-r", "command-a-03-2025",
            ],
            ProviderType.AI21: [
                "jamba-1.5-large", "jamba-1.5-mini", "jamba-instruct",
            ],
            ProviderType.MOONSHOT: [
                "moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k",
            ],
            ProviderType.DEEPSEEK: [
                "deepseek-chat", "deepseek-reasoner",
            ],
            ProviderType.QIANWEN: [
                "qwen-max", "qwen-plus", "qwen-turbo",
                "qwen2.5-72b-instruct", "qwen2.5-32b-instruct",
            ],
            ProviderType.ZHIPU: [
                "glm-4-plus", "glm-4", "glm-4-air", "glm-4-flash",
            ],
            ProviderType.AZURE_OPENAI: [
                "gpt-4o", "gpt-4", "gpt-35-turbo",
            ],
            ProviderType.LOCAL: [
                "llama3.2", "llama3.1", "mistral", "qwen2.5", "phi4", "deepseek-r1",
            ],
        }
        return defaults.get(provider, ["model-1", "model-2"])