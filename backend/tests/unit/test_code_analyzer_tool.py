"""
Quick smoke tests for code_analyzer_tool.
"""
import pytest


def test_code_analyzer_python_syntax_valid():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
def hello():
    print("Hello, World!")
    return 42
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["syntax"]
    ))
    assert result["success"] is True
    assert result["analysis"]["syntax"]["valid"] is True


def test_code_analyzer_python_syntax_invalid():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
def hello(
    print("Missing paren")
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["syntax"]
    ))
    assert result["success"] is True
    assert result["analysis"]["syntax"]["valid"] is False
    assert len(result["analysis"]["syntax"]["errors"]) > 0


def test_code_analyzer_complexity():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
def complex_func(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                print(i)
    return x
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["complexity"]
    ))
    assert result["success"] is True
    assert "complexity" in result["analysis"]
    assert "cyclomatic_complexity" in result["analysis"]["complexity"]
    assert result["analysis"]["complexity"]["functions"] == 1


def test_code_analyzer_imports():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
import os
import sys
from pathlib import Path
from typing import List, Dict
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["all"]
    ))
    assert result["success"] is True
    assert "imports" in result["analysis"]
    imports = result["analysis"]["imports"]
    assert "os" in imports
    assert "sys" in imports
    assert "pathlib.Path" in imports


def test_code_analyzer_functions():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
def func1(a, b):
    return a + b

async def func2(x):
    return x * 2

class MyClass:
    def method(self):
        pass
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["all"]
    ))
    assert result["success"] is True
    assert "functions" in result["analysis"]
    funcs = result["analysis"]["functions"]
    assert len(funcs) >= 2
    names = [f["name"] for f in funcs]
    assert "func1" in names
    assert "func2" in names


def test_code_analyzer_quality_score():
    from backend.tools.code_analyzer_tool import code_analyzer

    code = """
def clean_func():
    return 42
"""

    result = asyncio_run(code_analyzer.execute(
        code=code,
        language="python",
        analysis_types=["all"]
    ))
    assert result["success"] is True
    assert "quality_score" in result
    assert 0 <= result["quality_score"] <= 100


def test_code_analyzer_missing_code():
    from backend.tools.code_analyzer_tool import code_analyzer

    result = asyncio_run(code_analyzer.execute(
        code=None,
        file_path=None,
        language="python"
    ))
    assert result["success"] is False
    assert "provide code" in result["error"].lower()


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)