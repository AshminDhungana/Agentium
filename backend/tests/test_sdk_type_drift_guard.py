"""Unit tests for the pre-commit SDK type-drift guard (scripts/check_sdk_type_drift.py)."""

import importlib.util
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_sdk_type_drift.py"


def _load_guard(monkeypatch, staged=None):
    spec = importlib.util.spec_from_file_location("check_sdk_type_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if staged is not None:
        monkeypatch.setattr(module, "staged_files", lambda: staged)
    return module


@pytest.mark.parametrize(
    "staged, expected_exit",
    [
        # API-surface change without generated types -> fail
        (["backend/api/federation_routes.py"], 1),
        (["backend/api/federation_routes.py", "backend/services/foo.py"], 1),
        (["backend/models/requests.py"], 1),
        (["backend/main.py"], 1),
        # API-surface change WITH generated types staged -> pass
        (["backend/api/federation_routes.py", "sdk/typescript/src/generated-types.ts"], 0),
        # Non-API-surface changes -> pass
        (["backend/services/foo.py"], 0),
        (["backend/tests/test_foo.py"], 0),
        (["frontend/src/App.tsx"], 0),
        ([], 0),
    ],
)
def test_guard_verdicts(capsys, monkeypatch, staged, expected_exit):
    module = _load_guard(monkeypatch, staged)
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == expected_exit
    if expected_exit == 1:
        assert "make regen-sdk-types" in capsys.readouterr().out


def test_staged_files_uses_git_index(monkeypatch):
    """The real staged_files() shells out to git, not pre-commit's argv."""
    module = _load_guard(monkeypatch)
    assert callable(module.staged_files)
    with monkeypatch.context() as m:
        m.setattr(module.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "a\nb\n"})())
        assert module.staged_files() == ["a", "b"]
