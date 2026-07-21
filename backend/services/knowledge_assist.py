"""
knowledge_assist — the search-before-acting knowledge loop (6.5 + 6.6).

Owns two public coroutines:
  * retrieve_or_search() — query ChromaDB; if insufficient, web-search and
    write the result back; never block when web search is unavailable.
  * write_knowledge()    — the single funnel for ALL agent->ChromaDB writes,
    enforcing the shared 6.6 metadata schema with a deterministic dedup key.
"""
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from backend.tools.web_search_tool import web_search_tool  # noqa: E402

KNOWLEDGE_SUFFICIENCY_DISTANCE = 0.45
DEFAULT_RETRIEVAL_KEYS = [
    "web_knowledge",
    "domain_knowledge",
    "best_practices",
    "task_patterns",
]


@dataclass
class RetrievalOutcome:
    query: str
    chroma_results: Dict[str, Any]
    web_results: Optional[Dict[str, Any]]
    wrote_back: bool
    context_text: str
    fallback_used: bool


def enrich_knowledge_metadata(
    metadata: Optional[Dict[str, Any]],
    *,
    parent_id: Optional[str] = None,
    source: str = "agent",
    document_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    title: str = "",
) -> Dict[str, Any]:
    """
    Fill the 6.6 shared write schema defaults onto arbitrary metadata.

    Used by write paths that do NOT go through ``write_knowledge`` (e.g. the
    agent-learning pipeline's semantic revise-in-place logic) so that every
    agent write to ChromaDB still carries the full schema. ``parent_id`` is the
    dedup key and should be set to the call site's stable identifier.
    """
    meta = dict(metadata or {})
    if parent_id is not None:
        meta["parent_id"] = parent_id
    meta.setdefault("type", document_type or meta.get("document_type") or "agent_learning")
    meta.setdefault("source", source)
    meta.setdefault("source_url", "")
    meta.setdefault("title", title)
    # ChromaDB's metadata values must be strings/numbers/bools — never None.
    # Default to an empty string and coerce any provided value to str.
    resolved_agent_id = agent_id if agent_id is not None else meta.get("agent_id")
    meta["agent_id"] = "" if resolved_agent_id is None else str(resolved_agent_id)
    meta.setdefault("document_type", meta["type"])
    meta.setdefault("decay_score", 1.0)
    meta.setdefault("citation_boost", 1.0)
    return meta


def _normalize_query(q: str) -> str:
    return " ".join((q or "").lower().split())


def _parent_id_for_query(q: str) -> str:
    digest = hashlib.sha256(_normalize_query(q).encode("utf-8")).hexdigest()[:16]
    return f"web:{digest}"


def _top_distance(chroma: Optional[Dict[str, Any]]) -> Optional[float]:
    if not chroma or not chroma.get("ids") or not chroma["ids"][0]:
        return None
    eff = chroma.get("effective_distances")
    if eff and eff[0]:
        return float(eff[0][0])
    dists = chroma.get("distances")
    if not dists or not dists[0]:
        return None
    return float(dists[0][0])


def _synthesize_web_doc(query: str, results: List[Dict[str, Any]], k: int = 3,
                        heading: str = "Web search results for:") -> str:
    lines = [f"{heading} {query}", ""]
    for i, r in enumerate(results[:k], 1):
        title = r.get("title") or "(untitled)"
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        lines.append(f"{i}. {title} ({url})\n   {snippet}")
    return "\n".join(lines)


def _format_context(chroma: Optional[Dict[str, Any]]) -> str:
    if not chroma or not chroma.get("ids") or not chroma["ids"][0]:
        return ""
    out = []
    for i in range(len(chroma["ids"][0])):
        docs = chroma.get("documents", [[]])[0]
        if i >= len(docs):
            break
        doc = docs[i] if docs else ""
        if doc:
            out.append(doc)
    return "\n\n".join(out)


def get_vector_store():
    from backend.core.vector_store import get_vector_store as _gvs
    return _gvs()


async def write_knowledge(
    parent_id: str,
    text: str,
    metadata: Dict[str, Any],
    db: Any,
    collection_key: str = "web_knowledge",
) -> Dict[str, Any]:
    """Enforce the 6.6 write schema and upsert (dedup by parent_id)."""
    store = get_vector_store()
    now = datetime.now(timezone.utc).isoformat()
    meta = dict(metadata or {})
    meta["parent_id"] = parent_id
    meta.setdefault("type", "agent_learning")
    meta.setdefault("source", "agent")
    meta.setdefault("document_type", meta["type"])
    meta.setdefault("decay_score", 1.0)
    meta.setdefault("citation_boost", 1.0)
    meta.setdefault("source_url", "")
    meta.setdefault("title", "")
    meta.setdefault("agent_id", "")

    existing = store.get_parent_document(collection_key, parent_id, db)
    if existing and existing.get("metadata"):
        em = existing["metadata"]
        meta["created_at"] = em.get("created_at", now)
        meta["revision"] = int(em.get("revision", 0)) + 1
    else:
        meta["created_at"] = now
        meta["revision"] = 1
    meta["updated_at"] = now
    meta["revision_id"] = uuid.uuid4().hex
    return store.upsert_document(collection_key, parent_id, text, meta, db)


async def retrieve_or_search(
    query: str,
    agent: Any,
    db: Any,
    *,
    min_results: int = 3,
    collection_keys: Optional[List[str]] = None,
    sufficiency_distance: float = KNOWLEDGE_SUFFICIENCY_DISTANCE,
) -> RetrievalOutcome:
    store = get_vector_store()
    keys = collection_keys or DEFAULT_RETRIEVAL_KEYS
    chroma = store.query_knowledge(query, collection_keys=keys, n_results=max(5, min_results), db=db)

    wrote_back = False
    web_results: Optional[Dict[str, Any]] = None
    fallback_used = False

    top = _top_distance(chroma)
    if top is None or top > sufficiency_distance:
        try:
            web_results = await web_search_tool.execute(query=query, provider="auto")
            if web_results.get("status") == "success" and web_results.get("results"):
                doc = _synthesize_web_doc(query, web_results["results"])
                pid = _parent_id_for_query(query)
                await write_knowledge(
                    pid,
                    doc,
                    {
                        "type": "web_result",
                        "source": "web",
                        "source_url": web_results["results"][0].get("url"),
                        "title": web_results["results"][0].get("title"),
                        "agent_id": getattr(agent, "agentium_id", None),
                    },
                    db,
                    collection_key="web_knowledge",
                )
                wrote_back = True
                # refresh so the new doc is in the returned context
                chroma = store.query_knowledge(query, collection_keys=keys, n_results=max(5, min_results), db=db)
            elif web_results.get("status") != "success":
                logger.warning(
                    "retrieve_or_search: web search returned failure status: %s",
                    web_results.get("error"),
                )
                fallback_used = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieve_or_search: web search unavailable/failed: %s", exc)
            fallback_used = True

    return RetrievalOutcome(
        query=query,
        chroma_results=chroma,
        web_results=web_results,
        wrote_back=wrote_back,
        context_text=_format_context(chroma),
        fallback_used=fallback_used,
    )


CHECKPOINT_STAGES = ("received", "completed", "mid")


@dataclass
class CheckpointOutcome:
    stage: str
    queried_chroma: bool = False
    searched_web: bool = False
    wrote_back: bool = False
    fallback_used: bool = False
    parent_id: Optional[str] = None


_NEED_KNOWLEDGE_TAG = "<<NEED_KNOWLEDGE>>"


def _parent_id_for_checkpoint(stage: str, query: str) -> str:
    digest = hashlib.sha256(_normalize_query(query).encode("utf-8")).hexdigest()[:16]
    return f"ckpt:{stage}:{digest}"


def parse_knowledge_needed(text: str) -> Optional[str]:
    """Return the agent's stated gap query if ``<<NEED_KNOWLEDGE>>`` is present.

    The marker may be followed by a question on the same line, e.g.
    ``<<NEED_KNOWLEDGE>> how does X work?``. Returns None when absent.
    """
    m = re.search(re.escape(_NEED_KNOWLEDGE_TAG) + r"\s*(.*)", text)
    if not m:
        return None
    q = m.group(1).strip()
    return q or None


async def checkpoint_write(
    stage: str,
    task: Any,
    agent: Any,
    db: Any,
    *,
    query: Optional[str] = None,
) -> CheckpointOutcome:
    if stage not in CHECKPOINT_STAGES:
        raise ValueError(f"Unknown checkpoint stage: {stage!r}")
    store = get_vector_store()
    q = query or getattr(task, "description", "") or ""
    if not q:
        q = stage

    # 1. READ from ChromaDB (non-fatal)
    chroma_ctx = ""
    queried_chroma = False
    try:
        chroma = store.query_knowledge(
            q, collection_keys=DEFAULT_RETRIEVAL_KEYS, n_results=5, db=db
        )
        queried_chroma = True
        chroma_ctx = _format_context(chroma)
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint_write[%s]: ChromaDB query failed: %s", stage, exc)

    # 2. ALWAYS web-search (non-fatal)
    searched_web = False
    web_results: Optional[Dict[str, Any]] = None
    fallback_used = False
    try:
        web_results = await web_search_tool.execute(query=q, provider="auto")
        searched_web = True
        if web_results.get("status") != "success":
            fallback_used = True
            web_results = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint_write[%s]: web search unavailable: %s", stage, exc)
        fallback_used = True

    # 3 + 4. FOLD + WRITE (graceful)
    wrote_back = False
    parent_id: Optional[str] = None
    if web_results and web_results.get("results"):
        body = _synthesize_web_doc(q, web_results["results"],
                                   heading="Checkpoint web search for:")
        if chroma_ctx:
            body = chroma_ctx + "\n\n" + body
        parent_id = _parent_id_for_checkpoint(stage, q)
        try:
            await write_knowledge(
                parent_id,
                body,
                {
                    "type": "agent_learning",
                    "source": "agent",
                    "source_url": web_results["results"][0].get("url"),
                    "title": web_results["results"][0].get("title"),
                    "stage": stage,
                    "task_id": getattr(task, "agentium_id", None),
                    "agent_id": getattr(agent, "agentium_id", None),
                },
                db,
                collection_key="web_knowledge",
            )
            wrote_back = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_write[%s]: write-back failed: %s", stage, exc)
    elif chroma_ctx:
        # Web failed but we have Chroma context — still record the checkpoint.
        parent_id = _parent_id_for_checkpoint(stage, q)
        try:
            await write_knowledge(
                parent_id,
                chroma_ctx,
                {
                    "type": "agent_learning",
                    "source": "agent",
                    "stage": stage,
                    "task_id": getattr(task, "agentium_id", None),
                    "agent_id": getattr(agent, "agentium_id", None),
                },
                db,
                collection_key="web_knowledge",
            )
            wrote_back = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_write[%s]: chroma-only write failed: %s", stage, exc)
    else:
        # Neither Chroma nor web yielded content — still record the checkpoint
        # so every task shows the interaction (query + search) in the trace.
        parent_id = _parent_id_for_checkpoint(stage, q)
        try:
            await write_knowledge(
                parent_id,
                f"Checkpoint {stage}: no knowledge retrieved (query={q!r}).",
                {
                    "type": "agent_learning",
                    "source": "agent",
                    "stage": stage,
                    "task_id": getattr(task, "agentium_id", None),
                    "agent_id": getattr(agent, "agentium_id", None),
                    "empty": True,
                },
                db,
                collection_key="web_knowledge",
            )
            wrote_back = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_write[%s]: empty-marker write failed: %s", stage, exc)

    return CheckpointOutcome(
        stage=stage,
        queried_chroma=queried_chroma,
        searched_web=searched_web,
        wrote_back=wrote_back,
        fallback_used=fallback_used,
        parent_id=parent_id,
    )
