"""
Backfill chunked parent-document storage for existing ChromaDB knowledge.

Historically, documents were stored as a single ChromaDB entry whose text was
silently truncated to the embedding window.  ``VectorStore.upsert_document``
now keeps the untruncated text in PostgreSQL (``knowledge_documents``) and
stores chunk vectors in ChromaDB.  This script migrates every *legacy*
standalone document (one without a ``parent_id`` / ``is_chunk`` marker) into
the new store so retrieval serves the full, untruncated text.

Run with::

    python backend/scripts/backfill_knowledge_chunks.py [--collection KEY]

or via Make::

    make backfill-knowledge
"""

from __future__ import annotations

import argparse
import logging

from backend.core.vector_store import get_vector_store
from backend.models.database import SessionLocal

logger = logging.getLogger(__name__)

# Batch size for ChromaDB .get() paging.
_BATCH = 1000


def backfill_collection(vs, db, collection_key: str) -> int:
    """Migrate all legacy standalone docs in *collection_key* to the parent store.

    Returns the number of documents migrated.
    """
    collection = vs.get_collection(collection_key)
    migrated = 0
    offset = None

    while True:
        kwargs = {"include": ["documents", "metadatas"], "limit": _BATCH}
        if offset is not None:
            kwargs["offset"] = offset
        page = collection.get(**kwargs)
        ids = page.get("ids") or []
        if not ids:
            break

        docs = page.get("documents") or []
        metas = page.get("metadatas") or []

        for doc_id, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            # Skip documents already managed by the chunk store.
            if meta.get("is_chunk") or meta.get("parent_id"):
                continue
            if not doc or not doc.strip():
                continue
            # Persist full text in Postgres + chunked vectors in ChromaDB.
            vs.upsert_document(collection_key, doc_id, doc, meta, db)
            # Remove the now-redundant legacy standalone vector.
            try:
                collection.delete(ids=[doc_id])
            except Exception:  # noqa: BLE001
                logger.debug("Could not delete legacy doc %s", doc_id)
            migrated += 1

        if len(ids) < _BATCH:
            break
        offset = (offset or 0) + len(ids)

    logger.info("Backfilled %d legacy docs in '%s'", migrated, collection_key)
    return migrated


def backfill_all(vs, db) -> int:
    total = 0
    for key in vs.COLLECTIONS:
        total += backfill_collection(vs, db, key)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        default=None,
        help="Backfill only this collection key (default: all).",
    )
    args = parser.parse_args()

    vs = get_vector_store()
    db = SessionLocal()
    try:
        if args.collection:
            n = backfill_collection(vs, db, args.collection)
        else:
            n = backfill_all(vs, db)
        logger.info("Backfill complete: %d documents migrated.", n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
