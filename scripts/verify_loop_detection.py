#!/usr/bin/env python3
"""
Verification script for Loop & Runaway Detection (Task 20.4).

Run: python scripts/verify_loop_detection.py
"""

import asyncio
import sys
import os

# Add backend to path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(script_dir, "..", "backend")
sys.path.insert(0, backend_path)

from backend.core.loop_detector import LoopDetector
from backend.core.exceptions import LoopDetectedError, BudgetExhaustedError
from backend.core.config import settings


async def test_identical_call_detection():
    print("Testing identical call detection...")
    detector = LoopDetector(max_identical_calls=3)
    wrapped = detector.wrap_executor(lambda name, args: "ok")

    # 3 identical calls should succeed
    wrapped("search", {"q": "test"})
    wrapped("search", {"q": "test"})
    wrapped("search", {"q": "test"})

    # 4th should fail
    try:
        wrapped("search", {"q": "test"})
        print("  FAIL: Should have raised LoopDetectedError")
        return False
    except LoopDetectedError as e:
        print(f"  PASS: {e}")

    return True


async def test_budget_enforcement():
    print("Testing budget enforcement...")
    detector = LoopDetector(budget_usd=0.10, budget_tokens=1000)

    # Within budget
    detector.check_budget(100, 50, 0.01)
    detector.check_budget(200, 100, 0.02)

    # Exceed cost budget
    try:
        detector.check_budget(5000, 2000, 0.20)  # cumulative > 0.10
        print("  FAIL: Should have raised BudgetExhaustedError (cost)")
        return False
    except BudgetExhaustedError as e:
        print(f"  PASS: {e}")

    # Test token budget
    detector2 = LoopDetector(budget_usd=None, budget_tokens=500)
    detector2.check_budget(100, 100, 0.01)
    try:
        detector2.check_budget(200, 200, 0.01)  # cumulative 600 > 500
        print("  FAIL: Should have raised BudgetExhaustedError (tokens)")
        return False
    except BudgetExhaustedError as e:
        print(f"  PASS: {e}")

    return True


async def test_config_settings():
    print("Testing config settings...")
    assert hasattr(settings, "LOOP_DETECTION_MAX_IDENTICAL_CALLS"), "LOOP_DETECTION_MAX_IDENTICAL_CALLS missing"
    assert hasattr(settings, "LOOP_DETECTION_BUDGET_USD"), "LOOP_DETECTION_BUDGET_USD missing"
    assert hasattr(settings, "LOOP_DETECTION_BUDGET_TOKENS"), "LOOP_DETECTION_BUDGET_TOKENS missing"
    assert hasattr(settings, "LOOP_DETECTION_MAX_CALL_HISTORY"), "LOOP_DETECTION_MAX_CALL_HISTORY missing"

    assert settings.LOOP_DETECTION_MAX_IDENTICAL_CALLS == 3
    assert settings.LOOP_DETECTION_BUDGET_USD is None  # default is None (unlimited)
    assert settings.LOOP_DETECTION_BUDGET_TOKENS is None  # default is None (unlimited)
    assert settings.LOOP_DETECTION_MAX_CALL_HISTORY == 50
    print("  PASS: All settings present with correct defaults")
    return True


async def test_history_window():
    print("Testing history window eviction...")
    detector = LoopDetector(max_identical_calls=3, max_call_history=5)
    wrapped = detector.wrap_executor(lambda name, args: "ok")
    # Fill history with different calls
    for i in range(10):
        wrapped("search", {"q": f"q{i}"})
    # The 4th identical call should still be detected despite eviction
    wrapped("search", {"q": "repeat"})
    wrapped("search", {"q": "repeat"})
    wrapped("search", {"q": "repeat"})
    try:
        wrapped("search", {"q": "repeat"})
        print("  FAIL: Should have raised LoopDetectedError")
        return False
    except LoopDetectedError as e:
        print(f"  PASS: {e}")
    return True


async def test_args_order_invariant():
    print("Testing args order invariance...")
    detector = LoopDetector(max_identical_calls=2)
    wrapped = detector.wrap_executor(lambda name, args: "ok")
    wrapped("search", {"a": 1, "b": 2})
    wrapped("search", {"b": 2, "a": 1})  # Same args, different key order
    try:
        wrapped("search", {"a": 1, "b": 2})
        print("  FAIL: Should have raised LoopDetectedError")
        return False
    except LoopDetectedError as e:
        print(f"  PASS: {e}")
    return True


async def test_different_tools_independent():
    print("Testing different tools tracked independently...")
    detector = LoopDetector(max_identical_calls=2)
    wrapped = detector.wrap_executor(lambda name, args: "ok")
    wrapped("tool_a", {"x": 1})
    wrapped("tool_a", {"x": 1})  # 2 calls to tool_a OK
    wrapped("tool_b", {"x": 1})   # First call to tool_b OK
    wrapped("tool_b", {"x": 1})   # 2 calls to tool_b OK
    try:
        wrapped("tool_a", {"x": 1})  # 3rd call to tool_a fails
        print("  FAIL: Should have raised LoopDetectedError")
        return False
    except LoopDetectedError as e:
        print(f"  PASS: {e}")
    return True


async def test_stats():
    print("Testing get_stats...")
    detector = LoopDetector(max_identical_calls=3)
    wrapped = detector.wrap_executor(lambda name, args: "ok")
    wrapped("search", {"q": "a"})
    wrapped("search", {"q": "a"})
    wrapped("search", {"q": "b"})
    stats = detector.get_stats()
    assert stats["total_calls"] == 3, f"Expected 3 total calls, got {stats['total_calls']}"
    assert stats["unique_signatures"] == 2, f"Expected 2 unique signatures, got {stats['unique_signatures']}"
    assert stats["max_consecutive_identical"] == 2, f"Expected max 2 consecutive, got {stats['max_consecutive_identical']}"
    print("  PASS: Stats match expected values")
    return True


async def test_none_budget_unlimited():
    print("Testing None budget = unlimited...")
    detector = LoopDetector(budget_usd=None, budget_tokens=None)
    detector.check_budget(100000, 50000, 1000.0)  # No exception
    print("  PASS: None budget allows unlimited usage")
    return True


async def test_zero_budget_unlimited():
    print("Testing zero budget = unlimited...")
    detector = LoopDetector(budget_usd=0, budget_tokens=0)
    detector.check_budget(100000, 50000, 1000.0)  # No exception
    print("  PASS: Zero budget allows unlimited usage")
    return True


async def main():
    print("=" * 60)
    print("Loop & Runaway Detection Verification (Task 20.4)")
    print("=" * 60)

    all_passed = True
    all_passed &= await test_identical_call_detection()
    all_passed &= await test_budget_enforcement()
    all_passed &= await test_config_settings()
    all_passed &= await test_history_window()
    all_passed &= await test_args_order_invariant()
    all_passed &= await test_different_tools_independent()
    all_passed &= await test_stats()
    all_passed &= await test_none_budget_unlimited()
    all_passed &= await test_zero_budget_unlimited()

    print("=" * 60)
    if all_passed:
        print("ALL CHECKS PASSED")
        return 0
    else:
        print("SOME CHECKS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))