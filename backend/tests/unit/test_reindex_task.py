"""Task 14 — weekly reindex job targets the active (v2) embedding version."""
from unittest.mock import patch, MagicMock

import backend.services.tasks.reindex_knowledge as reindex_knowledge


def test_weekly_reindex_targets_v2(monkeypatch):
    monkeypatch.setattr(reindex_knowledge, "REINDEX_VERSIONS", ["v2"])

    fake_stat = {"key": "constitution", "count": 3, "metadata_mismatch": 0}

    def _fake_reindex(key, version="v2"):
        return {"key": key, "count": 3, "metadata_mismatch": 0}

    with patch.object(reindex_knowledge, "reindex_collection", side_effect=_fake_reindex):
        stats = reindex_knowledge.weekly_reindex()

    assert stats, "expected at least one collection reindexed"
    assert all(s["version"] == "v2" for s in stats)
    # The v2 constitution collection (Constitutional Guard source) is covered.
    assert any(s["key"] == "constitution" for s in stats)
