"""
DeepThinkTool — Universal extended reasoning for all agents on all providers.

Routing:
  - Anthropic key available + capable model → native extended thinking API
    (claude-3-7-sonnet-20250219, claude-opus-4-5, claude-sonnet-4-5)
  - Any other provider (OpenAI, Groq, Gemini, Mistral, local, …)
    → structured XML chain-of-thought prompt

Returns a normalised ThinkingResult dict so callers never need to know
which path executed.

Registered in ToolRegistry as 'deep_think'.
Authorized for ALL agent tiers (0xxxx–6xxxx).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Models that support Anthropic native extended thinking ─────────────────────
NATIVE_THINKING_MODELS = {
    "claude-3-7-sonnet-20250219",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-3-5-sonnet-20241022",
}

# ── CoT scaffold injected as a system-prompt addendum for non-Anthropic paths ──
COT_SYSTEM_ADDENDUM = """

Before answering, reason through the problem inside <thinking> tags.
Structure your thinking as:
  <thinking>
    <understand>Restate the problem in your own words</understand>
    <decompose>Break it into sub-problems or decision points</decompose>
    <consider>List at least 3 approaches, angles, or options</consider>
    <evaluate>Weigh trade-offs and risks for each</evaluate>
    <decide>State your chosen approach and the reason</decide>
  </thinking>

Then provide your final answer OUTSIDE the tags.
Be exhaustive inside <thinking>. The quality of your reasoning matters
more than the length of your final answer.
"""


class DeepThinkTool:
    """
    Provider-agnostic deep reasoning tool.

    Registered in ToolRegistry as 'deep_think'.
    Available to all agent tiers (0xxxx–6xxxx).

    execute() signature is intentionally **kwargs-friendly so the tool
    executor can inject 'db' and 'agent_id' without breaking callers
    that don't supply them.
    """

    TOOL_NAME        = "deep_think"
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]

    # ── Public entry-point ─────────────────────────────────────────────────────

    async def execute(
        self,
        problem: str,
        context: Optional[str] = None,
        budget_tokens: int = 8000,
        agent_id: Optional[str] = None,
        db=None,
        **_kwargs,                         # absorb any extra injected kwargs
    ) -> Dict[str, Any]:
        """
        Run extended/deep thinking on `problem`.

        Args:
            problem:       The question, task, or decision to reason through.
            context:       Optional background context or constraints.
            budget_tokens: Anthropic thinking token budget (1 024–32 000,
                           native path only). Ignored on CoT path.
            agent_id:      Calling agent's ID — used for usage logging.
            db:            SQLAlchemy session injected by tool_creation_service.
                           Required for model-config lookup; if None the tool
                           falls back to a prompt-only CoT scaffold.

        Returns a dict with keys:
            thinking_text  – raw reasoning scratchpad
            conclusion     – final answer / decision
            confidence     – 0.0–1.0 self-reported heuristic
            provider_path  – "anthropic_native" | "cot_prompt" | "no_config" | "error"
            model_used     – model identifier string
            tokens_used    – integer
            latency_ms     – integer
            status         – "success" | "error"
            error          – str | None
        """
        start = time.monotonic()

        # ── 1. Pick best available model config from DB ────────────────────────
        anthropic_cfg = None
        fallback_cfg  = None

        if db is not None:
            anthropic_cfg, fallback_cfg = self._pick_configs(db)

        # ── 2. Route to best available path ───────────────────────────────────
        try:
            if anthropic_cfg is not None:
                result = await self._run_native_thinking(
                    config=anthropic_cfg,
                    problem=problem,
                    context=context,
                    budget_tokens=max(1024, int(budget_tokens)),
                    agent_id=agent_id,
                )
            elif fallback_cfg is not None:
                result = await self._run_cot_prompt(
                    config=fallback_cfg,
                    problem=problem,
                    context=context,
                    agent_id=agent_id,
                )
            else:
                result = self._run_cot_no_config(problem, context)

        except Exception as exc:
            logger.exception("[DeepThinkTool] execution error: %s", exc)
            return {
                "thinking_text": "",
                "conclusion":    f"Deep thinking failed: {exc}",
                "confidence":    0.0,
                "provider_path": "error",
                "model_used":    "none",
                "tokens_used":   0,
                "latency_ms":    int((time.monotonic() - start) * 1000),
                "status":        "error",
                "error":         str(exc),
            }

        result["latency_ms"] = int((time.monotonic() - start) * 1000)
        result["status"]     = "success"
        result["error"]      = None
        return result

    # ── Private: config selection ──────────────────────────────────────────────

    def _pick_configs(self, db):
        """
        Scan active UserModelConfigs from the DB and return
        (best_anthropic_config, best_fallback_config).
        Returns (None, None) on any DB error — the tool will then
        fall back to the no-config CoT scaffold.
        """
        try:
            from backend.models.entities.user_config import (
                UserModelConfig,
                ProviderType,
                ConnectionStatus,
            )

            configs = (
                db.query(UserModelConfig)
                .filter_by(is_active=True, connection_status=ConnectionStatus.ACTIVE)
                .all()
            )
        except Exception as exc:
            logger.warning("[DeepThinkTool] DB config lookup failed: %s", exc)
            return None, None

        anthropic_cfg = None
        fallback_cfg  = None

        for cfg in configs:
            if cfg.provider == ProviderType.ANTHROPIC:
                model = cfg.default_model or ""
                # Prefer models with confirmed native thinking support
                if any(m in model for m in NATIVE_THINKING_MODELS):
                    anthropic_cfg = cfg
                elif anthropic_cfg is None:
                    # Accept any Anthropic config as a secondary fallback;
                    # the API call will error gracefully if the model doesn't
                    # support thinking — caught by the outer try/except.
                    anthropic_cfg = cfg
            elif fallback_cfg is None:
                fallback_cfg = cfg

        return anthropic_cfg, fallback_cfg

    # ── Private: Anthropic native extended thinking ────────────────────────────

    async def _run_native_thinking(
        self,
        config,
        problem: str,
        context: Optional[str],
        budget_tokens: int,
        agent_id: Optional[str],
    ) -> Dict[str, Any]:
        import anthropic as _anthropic

        client = _anthropic.AsyncAnthropic(api_key=config.api_key)
        model  = config.default_model

        system     = context or "You are a careful, thorough reasoning assistant."
        max_tokens = max(budget_tokens + 2000, getattr(config, "max_tokens", None) or 8000)

        # NOTE: temperature must be omitted (or set to 1) for extended thinking.
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "enabled", "budget_tokens": budget_tokens},
            messages=[{"role": "user", "content": problem}],
        )

        thinking_text = ""
        conclusion    = ""
        for block in response.content:
            if block.type == "thinking":
                thinking_text += block.thinking
            elif block.type == "text":
                conclusion += block.text

        tokens = 0
        if response.usage:
            tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        return {
            "thinking_text": thinking_text,
            "conclusion":    conclusion,
            "confidence":    self._estimate_confidence(thinking_text, conclusion),
            "provider_path": "anthropic_native",
            "model_used":    model,
            "tokens_used":   tokens,
        }

    # ── Private: structured CoT prompt (any OpenAI-compatible provider) ────────

    async def _run_cot_prompt(
        self,
        config,
        problem: str,
        context: Optional[str],
        agent_id: Optional[str],
    ) -> Dict[str, Any]:
        from backend.services.model_provider import ModelService

        provider_class = ModelService._get_provider_class(config.provider)
        if provider_class is None:
            raise ValueError(f"No provider class for {config.provider}")

        provider = provider_class(config)
        system   = (context or "You are a careful reasoning assistant.") + COT_SYSTEM_ADDENDUM

        result = await provider.generate(
            system_prompt=system,
            user_message=problem,
            max_tokens=getattr(config, "max_tokens", None) or 4096,
            temperature=0.3,            # lower temp → more consistent reasoning
            agentium_id=agent_id or "system",
        )

        raw          = result.get("content", "")
        thinking_txt = self._extract_thinking_xml(raw)
        conclusion   = self._strip_thinking_xml(raw).strip()

        return {
            "thinking_text": thinking_txt,
            "conclusion":    conclusion,
            "confidence":    self._estimate_confidence(thinking_txt, conclusion),
            "provider_path": "cot_prompt",
            "model_used":    result.get("model", str(config.default_model)),
            "tokens_used":   result.get("tokens_used", 0),
        }

    # ── Private: last-resort — no DB / no configs ──────────────────────────────

    def _run_cot_no_config(self, problem: str, context: Optional[str]) -> Dict[str, Any]:
        """
        Returns the CoT scaffold as thinking_text so the calling agent can
        embed it in its own next prompt if it wants structured reasoning.
        """
        scaffold = (
            f"{COT_SYSTEM_ADDENDUM.strip()}\n\nProblem to reason through:\n{problem}"
        )
        return {
            "thinking_text": scaffold,
            "conclusion":    (
                "No active model config found. "
                "Embed the thinking scaffold in your next prompt for structured CoT."
            ),
            "confidence":    0.0,
            "provider_path": "no_config",
            "model_used":    "none",
            "tokens_used":   0,
        }

    # ── Private: helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_thinking_xml(text: str) -> str:
        import re
        m = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _strip_thinking_xml(text: str) -> str:
        import re
        return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)

    @staticmethod
    def _estimate_confidence(thinking: str, conclusion: str) -> float:
        """
        Lightweight zero-latency heuristic.
        Longer + more structured thinking → higher score.
        Does NOT call an LLM.
        """
        if not thinking and not conclusion:
            return 0.0
        length_score = min(len(thinking) / 2000, 1.0) * 0.5
        structure    = 0.3 if ("<decide>" in thinking or "therefore" in thinking.lower()) else 0.0
        has_concl    = 0.2 if len(conclusion) > 50 else 0.0
        return round(min(length_score + structure + has_concl, 1.0), 2)


# ── Module-level singleton (imported by tool_registry.py) ─────────────────────
deep_think_tool = DeepThinkTool()