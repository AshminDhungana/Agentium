"""
Token-efficient chat context for the Sovereign <-> Head-of-Council chat.

Implements Task 2.1 (P1): reduce tokens sent to the model each turn by

  1. Sliding window  — send only the last N turns, always pinning the system
     prompt (handled by the caller) and the first user message (original intent).
  2. Background summarization — turns outside the window are condensed into a
     structured memo (key facts / decisions / open threads) by a cheap model
     and stored in Redis, then injected into the system prompt prefix.
  3. On-demand full-history retrieval — the agent can call ``get_full_history``
     / ``search_chat_history`` tools when the window + summary are insufficient.
  4. Cost/latency efficiency — token estimation before each call, prompt caching
     on the stable prefix (see model_provider wiring), and graceful truncation.

All of this is scoped to the chat path; agentic task execution is untouched.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.entities.chat_message import ChatMessage as ChatMsg

logger = logging.getLogger(__name__)

# DB role -> OpenAI-style role
_ROLE_MAP = {"sovereign": "user", "head_of_council": "assistant"}

# Redis key prefix for the rolling conversation summary (per sovereign user).
_SUMMARY_KEY_PREFIX = "agentium:chat_summary:"

# Per-request chat context for the full-history tools. The chat tool executor
# runs in a worker thread (via run_in_executor), so a ContextVar would not
# propagate; a module-level holder shared across threads is used instead.
# Chat is user-driven and effectively serial, so the race window is negligible.
_CHAT_REQUEST: Dict[str, Any] = {}


def set_chat_request(*, user_id: str, db: Session) -> None:
    """Bind the current sovereign user + DB session for the chat tools."""
    _CHAT_REQUEST["user_id"] = user_id
    _CHAT_REQUEST["db"] = db


def clear_chat_request() -> None:
    """Clear the per-request chat context after a turn completes."""
    _CHAT_REQUEST.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Token estimation
# ═══════════════════════════════════════════════════════════════════════════

def estimate_tokens(messages: List[Dict[str, str]], system_prompt: str = "") -> int:
    """Estimate the token count of a (system + messages) payload.

    Uses ``tiktoken`` when importable (accurate for the cl100k family);
    otherwise falls back to a chars/4 heuristic plus per-message role overhead.
    Conservative enough for pre-call truncation decisions without adding a
    network round-trip to a token-counting API.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        text = system_prompt + "\n"
        for m in messages:
            text += f"\n{m.get('role', 'user')}: {m.get('content', '')}"
        return len(enc.encode(text))
    except Exception:
        chars = len(system_prompt)
        for m in messages:
            chars += len(m.get("content", "")) + 8  # role/structural overhead
        return max(1, chars // 4)


# ═══════════════════════════════════════════════════════════════════════════
# Context builder (sliding window + pinning + graceful truncation)
# ═══════════════════════════════════════════════════════════════════════════

class ChatContextBuilder:
    """Build a compact, model-ready message list from raw chat history."""

    def __init__(self, window_size: int = 10, model_limit: int = 128_000):
        self.window_size = max(1, int(window_size))
        self.model_limit = int(model_limit)

    def _load_raw(self, db: Session, user_id: str) -> List[Dict[str, str]]:
        rows = (
            db.query(ChatMsg)
            .filter(ChatMsg.user_id == user_id, ChatMsg.is_deleted == "N")
            .filter(ChatMsg.role.in_(["sovereign", "head_of_council"]))
            .order_by(ChatMsg.created_at.asc())
            .all()
        )
        out: List[Dict[str, str]] = []
        for r in rows:
            mapped = _ROLE_MAP.get(r.role)
            if mapped and r.content and r.content.strip():
                out.append({"role": mapped, "content": r.content})
        return out

    def build(
        self,
        db: Session,
        user_id: str,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a compacted history (excluding the current turn).

        Returns a dict with:
            history:             List[Dict] (user/assistant only) ready to seed
                                 the model; the caller appends the current turn.
            context_compressed:  True if the window was applied or a summary used.
            estimated_tokens:    Token estimate of (summary + history) without
                                 the system prompt or current turn.
            raw_turn_count:      Total turns loaded from the DB (for benchmarking).
        """
        raw = self._load_raw(db, user_id)
        raw_turn_count = len(raw)

        compressed = bool(summary)
        first_msg: Optional[Dict[str, str]] = raw[0] if raw else None

        # Recent window = last `window_size` turns.
        recent = raw[-self.window_size:] if raw else []

        history: List[Dict[str, str]] = []
        pinned_idx: Optional[int] = None
        summary_idx: Optional[int] = None

        # 1) Rolling summary lives in the system prefix (handled by caller); we
        #    still flag compression when a summary is present.
        # 2) Pin the first user message (original intent) unless it is already
        #    the head of the recent window (short conversations).
        if first_msg is not None and (not recent or recent[0] is not first_msg):
            if len(raw) > self.window_size + 1:
                compressed = True
            history.append(first_msg)
            pinned_idx = len(history) - 1

        # 3) Recent window.
        history.extend(recent)

        # 4) Graceful truncation if the (summary + history) estimate overflows.
        if summary:
            summary_idx = 0  # summary is injected into the system prompt by caller
        if estimate_tokens(history, summary or "") > self.model_limit:
            history, compressed = self._truncate(
                history, summary, pinned_idx, self.model_limit
            )

        return {
            "history": history,
            "context_compressed": compressed,
            "estimated_tokens": estimate_tokens(history, summary or ""),
            "raw_turn_count": raw_turn_count,
        }

    @staticmethod
    def _truncate(
        history: List[Dict[str, str]],
        summary: Optional[str],
        pinned_idx: Optional[int],
        limit: int,
    ) -> tuple:
        """Drop oldest non-pinned turns until under the limit.

        Never drops the pinned first message or (conceptually) the summary,
        which the caller injects into the system prompt. The final message is
        the current turn and is added later, so we only protect the pinned idx.
        """
        compressed = True
        while estimate_tokens(history, summary or "") > limit and len(history) > 1:
            drop = None
            for i in range(len(history)):
                if i == pinned_idx:
                    continue
                drop = i
                break
            if drop is None:
                break
            history = history[:drop] + history[drop + 1:]
        return history, compressed


# ═══════════════════════════════════════════════════════════════════════════
# Background summarization (async, stored in Redis)
# ═══════════════════════════════════════════════════════════════════════════

_SUMMARY_SYSTEM = (
    "You condense a chat transcript into a compact structured memory. "
    "Reply with ONLY valid JSON of the form:\n"
    '{"key_facts":[...],"decisions":[...],"open_threads":[...]}\n'
    "Keep entries short. Preserve the user's original intent, proper names, "
    "and any explicit instructions or commitments."
)


async def load_summary(user_id: str) -> Optional[str]:
    """Load the rolling summary string for a user from Redis (None if absent)."""
    try:
        from backend.core.redis import get_redis_client

        r = await get_redis_client()
        raw = await r.get(_SUMMARY_KEY_PREFIX + user_id)
        return raw
    except Exception as exc:  # pragma: no cover - redis optional
        logger.debug("Chat summary load failed (non-fatal): %s", exc)
        return None


async def save_summary(user_id: str, summary: str) -> None:
    """Persist the rolling summary for a user in Redis (7-day TTL)."""
    try:
        from backend.core.redis import get_redis_client

        r = await get_redis_client()
        await r.set(_SUMMARY_KEY_PREFIX + user_id, summary, ex=60 * 60 * 24 * 7)
    except Exception as exc:  # pragma: no cover - redis optional
        logger.debug("Chat summary save failed (non-fatal): %s", exc)


async def summarize_history(
    db: Session,
    user_id: str,
    model_config_id: Optional[str],
) -> Optional[str]:
    """Summarize the full chat history into a structured memo (async-safe).

    Runs a cheap model and overwrites the rolling Redis summary. Returns the
    new summary string, or None if summarization could not be performed.

    Opens its own DB session from the caller's engine binding, because this is
    typically invoked as a fire-and-forget background task after the request
    session has been closed.
    """
    from sqlalchemy.orm import Session as OrmSession
    from backend.services.model_provider import ModelService

    # Open an independent session so the background task is not coupled to the
    # request-scoped session lifetime.
    own_session = False
    try:
        bind = db.get_bind()
        sdb: Session = OrmSession(bind)
        own_session = True
    except Exception:
        sdb = db

    try:
        rows = (
            sdb.query(ChatMsg)
            .filter(ChatMsg.user_id == user_id, ChatMsg.is_deleted == "N")
            .filter(ChatMsg.role.in_(["sovereign", "head_of_council"]))
            .order_by(ChatMsg.created_at.asc())
            .all()
        )
        if len(rows) < 6:
            return None

        transcript = "\n".join(
            f"{_ROLE_MAP.get(r.role, r.role)}: {r.content}" for r in rows if r.content
        )
        if not transcript.strip():
            return None

        provider = await ModelService.get_provider("sovereign", model_config_id)
        if not provider:
            return None

        result = await provider.generate(
            system_prompt=_SUMMARY_SYSTEM,
            user_message=transcript[:12000],
            max_tokens=600,
        )
        text = (result.get("content") or "").strip()
        if not text:
            return None
        # Validate it is JSON-ish; if the model wrapped it, extract the object.
        parsed = _extract_json_object(text)
        if parsed is None:
            return None
        summary = json.dumps(parsed, ensure_ascii=False)
        await save_summary(user_id, summary)
        return summary
    except Exception as exc:  # pragma: no cover - provider-dependent
        logger.warning("Chat history summarization failed (non-fatal): %s", exc)
        return None
    finally:
        if own_session:
            try:
                sdb.close()
            except Exception:
                pass


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from a model response."""
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def format_summary_for_prompt(summary_json: str) -> str:
    """Render the stored summary JSON into a compact human-readable block."""
    try:
        data = json.loads(summary_json)
    except Exception:
        return summary_json
    parts: List[str] = []
    for key, label in (
        ("key_facts", "Key facts"),
        ("decisions", "Decisions"),
        ("open_threads", "Open threads"),
    ):
        items = data.get(key) or []
        if items:
            parts.append(f"{label}: " + "; ".join(str(i) for i in items))
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# On-demand full-history tools (registered in tool_registry)
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_chat_rows(db: Session, limit: int, query: Optional[str] = None):
    user_id = _CHAT_REQUEST.get("user_id")
    if not user_id:
        return []
    q = (
        db.query(ChatMsg)
        .filter(ChatMsg.user_id == user_id, ChatMsg.is_deleted == "N")
        .filter(ChatMsg.role.in_(["sovereign", "head_of_council"]))
        .order_by(ChatMsg.created_at.desc())
    )
    if query:
        q = q.filter(ChatMsg.content.ilike(f"%{query}%"))
    rows = q.limit(limit).all()
    # Return oldest-first so the agent reads chronologically.
    rows = list(reversed(rows))
    seen = set()
    out = []
    for r in rows:
        mapped = _ROLE_MAP.get(r.role)
        if not mapped or not r.content:
            continue
        key = (mapped, r.content)
        if key in seen:
            continue
        seen.add(key)
        out.append({"role": mapped, "content": r.content})
    return out


def get_full_history(limit: int = 50, db_session=None) -> Dict[str, Any]:
    """Tool: return the full (deduped, chronological) chat history."""
    db = db_session or _CHAT_REQUEST.get("db")
    if db is None:
        return {"status": "error", "error": "no_db_session"}
    rows = _fetch_chat_rows(db, int(limit), None)
    return {
        "status": "ok",
        "message_count": len(rows),
        "history": rows,
    }


def search_chat_history(query: str, limit: int = 20, db_session=None) -> Dict[str, Any]:
    """Tool: search past chat turns containing ``query``."""
    db = db_session or _CHAT_REQUEST.get("db")
    if db is None:
        return {"status": "error", "error": "no_db_session"}
    if not query or not query.strip():
        return {"status": "error", "error": "empty_query"}
    rows = _fetch_chat_rows(db, int(limit), query.strip())
    return {
        "status": "ok",
        "query": query,
        "message_count": len(rows),
        "history": rows,
    }
