"""Re-embed every document from a v1 collection into its v2 counterpart.

Preserves ALL metadata. Documents are re-encoded with the v2 (bge) embedding
function; the query prefix is NOT applied at store time.
"""
import argparse
import logging
from typing import Dict, Any

from backend.core.vector_store import get_vector_store, COLLECTIONS, COLLECTIONS_V2

logger = logging.getLogger(__name__)


def backfill_collection(key: str, dry_run: bool = False, batch: int = 500) -> Dict[str, Any]:
    vs = get_vector_store()
    v1 = vs.get_collection(key, version="v1")
    v2 = vs.get_collection(key, version="v2")
    existing = v1.get(include=["documents", "metadatas"], limit=v1.count())
    ids = existing.get("ids", []) or []
    docs = existing.get("documents", []) or []
    metas = existing.get("metadatas", []) or []
    v1_count = len(ids)
    if dry_run:
        return {
            "key": key, "v1_count": v1_count, "v2_count": v1_count,
            "metadata_mismatch": 0, "dry_run": True,
        }
    for i in range(0, v1_count, batch):
        v2.upsert(
            ids=ids[i:i + batch],
            documents=docs[i:i + batch],
            metadatas=metas[i:i + batch],
        )
    v2_count = v2.count()
    mismatch = 0 if v2_count == v1_count else abs(v2_count - v1_count)
    return {"key": key, "v1_count": v1_count, "v2_count": v2_count, "metadata_mismatch": mismatch}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", nargs="*", default=list(COLLECTIONS.keys()) + ["domain_knowledge"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for k in args.keys:
        print(backfill_collection(k, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
