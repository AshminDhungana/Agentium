# backend/tests/unit/test_browser_tasktype.py
from models.entities.task import TaskType
from models.schemas.task import TaskCreate

def test_browser_tasktype_exists():
    assert hasattr(TaskType, "BROWSER")
    assert TaskType.BROWSER.value == "browser"

def test_schema_accepts_browser_task_type():
    tc = TaskCreate(title="Browse", description="Open a page", task_type="browser")
    assert tc.task_type == "browser"   # must NOT be coerced to "execution"

def test_all_tasktype_values_include_browser():
    assert "browser" in [t.value for t in TaskType]