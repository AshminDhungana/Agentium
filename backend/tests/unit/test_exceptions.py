# tests/unit/test_exceptions.py
import pytest
from backend.core.exceptions import LoopDetectedError, BudgetExhaustedError

def test_loop_detected_error_creation():
    err = LoopDetectedError("tool_name", 5, 3)
    assert "tool_name" in str(err)
    assert "5" in str(err)
    assert "3" in str(err)
    assert err.tool_name == "tool_name"
    assert err.identical_count == 5
    assert err.max_allowed == 3

def test_budget_exhausted_error_creation():
    err = BudgetExhaustedError("cost", 15.50, 10.00)
    assert "cost" in str(err)
    assert "15.50" in str(err)
    assert "10.00" in str(err)
    assert err.budget_type == "cost"
    assert err.actual == 15.50
    assert err.limit == 10.00

def test_budget_exhausted_error_tokens():
    err = BudgetExhaustedError("tokens", 150000, 100000)
    assert err.budget_type == "tokens"
    assert err.actual == 150000
    assert err.limit == 100000