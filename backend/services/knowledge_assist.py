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
import uuid
from dataclasses import dataclass
from datetime import datetime
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


def _normalize_query(q: str) -> str:
    return " ".join((q or "").lower().split())


def _parent_id_for_query(q: str) -> str:
    digest = hashlib.sha256(_normalize_query(q).encode("utf-8")).hexdigest()[:16]
    return f"web:{digest}"


def _top_distance(chroma: Optional[Dict[str, Any]]) -> Optional[float]:
    if not chroma or not chroma.get("ids") or not chroma["ids"][0]:
        return None
    dists = chroma.get("distances")
    if not dists or not dists[0]:
        return None
    return float(dists[0][0])


def _synthesize_web_doc(query: str, results: List[Dict[str, Any]], k: int = 3) -> str:
    lines = [f"Web search results for: {query}", ""]
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
        doc = chroma.get("documents", [[]])[0][i] if chroma.get("documents") else ""
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
    now = datetime.utcnow().isoformat()
    meta = dict(metadata or {})
    meta["parent_id"] = parent_id
    meta.setdefault("type", "agent_learning")
    meta.setdefault("source", "agent")
    meta.setdefault("document_type", meta["type"])
    meta.setdefault("decay_score", 1.0)
    meta.setdefault("citation_boost", 1.0)

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
    chroma = store.query_knowledge(query, collection_keys=keys, n_results=5, db=db)

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
                chroma = store.query_knowledge(query, collection_keys=keys, n_results=5, db=db)
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
