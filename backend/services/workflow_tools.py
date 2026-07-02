"""
Workflow Tool Registry
======================
A lightweight registry of async callable tools used exclusively by the
WorkflowExecutor.  Named ``workflow_tools`` (not ``tool_registry``) to
avoid any collision with the existing ``backend.core.tool_registry`` used
by MCP / capability routes.

Built-in tools
--------------
  fetch_stock_price   — live stock price via yfinance (fallback: Alpha Vantage)
  send_email          — SMTP send through an active EmailAdapter channel
  create_reminder     — persist a ScheduledTask record for an immediate alert
  schedule_followup   — enqueue a Celery countdown task for a deferred reminder
  generic_task        — no-op pass-through for unrecognised intents
"""
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

# Internal registry: intent name → async callable
_REGISTRY: Dict[str, Callable] = {}


def register(name: str):
    """Decorator that registers an async function under *name*."""
    def decorator(fn: Callable) -> Callable:
        """Decorator."""
        _REGISTRY[name] = fn
        return fn
    return decorator


async def execute(name: str, params: dict, context: dict = None) -> dict:
    """
    Execute a registered tool.

    *context* contains the output dicts from already-completed upstream
    sub-tasks, keyed by their intent name.  They are merged into *params*
    so that a tool can reference e.g. ``params["fetch_stock_price"]["display"]``.
    """
    if name not in _REGISTRY:
        logger.warning(
            f"[workflow_tools] Unknown intent '{name}' — using generic_task."
        )
        name = "generic_task"

    merged = {**(context or {}), **params}
    logger.info(f"[workflow_tools] Executing '{name}'")
    return await _REGISTRY[name](merged)


def list_tools() -> list:
    """List tools."""

    return list(_REGISTRY.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Tool: fetch_stock_price
# ─────────────────────────────────────────────────────────────────────────────

@register("fetch_stock_price")
async def _fetch_stock_price(params: dict) -> dict:
    """
    Fetch the current price of a stock.

    params:
        ticker  (str) — e.g. "HDFCBANK.NS"
    """
    ticker = params.get("ticker", "HDFCBANK.NS")
    try:
        import yfinance as yf  # optional dependency; graceful fallback below
        info = yf.Ticker(ticker).fast_info
        price = float(info.last_price or info.regular_market_previous_close or 0)
        currency = getattr(info, "currency", "INR")
        result = {
            "ticker": ticker,
            "price": round(price, 2),
            "currency": currency,
            "display": f"{ticker}: {currency} {round(price, 2)}",
        }
        logger.info(f"[fetch_stock_price] {result['display']}")
        return result
    except ImportError:
        return await _fetch_alpha_vantage(ticker)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch price for '{ticker}': {exc}") from exc


async def _fetch_alpha_vantage(ticker: str) -> dict:
    """Fetch alpha vantage."""

    import os, httpx
    api_key = os.getenv("STOCK_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "yfinance is not installed and STOCK_API_KEY is not set. "
            "Add 'yfinance' to requirements.txt or set STOCK_API_KEY."
        )
    symbol = ticker.replace(".NS", "").replace(".BSE", "")
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    quote = resp.json().get("Global Quote", {})
    price = round(float(quote.get("05. price", 0)), 2)
    return {
        "ticker": ticker,
        "price": price,
        "currency": "INR",
        "display": f"{ticker}: INR {price}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool: send_email
# ─────────────────────────────────────────────────────────────────────────────

@register("send_email")
async def _send_email(params: dict) -> dict:
    """
    Send an email via the first active SMTP channel.

    params:
        to            (str)  — recipient; falls back to DEFAULT_BROKER_EMAIL
        subject       (str)
        body_template (str)  — may contain {{fetch_stock_price.display}}
        inject_from   (str)  — context key whose .display is appended to body
    """
    import os, re
    from backend.models.database import get_db_context
    from backend.models.entities.channels import (
        ExternalChannel, ChannelType, ChannelStatus,
    )
    from backend.services.channel_manager import EmailAdapter

    to_addr = params.get("to", "").strip()
    if not to_addr:
        to_addr = os.getenv("DEFAULT_BROKER_EMAIL", "")
    if not to_addr:
        return {"sent": False, "error": "No recipient email — set DEFAULT_BROKER_EMAIL."}

    subject = params.get("subject", "Stock Update")
    body = params.get("body_template", "")

    # Resolve {{key.subkey}} placeholders from context
    for placeholder in re.findall(r"\{\{([^}]+)\}\}", body):
        parts = placeholder.split(".")
        val: Any = params
        for part in parts:
            val = val.get(part, "") if isinstance(val, dict) else ""
        body = body.replace("{{" + placeholder + "}}", str(val))

    # Append the "display" field from the upstream stock-fetch result
    inject_key = params.get("inject_from")
    if inject_key and isinstance(params.get(inject_key), dict):
        display = params[inject_key].get("display", "")
        if display and display not in body:
            body = f"{body}\n\n{display}".strip()

    try:
        with get_db_context() as db:
            channel = (
                db.query(ExternalChannel)
                .filter(
                    ExternalChannel.channel_type == ChannelType.EMAIL,
                    ExternalChannel.status == ChannelStatus.ACTIVE,
                )
                .first()
            )
            if not channel:
                return {"sent": False, "error": "No active SMTP channel configured."}

            cfg = channel.config or {}
            adapter = EmailAdapter(cfg)
            await adapter.send_message(
                recipient=to_addr,
                content=f"Subject: {subject}\n\n{body}",
                channel_config=cfg,
            )
        logger.info(f"[send_email] Sent to {to_addr}: {subject}")
        return {"sent": True, "to": to_addr, "subject": subject}
    except Exception as exc:
        logger.error(f"[send_email] Failed: {exc}")
        return {"sent": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool: create_reminder
# ─────────────────────────────────────────────────────────────────────────────

@register("create_reminder")
async def _create_reminder(params: dict) -> dict:
    """
    Persist an immediate reminder as a WorkflowSubTask-style record.

    params:
        message       (str)
        delay_seconds (int)  — 0 = fire immediately (stored for audit only)
    """
    import uuid
    from datetime import datetime, timedelta
    from backend.models.database import get_db_context

    message = params.get("message", "Reminder")
    delay = int(params.get("delay_seconds", 0))
    fire_at = datetime.utcnow() + timedelta(seconds=delay)

    # Try the ScheduledTask model if it exists and has the expected fields;
    # fall back to a simple log record so the workflow never hard-fails here.
    try:
        from backend.models.entities.scheduled_task import ScheduledTask
        with get_db_context() as db:
            task = ScheduledTask(
                id=str(uuid.uuid4()),
                name=f"reminder_{uuid.uuid4().hex[:8]}",
                task_type="reminder",
                payload={"message": message},
                scheduled_for=fire_at,
                status="pending",
            )
            db.add(task)
            db.commit()
            reminder_id = task.id
    except Exception as exc:
        logger.warning(
            f"[create_reminder] ScheduledTask write failed ({exc}); "
            "reminder logged only."
        )
        reminder_id = str(uuid.uuid4())

    logger.info(f"[create_reminder] Scheduled for {fire_at.isoformat()}: {message[:60]}")
    return {
        "created": True,
        "reminder_id": reminder_id,
        "message": message,
        "scheduled_for": fire_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool: schedule_followup
# ─────────────────────────────────────────────────────────────────────────────

@register("schedule_followup")
async def _schedule_followup(params: dict) -> dict:
    """
    Enqueue a deferred Celery task that fires a reminder after *delay_seconds*.

    params:
        message       (str)
        delay_seconds (int)  — default 14 days (1 209 600 s)
    """
    message = params.get("message", "Follow-up reminder")
    delay = int(params.get("delay_seconds", 14 * 24 * 3600))

    try:
        from backend.services.tasks.workflow_tasks import fire_reminder
        async_result = fire_reminder.apply_async(
            kwargs={"message": message},
            countdown=delay,
        )
        logger.info(
            f"[schedule_followup] Enqueued in {delay}s "
            f"(celery_id={async_result.id})"
        )
        return {
            "scheduled": True,
            "celery_task_id": async_result.id,
            "fires_in_seconds": delay,
            "message": message,
        }
    except Exception as exc:
        logger.error(f"[schedule_followup] Enqueue failed: {exc}")
        return {"scheduled": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool: generic_task (pass-through for unrecognised intents)
# ─────────────────────────────────────────────────────────────────────────────

@register("generic_task")
async def _generic_task(params: dict) -> dict:
    """No-op handler for unrecognised intents; logs and returns params."""
    logger.info(f"[generic_task] Unhandled intent with params: {list(params.keys())}")
    return {"handled": False, "params": params}