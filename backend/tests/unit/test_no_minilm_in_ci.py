from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".github" / "workflows" / "integration-tests.yml").exists():
            return cand
    return p.parents[3]  # fallback: backend/tests/unit -> repo root


def test_ci_workflow_has_no_minilm():
    wf = _repo_root() / ".github" / "workflows" / "integration-tests.yml"
    text = wf.read_text(encoding="utf-8")
    assert "all-MiniLM-L6-v2" not in text
    assert "BAAI/bge-base-en-v1.5" in text
