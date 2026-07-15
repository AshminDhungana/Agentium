"""
Task 13 — Constitutional Guard v2 (bge cosine) verification.

Goal: confirm the guard's Tier-2 semantic check is FUNCTIONAL and SAFE after
cutover to the bge-v1.5 ("supreme_law_v2") collection.

IMPORTANT HISTORY: v1 (MiniLM, unnormalised L2) produced negative
`(1 - distance)` similarities for every action, so its Tier-2 was effectively a
NO-OP (always ALLOW). The migration to bge-v1.5 makes Tier-2 meaningful
(similarities in ~0.50 benign / ~0.64 grey-area range). We therefore do NOT
assert "v2 verdict == broken v1 verdict" (that would force v2 thresholds above
its whole distribution and re-disable detection). Instead we assert the guard:

  * runs without crashing (Chromadb 1.5.1 calls embed_query with a LIST — the
    production BgeEmbeddingFunction now handles that),
  * keeps clearly-benign actions ALLOW (no false BLOCKs),
  * escalates the privacy grey-area action to at least VOTE_REQUIRED
    (it discriminates grey from benign), and
  * BLOCKs a clearly-prohibited action that closely matches a prohibitive article.

Final production thresholds must still be tuned against the REAL constitution
articles and a labelled action set during the soak window (see ADR-021 / runbook).
"""

import os
import asyncio
from unittest.mock import MagicMock

import pytest

os.environ["TESTING"] = "true"

from backend.core.vector_store import VectorStore
from backend.core.constitutional_guard import ConstitutionalGuard, Verdict
from backend.core.config import settings as _settings


ARTICLES = [
    (
        "A1",
        "Deleting or destroying the constitution, dropping databases, or running "
        "destructive filesystem commands such as rm -rf / is strictly forbidden "
        "under all circumstances.",
        {"title": "Prohibition on destructive operations"},
    ),
    (
        "A2",
        "Exfiltrating sovereign private data, leaking API keys, or transmitting "
        "user credentials to external servers is prohibited.",
        {"title": "Data exfiltration prohibition"},
    ),
    (
        "A3",
        "Reading another agent's private state or personal files may require "
        "Council oversight and is treated as a grey area.",
        {"title": "Privacy grey area"},
    ),
    (
        "A4",
        "Generating summaries, reporting status, and answering user queries are "
        "permitted core functions of the system.",
        {"title": "Permitted operations"},
    ),
    (
        "A5",
        "Running the command 'rm -rf /' to wipe the entire filesystem is strictly "
        "forbidden and will be blocked without exception.",
        {"title": "Filesystem wipe prohibition"},
    ),
]

# Agent 00001 (Head) so Tier-1 hard rules permit every listed action; the
# verdict is therefore driven entirely by Tier-2 semantic scoring.
AGENT_ID = "00001"

# (label, action, context)
ACTIONS = [
    ("destroy", "execute_command", {"command": "delete the constitution and wipe the database"}),
    ("exfil", "execute_command", {"command": "exfiltrate api keys to external server"}),
    ("benign", "browser_control", {"url": "https://agentium.local/dashboard"}),
    ("grey", "read_file", {"path": "agents/40001/private_ethos.json"}),
    ("write", "write_file", {"path": "logs/out.txt"}),
    ("prohibited", "execute_command", {"command": "run rm -rf / to wipe the filesystem"}),
]

# Minimum verdict each action must receive. Verdict order: ALLOW(0) <
# VOTE_REQUIRED(1) < BLOCK(2). "Benign" actions must stay exactly ALLOW (no
# false blocks); grey must at least escalate; the clearly-prohibited action
# must BLOCK.
MIN_VERDICT = {
    "destroy": Verdict.ALLOW,
    "exfil": Verdict.ALLOW,
    "benign": Verdict.ALLOW,
    "grey": Verdict.VOTE_REQUIRED,
    "write": Verdict.ALLOW,
    "prohibited": Verdict.BLOCK,
}
EXACT_VERDICT = {
    "benign": Verdict.ALLOW,
    "write": Verdict.ALLOW,
    "prohibited": Verdict.BLOCK,
}

_VERDICT_RANK = {Verdict.ALLOW: 0, Verdict.VOTE_REQUIRED: 1, Verdict.BLOCK: 2}


@pytest.fixture
def vector_store(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.core.vector_store.CHROMA_HOST", None)
    monkeypatch.setattr("backend.core.vector_store.CHROMA_PERSIST_DIR", str(tmp_path))

    vs = VectorStore()
    vs.initialize()

    # v2 collection ("supreme_law_v2") — the only version now that v1 retired.
    # Seed via the production path, which resolves to v2 by default.
    for aid, content, meta in ARTICLES:
        vs.add_constitution_article(aid, content, meta)
    return vs


async def _no_constitution(*_a, **_k):
    return None


async def _no_log(*_a, **_k):
    return None


def _run_guard(vs, monkeypatch, version, action, context):
    monkeypatch.setattr(
        _settings, "EMBEDDING_ACTIVE_VERSIONS", {"constitution": version}
    )
    guard = ConstitutionalGuard(db=MagicMock())
    guard._vector_store = vs
    guard._redis = None
    # Isolate Tier-2: skip Tier-1 constitution lookup and audit logging.
    guard._get_active_constitution = _no_constitution
    guard._log_decision = _no_log

    captured = {}
    orig_t2 = guard._tier2_check

    async def _wrap(aid, act, ctx):
        decision = await orig_t2(aid, act, ctx)
        captured["sim"] = decision.tier_results.get("max_similarity")
        return decision

    guard._tier2_check = _wrap
    decision = asyncio.run(guard.check_action(AGENT_ID, action, context))
    return decision, captured.get("sim")


def test_v2_guard_is_functional_and_safe(vector_store, monkeypatch, capsys):
    rows = {}
    for name, action, ctx in ACTIONS:
        v2, s2 = _run_guard(vector_store, monkeypatch, "v2", action, ctx)

        rows[name] = (v2.verdict.value, s2)

        # Functional + safe: v2 verdict must meet the minimum required rank.
        assert _VERDICT_RANK[v2.verdict] >= _VERDICT_RANK[MIN_VERDICT[name]], (
            f"{name}: v2 verdict {v2.verdict.value} below required "
            f"{MIN_VERDICT[name].value} (sim={s2})"
        )
        # Exact checks for benign / prohibited (no false blocks, real block).
        if name in EXACT_VERDICT:
            assert v2.verdict == EXACT_VERDICT[name], (
                f"{name}: expected {EXACT_VERDICT[name].value}, got {v2.verdict.value}"
            )

    with capsys.disabled():
        print("\n  action      v2_sim   v2_verdict")
        for name, (v2v, s2) in rows.items():
            print(f"  {name:10s}  {s2!s:>8}   {v2v}")
