"""ChromaDB Vector-Query Benchmark - Phase 18.2 Performance Regression Gate.

Asserts: p95 < 200 ms for ``query_knowledge()`` with 10,000 seeded documents.

Usage::

    pytest tests/benchmarks/test_chroma_query.py -m benchmark --benchmark-only

Dependencies
------------
pytest-benchmark (installed via ``pip install -r requirements-dev.txt``)
"""

from __future__ import annotations

import time
import statistics
import pytest

# Target threshold (ms) – Phase 8 baseline
_THRESHOLD_MS = 200

# Number of documents to seed
_SEED_COUNT = 10000

# Number of benchmarked measurement queries
_MEASURE = 100

pytestmark = [
    pytest.mark.slow,
    pytest.mark.benchmark,
]


def _seed_collection(vector_store):
    """Seed 10,000 synthetic documents in batches."""
    collection_key = "task_patterns"
    batch_size = 500
    for batch_start in range(0, _SEED_COUNT, batch_size):
        batch_end = min(batch_start + batch_size, _SEED_COUNT)
        texts = [
            f"Synthetic document {i}: "
            f"The quick brown fox jumps over the lazy dog. "
            f"Document number {i} used for ChromaDB performance benchmarking."
            for i in range(batch_start, batch_end)
        ]
        metadatas = [
            {"agent_id": f"agent-{i % 100}", "source": "benchmark", "index": i}
            for i in range(batch_start, batch_end)
        ]
        ids = [f"bench-{i}" for i in range(batch_start, batch_end)]
        vector_store.add_documents(
            collection_key=collection_key,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
    return collection_key


def _warmup_queries(vector_store, collection_key, n=10):
    """Discard warm-up queries to prime caches."""
    for i in range(n):
        vector_store.query_knowledge(
            f"What is the content of document {i}?",
            collection_keys=[collection_key],
            n_results=5,
        )


def test_chroma_query_p95(benchmark, vector_store):
    """Seed 10,000 docs, run 100 queries, assert p95 < 200 ms."""
    collection_key = _seed_collection(vector_store)
    _warmup_queries(vector_store, collection_key)

    # Run the benchmark and capture per-query timings
    results_ms = []

    def _run_queries():
        for i in range(_MEASURE):
            start = time.perf_counter()
            vector_store.query_knowledge(
                f"What is the content of synthetic document {i % _SEED_COUNT}?",
                collection_keys=[collection_key],
                n_results=5,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            results_ms.append(elapsed_ms)

    # pytest-benchmark drives the timing loop
    benchmark(_run_queries)

    # Compute p95
    if len(results_ms) < 2:  # pragma: no cover
        pytest.skip("Not enough samples collected for p95 computation")

    sorted_results = sorted(results_ms)
    p95_idx = int((len(sorted_results) - 1) * 0.95)
    p95_ms = sorted_results[p95_idx]

    # pytest-benchmark stores the total wall-clock; log it for CI
    total_wall = sum(results_ms)
    mean_ms = statistics.mean(results_ms)

    pytest._tmp = {  # type: ignore[attr-defined]
        "p95_ms": p95_ms,
        "mean_ms": mean_ms,
        "total_ms": total_wall,
    }

    assert p95_ms < _THRESHOLD_MS, (
        f"p95 {p95_ms:.2f} ms >= threshold {_THRESHOLD_MS} ms "
        f"(mean={mean_ms:.2f}ms, n={len(results_ms)})"
    )
