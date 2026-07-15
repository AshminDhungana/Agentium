"""Task 18 — assert the RAG embedding path no longer references the v1 model.

v1 (sentence-transformers/all-MiniLM-L6-v2, 384-dim) was retired. This test
asserts the RAG/ChromaDB embedding path — vector_store, config, the build
images, and knowledge_service — contains no reference to that model.

OUT OF SCOPE (intentionally excluded, separate model choice):
  * backend/services/skill_manager.py and backend/models/entities/skill.py
    (the SkillManager pipeline, per ADR-021 scope)
  * backend/tools/embedding_tool.py (an agent tool with its own default)
  * backend/alembic/versions/* (historical DB migrations — not changed)
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # backend/tests/unit -> repo root
BACKEND = ROOT / "backend"

# Files belonging to the RAG embedding path that must be MiniLM-free.
RAG_PATH_FILES = [
    BACKEND / "core" / "vector_store.py",
    BACKEND / "core" / "config.py",
    BACKEND / "Dockerfile",
    BACKEND / "Dockerfile.privileged",
    BACKEND / "services" / "knowledge_service.py",
]

LEGACY_MARKERS = ["all-MiniLM-L6-v2", "sentence-transformers/all-MiniLM-L6-v2"]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_no_legacy_embedding_in_rag_path():
    for f in RAG_PATH_FILES:
        assert f.exists(), f"expected {f} to exist"
        content = _read(f)
        for marker in LEGACY_MARKERS:
            assert marker not in content, f"{f} still references legacy model: {marker}"


def test_config_default_is_bge():
    config = _read(BACKEND / "core" / "config.py")
    assert 'EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"' in config
    assert "EMBEDDING_DIM: int = 768" in config
    # No 384-dim default remains for the RAG embedding.
    assert "EMBEDDING_DIM: int = 384" not in config
