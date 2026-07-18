from backend.services.tasks.task_executor import _extract_workspace


def test_extract_workspace_present():
    result = {
        "content": ["done"],
        "workspace_path": "~/agentium-workspace/30001/t9",
        "artifacts": [{"name": "a.txt", "size": 3}],
    }
    ws_path, arts = _extract_workspace(result)
    assert ws_path == "~/agentium-workspace/30001/t9"
    assert arts == [{"name": "a.txt", "size": 3}]


def test_extract_workspace_absent():
    result = {"content": ["done"]}
    ws_path, arts = _extract_workspace(result)
    assert ws_path is None
    assert arts == []


def test_extract_workspace_not_a_dict():
    ws_path, arts = _extract_workspace("not a dict")
    assert ws_path is None
    assert arts == []


def test_extract_workspace_artifacts_missing_defaults_empty():
    result = {"content": ["done"], "workspace_path": "~/x"}
    ws_path, arts = _extract_workspace(result)
    assert ws_path == "~/x"
    assert arts == []
