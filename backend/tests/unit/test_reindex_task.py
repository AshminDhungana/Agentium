"""Task 14 — weekly reindex job targets the active (v2) embedding version."""
from unittest.mock import patch, MagicMock

import backend.services.tasks.reindex_knowledge as reindex_knowledge


def test_weekly_reindex_targets_v2(monkeypatch):
    monkeypatch.setattr(reindex_knowledge, "REINDEX_VERSIONS", ["v2"])

    fake_stat = {"key": "constitution", "count": 3, "metadata_mismatch": 0}

    def _fake_reindex(key, version):
        return {"key": key, "count": 3, "metadata_mismatch": 0}

    with patch.object(reindex_knowledge, "reindex_collection", side_effect=_fake_reindex):
        stats = reindex_knowledge.weekly_reindex()

    assert stats, "expected at least one collection reindexed"
    assert all(s["version"] == "v2" for s in stats)
    # The v2 constitution collection (Constitutional Guard source) is covered.
    assert any(s["key"] == "constitution" for s in stats)


def test_weekly_reindex_skips_retired_v1(monkeypatch):
    monkeypatch.setattr(reindex_knowledge, "REINDEX_VERSIONS", ["v1", "v2"])
    called = []
    with patch.object(reindex_knowledge, "reindex_collection",
                      side_effect=lambda k, v: called.append((k, v)) or {"key": k, "count": 0}):
        reindex_knowledge.weekly_reindex()
    # v1 of retired collections must not be reindexed.
    retired_v1 = [(k, v) for k, v in called if v == "v1" and k in reindex_knowledge._RETIRE_V1]
    assert not retired_v1
    # v2 runs for every collection.
    v2_keys = {k for k, v in called if v == "v2"}
    assert v2_keys == set(reindex_knowledge._REINDEX_KEYS)
    # v1 only runs for collections NOT scheduled for deletion.
    v1_keys = {k for k, v in called if v == "v1"}
    assert v1_keys.isdisjoint(reindex_knowledge._RETIRE_V1)
