# Re-export the code_execution singleton so `from backend.tools import
# code_execution_tool` binds to the instance (with `execute`/`_make_service`
# as instance methods), matching how the unit tests drive it.
from .code_execution_tool import code_execution_tool  # noqa: F401
from .tool_search_tool import tool_search_tool  # noqa: F401
# Re-export the web_fetch singleton so `from backend.tools import web_fetch_tool`
# binds to the instance (with `execute`/`client`/`_extract` as instance
# attributes), matching how the unit tests monkeypatch and drive it.
from .web_fetch_tool import web_fetch_tool  # noqa: F401
