"""
Universal Model Provider Service for Agentium 

"""

import asyncio
import os
import time
import json
from typing import Optional, Dict, Any, AsyncGenerator, List, Callable, Tuple
from abc import ABC, abstractmethod
from datetime import datetime

from backend.models.database import get_db_context
from backend.models.entities.user_config import UserModelConfig, ProviderType, ModelUsageLog


# ─────────────────────────────────────────────────────────────────────────────
# Per-model pricing table
# Prices are USD per 1 M tokens (input_rate, output_rate).
# Source: official provider pricing pages as of early 2026.
# ─────────────────────────────────────────────────────────────────────────────

# fmt: off
MODEL_PRICES: Dict[str, Tuple[float, float]] = {
    # ── OpenAI ───────────────────────────────────────────────────────────────
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
    "claude-3-5-sonnet-20241022":      (3.00,   15.00),
    "claude-3-5-sonnet-20240620":      (3.00,   15.00),
    "claude-3-5-haiku-20241022":       (0.80,    4.00),
    "claude-3-opus-20240229":          (15.00,  75.00),
    "claude-3-sonnet-20240229":        (3.00,   15.00),
    "claude-3-haiku-20240307":         (0.25,    1.25),
    "claude-2.1":                      (8.00,   24.00),
    "claude-2.0":                      (8.00,   24.00),

    # ── Google Gemini ─────────────────────────────────────────────────────────
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
    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo":  (0.88,  0.88),
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo":   (0.18,  0.18),
    "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": (3.50,  3.50),
    "mistralai/Mixtral-8x7B-Instruct-v0.1":          (0.60,  0.60),
    "Qwen/Qwen2.5-72B-Instruct-Turbo":               (1.20,  1.20),

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

    # 1. Exact match
    prices = MODEL_PRICES.get(model_name) or MODEL_PRICES.get(normalised)

    # 2. Prefix match — handles "gpt-4o-2024-xx-xx" → "gpt-4o" etc.
    if prices is None:
        for key, val in MODEL_PRICES.items():
            if normalised.startswith(key.lower()):
                prices = val
                break

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
        self.config = config
        self.api_key = self._get_api_key() if config.requires_api_key() else None
        self.base_url = config.get_effective_base_url()

    def _get_api_key(self) -> Optional[str]:
        """Decrypt API key."""
        if not self.config.api_key_encrypted:
            return None
        from backend.core.security import decrypt_api_key
        try:
            return decrypt_api_key(self.config.api_key_encrypted)
        except:
            return None

    @abstractmethod
    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs) -> AsyncGenerator[str, None]:
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
                ))
                db.commit()
        except Exception as exc:
            # Logging must never crash the main request path
            print(f"⚠️  _log_usage failed: {exc}")


class OpenAICompatibleProvider(BaseModelProvider):
    """
    Universal provider for ANY OpenAI-compatible API.
    Works with Groq, Mistral, Together, Fireworks, Local models, etc.
    GeminiProvider and LocalProvider inherit generate_with_tools() automatically.
    """

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds
        )

        start_time = time.time()
        try:
            response = await client.chat.completions.create(
                model=kwargs.get('model', self.config.default_model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                top_p=kwargs.get('top_p', self.config.top_p),
            )

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
                agentium_id=kwargs.get('agentium_id', 'system'),
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
                agentium_id=kwargs.get('agentium_id', 'system'),
            )
            raise

    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs):
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds
        )

        stream = await client.chat.completions.create(
            model=kwargs.get('model', self.config.default_model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            stream=True,
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
            temperature=kwargs.get('temperature', self.config.temperature),
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
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
        import openai

        actual_model = kwargs.get("model", self.config.default_model)
        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
        )

        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        start_time = time.time()

        try:
            for _ in range(max_iterations):
                create_kwargs: Dict[str, Any] = dict(
                    model=actual_model,
                    messages=[{"role": "system", "content": system_prompt}] + conversation,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                )
                if tools:
                    create_kwargs["tools"] = tools
                    create_kwargs["tool_choice"] = "auto"

                response = await client.chat.completions.create(**create_kwargs)
                msg = response.choices[0].message

                if response.usage:
                    total_prompt_tokens     += response.usage.prompt_tokens     or 0
                    total_completion_tokens += response.usage.completion_tokens or 0

                # Append raw assistant turn to history so the next iteration
                # has full context.  model_dump(exclude_none=True) avoids
                # sending null fields that some providers reject.
                try:
                    conversation.append(msg.model_dump(exclude_none=True))
                except Exception:
                    # Fallback for providers that return non-Pydantic objects
                    conversation.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        **({"tool_calls": [tc.model_dump() for tc in msg.tool_calls]} if msg.tool_calls else {}),
                    })

                finish_reason = response.choices[0].finish_reason

                # Model signalled it is done — no more tool calls
                if finish_reason == "stop" or not msg.tool_calls:
                    content = msg.content or ""
                    break

                if finish_reason == "tool_calls" and msg.tool_calls:
                    # Execute ALL tool calls in this response in parallel
                    results = await asyncio.gather(
                        *[
                            tool_executor(tc.function.name, json.loads(tc.function.arguments or "{}"))
                            for tc in msg.tool_calls
                        ],
                        return_exceptions=True,
                    )

                    # Feed each result back as a separate tool message
                    for tc, result in zip(msg.tool_calls, results):
                        result_str = (
                            str(result) if not isinstance(result, Exception)
                            else f"ERROR: {result}"
                        )
                        conversation.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content":      result_str,
                        })
                else:
                    # Unexpected finish_reason — return whatever content exists
                    content = msg.content or ""
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
                agentium_id=kwargs.get("agentium_id", "system"),
            )
            raise

        latency = int((time.time() - start_time) * 1000)
        total_tokens = total_prompt_tokens + total_completion_tokens
        await self._log_usage(
            model_used=actual_model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=latency,
            success=True,
            agentium_id=kwargs.get("agentium_id", "system"),
        )

        return {
            "content":           content,
            "tokens_used":       total_tokens,
            "prompt_tokens":     total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "latency_ms":        latency,
            "model":             actual_model,
            "messages":          conversation,
            "cost_usd":          calculate_cost(
                actual_model, self.config.provider,
                total_prompt_tokens, total_completion_tokens
            ),
        }


class AnthropicProvider(BaseModelProvider):
    """Anthropic Claude API."""

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        start_time = time.time()
        response = await client.messages.create(
            model=kwargs.get('model', self.config.default_model),
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
            temperature=kwargs.get('temperature', self.config.temperature),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

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
            agentium_id=kwargs.get('agentium_id', 'system'),
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

    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs):
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        async with client.messages.stream(
            model=kwargs.get('model', self.config.default_model),
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
            temperature=kwargs.get('temperature', self.config.temperature),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Agentic tool-calling loop for the Anthropic Messages API.

        Handles tool_use content blocks in the assistant turn and builds the
        corresponding tool_result user turn as required by the Anthropic spec.
        All tool calls in one response are executed in parallel.

        Args:
            system_prompt:   System-level instruction.
            messages:        Initial conversation turns.
            tools:           Tool definitions in Anthropic input_schema format
                             (produced by tool_registry.to_anthropic_tools()).
            tool_executor:   Async callable(name: str, args: dict) -> str.
            max_iterations:  Safety cap on loop turns (default 10).
            **kwargs:        Forwarded to the API (model, max_tokens, agentium_id).

        Returns:
            Same shape as OpenAICompatibleProvider.generate_with_tools().
        """
        import anthropic

        actual_model = kwargs.get("model", self.config.default_model)
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        start_time = time.time()

        try:
            for _ in range(max_iterations):
                create_kwargs: Dict[str, Any] = dict(
                    model=actual_model,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    system=system_prompt,
                    messages=conversation,
                )
                if tools:
                    create_kwargs["tools"] = tools

                response = await client.messages.create(**create_kwargs)

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
                agentium_id=kwargs.get("agentium_id", "system"),
            )
            raise

        latency = int((time.time() - start_time) * 1000)
        total_tokens = total_prompt_tokens + total_completion_tokens
        await self._log_usage(
            model_used=actual_model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=latency,
            success=True,
            agentium_id=kwargs.get("agentium_id", "system"),
        )

        return {
            "content":           content,
            "tokens_used":       total_tokens,
            "prompt_tokens":     total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "latency_ms":        latency,
            "model":             actual_model,
            "messages":          conversation,
            "cost_usd":          calculate_cost(
                actual_model, self.config.provider,
                total_prompt_tokens, total_completion_tokens
            ),
        }


class GeminiProvider(BaseModelProvider):
    """Google Gemini API (via OpenAI compatibility layer)."""

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=self.config.timeout_seconds
        )

        start_time = time.time()
        response = await client.chat.completions.create(
            model=kwargs.get('model', self.config.default_model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
        )

        latency = int((time.time() - start_time) * 1000)

        return {
            "content": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens if response.usage else 0,
            "latency_ms": latency,
            "model": response.model
        }

    async def stream_generate(self, system_prompt: str, user_message: str, **kwargs):
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        stream = await client.chat.completions.create(
            model=kwargs.get('model', self.config.default_model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            stream=True,
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # generate_with_tools() is inherited from OpenAICompatibleProvider
    # once base_url is set to the Gemini OpenAI-compat endpoint.
    # Override here so the correct base_url is used.
    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        # Temporarily set base_url to Gemini endpoint, then delegate to the
        # OpenAI-compatible implementation.
        original_base_url = self.base_url
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        try:
            return await OpenAICompatibleProvider.generate_with_tools(
                self, system_prompt, messages, tools, tool_executor, max_iterations, **kwargs
            )
        finally:
            self.base_url = original_base_url


class LocalProvider(OpenAICompatibleProvider):
    """Local models via Ollama, llama.cpp, LM Studio, etc."""

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        combined_prompt = f"{system_prompt}\n\nUser: {user_message}"

        import openai

        client = openai.AsyncOpenAI(
            base_url=self.base_url or "http://localhost:11434/v1",
            api_key="ollama"
        )

        start_time = time.time()
        try:
            response = await client.chat.completions.create(
                model=self.config.default_model,
                messages=[{"role": "user", "content": combined_prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
            )

            latency = int((time.time() - start_time) * 1000)

            return {
                "content": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens if response.usage else len(combined_prompt.split()) + len(response.choices[0].message.content.split()),
                "latency_ms": latency,
                "model": response.model or self.config.default_model
            }
        except Exception as e:
            return await self._fallback_local_generate(system_prompt, user_message, kwargs)

    async def _fallback_local_generate(self, system_prompt, user_message, kwargs):
        """Fallback for raw HTTP local servers."""
        import aiohttp

        url = f"{self.base_url}/generate" if self.base_url else "http://localhost:11434/api/generate"

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
                    "tokens_used": data.get('eval_count', 0),
                    "latency_ms": 0,
                    "model": self.config.default_model
                }

    # generate_with_tools() is fully inherited from OpenAICompatibleProvider
    # since LocalProvider already delegates to the OpenAI-compat endpoint.


# Provider factory — UNIVERSAL mapping
PROVIDERS = {
    ProviderType.ANTHROPIC:       AnthropicProvider,
    ProviderType.GEMINI:          GeminiProvider,
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


class ModelService:
    """Service to manage model interactions with any provider."""

    @staticmethod
    async def get_provider(user_id: str, preferred_config_id: Optional[str] = None) -> Optional[BaseModelProvider]:
        """Get provider instance for user."""
        with get_db_context() as db:
            if preferred_config_id:
                config = db.query(UserModelConfig).filter_by(
                    id=preferred_config_id,
                    user_id=user_id,
                    status='active'
                ).first()
            else:
                config = db.query(UserModelConfig).filter_by(
                    user_id=user_id,
                    is_default=True,
                    status='active'
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

        return await provider.generate(system_prompt, user_message)

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
        from backend.services.tool_creation_service import ToolCreationService

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

        # ── Analytics-wrapped executor ─────────────────────────────────────────
        # Routes every tool call through ToolCreationService.execute_tool() so
        # ToolUsageLog rows, version tracking, and audit entries are all written
        # exactly as they are for direct tool executions.
        svc = ToolCreationService(db)
        agent_id = getattr(agent, "agentium_id", "system")

        async def tool_executor(name: str, args: Dict[str, Any]) -> str:
            # execute_tool is synchronous; run in thread pool to avoid blocking
            # the event loop during heavy tool calls.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: svc.execute_tool(
                    tool_name=name,
                    called_by=agent_id,
                    kwargs=args,
                    task_id=task_id,
                ),
            )
            return json.dumps(result)

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

        messages = [{"role": "user", "content": user_message}]

        return await provider.generate_with_tools(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            tool_executor=tool_executor,
            max_iterations=max_tool_iterations,
            agentium_id=agent_id,
            **kwargs,
        )

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
            if provider == ProviderType.OPENAI:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key)
                models = await client.models.list()
                return sorted([
                    m.id for m in models.data
                    if any(x in m.id.lower() for x in ['gpt-4', 'gpt-3.5', 'gpt-4o'])
                ])

            elif provider == ProviderType.GROQ:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            elif provider == ProviderType.MISTRAL:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            elif provider == ProviderType.TOGETHER:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.together.xyz/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            elif provider == ProviderType.DEEPSEEK:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            elif provider == ProviderType.MOONSHOT:
                if not api_key:
                    return ModelService._get_default_models(provider)
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            elif provider == ProviderType.ANTHROPIC:
                return [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307"
                ]

            elif provider == ProviderType.GEMINI:
                return [
                    "gemini-1.5-pro-latest",
                    "gemini-1.5-flash-latest",
                    "gemini-1.0-pro"
                ]

            elif provider == ProviderType.LOCAL:
                import aiohttp
                url = base_url or "http://localhost:11434"
                if url.endswith('/v1'):
                    url = url[:-3]
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m['name'] for m in data.get('models', [])]
                            return sorted(models) if models else ModelService._get_default_models(provider)
                        else:
                            return ModelService._get_default_models(provider)

            elif provider in [ProviderType.CUSTOM, ProviderType.OPENAI_COMPATIBLE]:
                if not base_url or not api_key:
                    return ["custom-model-1", "custom-model-2"]
                import openai
                client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
                models = await client.models.list()
                return sorted([m.id for m in models.data])

            else:
                return ModelService._get_default_models(provider)

        except Exception as e:
            print(f"Error fetching models for {provider}: {e}")
            return ModelService._get_default_models(provider)

    @staticmethod
    def _get_default_models(provider: ProviderType) -> List[str]:
        """Get sensible default models when API fetch fails."""
        defaults = {
            ProviderType.OPENAI: [
                "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-3.5-turbo"
            ],
            ProviderType.ANTHROPIC: [
                "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"
            ],
            ProviderType.GROQ: [
                "llama-3.3-70b-versatile", "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"
            ],
            ProviderType.MISTRAL: [
                "mistral-large-latest", "mistral-medium-latest",
                "mistral-small-latest", "open-mistral-7b"
            ],
            ProviderType.TOGETHER: [
                "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "Qwen/Qwen2.5-72B-Instruct-Turbo"
            ],
            ProviderType.GEMINI: [
                "gemini-1.5-pro-latest", "gemini-1.5-flash-latest", "gemini-1.0-pro"
            ],
            ProviderType.MOONSHOT: [
                "moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"
            ],
            ProviderType.DEEPSEEK: [
                "deepseek-chat", "deepseek-coder"
            ],
            ProviderType.LOCAL: [
                "llama3.2", "llama3.1", "mistral", "qwen2.5", "phi3"
            ],
            ProviderType.COHERE: [
                "command-r-plus", "command-r", "command"
            ],
        }
        return defaults.get(provider, ["model-1", "model-2"])