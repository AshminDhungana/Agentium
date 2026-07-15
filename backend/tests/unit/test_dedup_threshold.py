from sentence_transformers import SentenceTransformer


def _cosine_distance(a, b):
    return 1.0 - float((a * b).sum())


def test_dedup_threshold_evaluated_for_bge():
    m = SentenceTransformer("BAAI/bge-base-en-v1.5")
    dups = [
        ("the agent spawned a task", "the agent spawned a task"),
        ("rebuild the index weekly", "rebuild the vector index every week"),
    ]
    distinct = [
        ("the agent spawned a task", "a recipe for banana bread"),
        ("rebuild the index weekly", "the weather is sunny today"),
    ]
    dup_dists = [
        _cosine_distance(
            m.encode([a], normalize_embeddings=True)[0],
            m.encode([b], normalize_embeddings=True)[0],
        )
        for a, b in dups
    ]
    dist_dists = [
        _cosine_distance(
            m.encode([a], normalize_embeddings=True)[0],
            m.encode([b], normalize_embeddings=True)[0],
        )
        for a, b in distinct
    ]
    # Duplicates must be tight; use this to set the v2 cosine threshold.
    assert max(dup_dists) < 0.2, f"duplicate distances too loose: {dup_dists}"
    # Distinct pairs should be clearly looser than duplicates.
    assert min(dist_dists) > max(dup_dists), f"no separation: dups={dup_dists} distinct={dist_dists}"
