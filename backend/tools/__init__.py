# Re-export the code_execution singleton so `from backend.tools import
# code_execution_tool` binds to the instance (with `execute`/`_make_service`
# as instance methods), matching how the unit tests drive it.
from .code_execution_tool import code_execution_tool  # noqa: F401
