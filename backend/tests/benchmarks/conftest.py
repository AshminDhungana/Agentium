"""Conftest for benchmark tests.

Provides the ``vector_store`` fixture required by
``test_chroma_query.py``.  This conftest is only used when running the
benchmarks in isolation (e.g. the ``performance-tests`` CI job).
"""

from __future__ import annotations

import os
import pytest

from backend.core.vector_store import VectorStore


@pytest.fixture(scope="function")
def vector_store():
    """Provide a clean ChromaDB instance for benchmarking."""
    vs = VectorStore(
        host=os.environ.get("CHROMA_HOST", "localhost"),
        port=int(os.environ.get("CHROMA_PORT", "8001")),
    )

    # Prefix collection names so benchmark data is isolated from production.
    original_names = vs.COLLECTIONS.copy()
    for key in list(vs.COLLECTIONS.keys()):
        vs.COLLECTIONS[key] = f"bench_{vs.COLLECTIONS[key]}"
    # Also prefix the v2 (bge) collection names for the same isolation.
    original_names_v2 = vs.COLLECTIONS_V2.copy()
    for key in list(vs.COLLECTIONS_V2.keys()):
        vs.COLLECTIONS_V2[key] = f"bench_{vs.COLLECTIONS_V2[key]}"

    # Delete stale collections *before* initialize() so cached Collection
    # objects always point at live server UUIDs.
    for coll_name in vs.COLLECTIONS.values():
        try:
            vs.client.delete_collection(name=coll_name)
        except Exception:
            pass

    vs._client = None
    vs._collections = {}
    vs.initialize()

    yield vs

    # Teardown: remove benchmark collections.
    for coll_name in vs.COLLECTIONS.values():
        try:
            vs.client.delete_collection(name=coll_name)
        except Exception:
            pass
    for coll_name in vs.COLLECTIONS_V2.values():
        try:
            vs.client.delete_collection(name=coll_name)
        except Exception:
            pass

    vs.COLLECTIONS.update(original_names)
    vs.COLLECTIONS_V2.update(original_names_v2)
