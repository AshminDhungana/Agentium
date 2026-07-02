"""
WorkflowPlanner — turns a compound user instruction into a structured
WorkflowPlan (ordered list of atomic sub-tasks with declared dependencies).

Strategy:
  1. Ask the configured LLM to extract sub-tasks as JSON.
  2. On any failure (LLM unavailable, JSON parse error) fall back to a
     deterministic keyword parser that handles the common HDFC-style pattern.
"""
import json
import uuid
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt injected into the LLM call
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a workflow decomposition engine.
Given a user instruction, extract an ordered JSON array of atomic sub-tasks.

Each element must have exactly these keys:
  intent              (str)  — one of: fetch_stock_price | send_email |
                                       create_reminder | schedule_followup
  params              (dict) — tool-specific parameters (see examples below)
  depends_on          (list) — intent names that must succeed before this runs
  schedule_offset_days (int) — 0 = run immediately; 14 = defer by 14 days

Parameter examples:
  fetch_stock_price : {"ticker": "HDFCBANK.NS"}
  send_email        : {"to": "", "subject": "Stock Price", "body_template":
                       "Current price: {{fetch_stock_price.display}}",
                       "inject_from": "fetch_stock_price"}
  create_reminder   : {"message": "<reminder text>", "delay_seconds": 0}
  schedule_followup : {"message": "<follow-up text>", "delay_seconds": 1209600}

Return ONLY the raw JSON array — no markdown fences, no prose."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SubTaskSpec:
    """SubTaskSpec."""
    intent: str
    params: dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    schedule_offset_days: int = 0
    step_index: int = 0


@dataclass
class WorkflowPlan:
    """WorkflowPlan."""
    workflow_id: str
    original_message: str
    subtasks: List[SubTaskSpec]


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class WorkflowPlanner:
    """
    Parses a raw user message into a WorkflowPlan.
    Falls back to rule-based parsing if the LLM call fails.
    """

    def __init__(self, model_config_id: Optional[str] = None):
        """Init."""

        self.model_config_id = model_config_id

    async def parse(self, message: str) -> WorkflowPlan:
        """Parse."""

        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        try:
            subtasks = await self._llm_parse(message)
            logger.info(
                f"[WorkflowPlanner] LLM extracted {len(subtasks)} sub-tasks "
                f"for workflow {workflow_id}"
            )
        except Exception as exc:
            logger.warning(
                f"[WorkflowPlanner] LLM parse failed ({exc}), "
                "falling back to rule-based parser"
            )
            subtasks = self._rule_based_parse(message)

        for i, st in enumerate(subtasks):
            st.step_index = i

        return WorkflowPlan(
            workflow_id=workflow_id,
            original_message=message,
            subtasks=subtasks,
        )

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    async def _llm_parse(self, message: str) -> List[SubTaskSpec]:
        """Call the head agent's model to extract sub-tasks."""
        from backend.services.model_provider import ModelService

        svc = ModelService()
        raw: str = await svc.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_message=message,
            max_tokens=1024,
        )
        # Strip optional markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("LLM response is not a JSON array")

        return [
            SubTaskSpec(
                intent=item["intent"],
                params=item.get("params", {}),
                depends_on=item.get("depends_on", []),
                schedule_offset_days=int(item.get("schedule_offset_days", 0)),
            )
            for item in items
        ]

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_based_parse(self, message: str) -> List[SubTaskSpec]:
        """
        Keyword-based parser. Covers the HDFC scenario and most common
        combinations without any LLM dependency.
        """
        msg_lower = message.lower()
        subtasks: List[SubTaskSpec] = []

        # ── T1: Fetch stock price ─────────────────────────────────────────
        stock_kw = ["price", "stock", "share", "nse", "bse", "market",
                    "hdfc", "reliance", "tcs", "infy", "sensex", "nifty"]
        if any(kw in msg_lower for kw in stock_kw):
            ticker = self._extract_ticker(message)
            subtasks.append(SubTaskSpec(
                intent="fetch_stock_price",
                params={"ticker": ticker},
                depends_on=[],
            ))

        # ── T2: Send email ────────────────────────────────────────────────
        email_kw = ["email", "mail", "send", "broker", "forward", "notify"]
        if any(kw in msg_lower for kw in email_kw):
            stock_done = any(s.intent == "fetch_stock_price" for s in subtasks)
            subtasks.append(SubTaskSpec(
                intent="send_email",
                params={
                    "to": "",                         # resolved from preferences at runtime
                    "subject": "Stock Price Update",
                    "body_template": "Current price: {{fetch_stock_price.display}}",
                    "inject_from": "fetch_stock_price",
                },
                depends_on=["fetch_stock_price"] if stock_done else [],
            ))

        # ── T3: Immediate reminder ────────────────────────────────────────
        reminder_kw = ["remind", "reminder", "alert", "alarm", "notify me"]
        if any(kw in msg_lower for kw in reminder_kw):
            prev = subtasks[-1].intent if subtasks else None
            subtasks.append(SubTaskSpec(
                intent="create_reminder",
                params={"message": message, "delay_seconds": 0},
                depends_on=[prev] if prev else [],
            ))

        # ── T4: Deferred follow-up ────────────────────────────────────────
        followup_kw = [
            "2 week", "two week", "fortnight", "14 day", "after 2",
            "follow up", "followup", "follow-up", "remind again",
        ]
        if any(kw in msg_lower for kw in followup_kw):
            prev = subtasks[-1].intent if subtasks else None
            subtasks.append(SubTaskSpec(
                intent="schedule_followup",
                params={
                    "message": f"Follow-up: {message}",
                    "delay_seconds": 14 * 24 * 3600,
                },
                depends_on=[prev] if prev else [],
                schedule_offset_days=14,
            ))

        # ── Fallback: treat the whole message as a generic task ───────────
        if not subtasks:
            subtasks.append(SubTaskSpec(
                intent="generic_task",
                params={"message": message},
                depends_on=[],
            ))

        return subtasks

    @staticmethod
    def _extract_ticker(message: str) -> str:
        """Guess NSE ticker from message text."""
        _KNOWN = {
            "HDFC": "HDFCBANK.NS",
            "RELIANCE": "RELIANCE.NS",
            "TCS": "TCS.NS",
            "INFY": "INFY.NS",
            "WIPRO": "WIPRO.NS",
            "ICICI": "ICICIBANK.NS",
            "SBIN": "SBIN.NS",
        }
        for word in message.upper().split():
            clean = word.strip(".,!?")
            if clean in _KNOWN:
                return _KNOWN[clean]
        # Default to HDFC Bank if nothing matches
        return "HDFCBANK.NS"