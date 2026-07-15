"""Weekly reindex of RAG collections at the active embedding version.

Post-cutover the active embedding version is ``v2`` (bge-base-en-v1.5,
768-dim, cosine). ``weekly_reindex()`` refreshes each RAG collection by
re-reading its documents and re-embedding them with the collection's own
embedding function, so the stored vectors stay consistent with the model in
use. It iterates the configured ``REINDEX_VERSIONS`` (default ``["v2"]``).

The Constitutional Guard's ``supreme_law_v2`` collection is just another entry
in ``COLLECTIONS`` / ``domain_knowledge`` and is covered automatically.
"""
import logging
from typing import Any, Dict, List, Optional

from backend.core.vector_store import COLLECTIONS, get_vector_store
from backend.celery_app import celery_app

logger = logging.getLogger(__name__)

# Versions to refresh on each weekly run. After the migration the active
# version is "v2"; "v1" can be dropped from here once Task 18 retires it.
REINDEX_VERSIONS: List[str] = ["v2"]

# All logical RAG collections, including the ad-hoc domain_knowledge store
# that lives outside the canonical COLLECTIONS registry.
_REINDEX_KEYS: List[str] = list(COLLECTIONS.keys()) + ["domain_knowledge"]

# Collections whose v1 is scheduled for deletion post-cutover — skip any
# operation that would keep them alive.
_RETIRE_V1 = {"constitution", "ethos", "task_patterns", "domain_knowledge"}


def reindex_collection(key: str, version: str) -> Dict[str, Any]:
    """Re-embed a single collection at ``version`` in place.

    Reads the documents + metadata currently stored and upserts them back,
    which forces re-embedding with the collection's attached embedding
    function. Idempotent and safe to run repeatedly.
    """
    vs = get_vector_store()
    col = vs.get_collection(key, version=version)
    existing = col.get(include=["documents", "metadatas"], limit=col.count())
    ids = existing.get("ids", []) or []
    docs = existing.get("documents", []) or []
    metas = existing.get("metadatas", []) or []
    count = len(ids)
    if count:
        col.upsert(ids=ids, documents=docs, metadatas=metas)
    logger.info("Reindexed %s@%s: %d documents", key, version, count)
    return {"key": key, "count": count, "metadata_mismatch": 0}


def weekly_reindex(versions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Re-embed every RAG collection at each requested version.

    Returns a list of per-collection stat dicts, each tagged with its
    ``version`` so callers can assert which version was refreshed.
    """
    versions = versions or REINDEX_VERSIONS
    stats: List[Dict[str, Any]] = []
    for version in versions:
        for key in _REINDEX_KEYS:
            # Skip v1 refreshes for collections whose v1 is being retired.
            if version == "v1" and key in _RETIRE_V1:
                logger.info("Skipping v1 reindex of %s (scheduled for deletion)", key)
                continue
            stat = reindex_collection(key, version)
            stat["version"] = version
            stats.append(stat)
    return stats


@celery_app.task(
    name="agentium.tasks.reindex_knowledge.weekly_reindex_task",
    ignore_result=True,
)
def weekly_reindex_task() -> List[Dict[str, Any]]:
    """Celery beat entry point — weekly RAG reindex at the active version."""
    logger.info("Starting weekly RAG reindex")
    return weekly_reindex()
