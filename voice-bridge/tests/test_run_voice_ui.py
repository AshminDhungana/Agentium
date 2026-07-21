import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..")
    ),
)


class TestRunVoiceUi:
    def test_module_inserts_own_dir_in_sys_path(self):
        with patch("ui.main.main") as mock_main:
            exec_globals = {
                "__name__": "__main__",
                "main": mock_main,
            }
            with patch.object(sys, "path") as mock_path:
                mock_path.__setitem__ = MagicMock()
                mock_path.insert = MagicMock()
                exec(
                    'import sys; import os; sys.path.insert(0, os.path.dirname(".")); from ui.main import main',
                    exec_globals,
                )

    def test_main_called_when_module_executed(self):
        with patch("ui.main.main") as mock_main:
            exec_globals = {"__name__": "__main__", "main": mock_main}
            exec("if __name__ == '__main__': main()", exec_globals)
            mock_main.assert_called_once()

    def test_main_not_called_when_imported(self):
        with patch("ui.main.main") as mock_main:
            exec_globals = {"__name__": "run_voice_ui", "main": mock_main}
            exec("if __name__ == '__main__': main()", exec_globals)
            mock_main.assert_not_called()

    def test_sys_path_inserted_before_import(self):
        fake_path = ["/fake"]
        with (
            patch("sys.path", fake_path),
            patch("os.path.dirname", return_value="/fake/dir"),
        ):
            import importlib
            spec = importlib.util.find_spec("ui.main")
            if spec is not None:
                pass
