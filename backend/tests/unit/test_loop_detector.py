# tests/unit/test_loop_detector.py
import pytest
import json
from backend.core.loop_detector import LoopDetector
from backend.core.exceptions import LoopDetectedError, BudgetExhaustedError

class TestIdenticalCallDetection:
    def test_allows_first_call(self):
        detector = LoopDetector(max_identical_calls=3)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        result = wrapped("search", {"query": "test"})
        assert result == "ok"

    def test_allows_different_args(self):
        detector = LoopDetector(max_identical_calls=3)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        wrapped("search", {"query": "a"})
        wrapped("search", {"query": "b"})
        wrapped("search", {"query": "c"})  # 3 different calls OK

    def test_blocks_fourth_identical_call(self):
        detector = LoopDetector(max_identical_calls=3)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        wrapped("search", {"query": "same"})
        wrapped("search", {"query": "same"})
        wrapped("search", {"query": "same"})
        with pytest.raises(LoopDetectedError) as exc:
            wrapped("search", {"query": "same"})
        assert exc.value.tool_name == "search"
        assert exc.value.identical_count == 4
        assert exc.value.max_allowed == 3

    def test_different_tools_independent(self):
        detector = LoopDetector(max_identical_calls=2)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        wrapped("tool_a", {"x": 1})
        wrapped("tool_a", {"x": 1})  # 2 calls to tool_a OK
        wrapped("tool_b", {"x": 1})   # First call to tool_b OK
        wrapped("tool_b", {"x": 1})   # 2 calls to tool_b OK
        with pytest.raises(LoopDetectedError):
            wrapped("tool_a", {"x": 1})  # 3rd call to tool_a fails

    def test_args_order_invariant(self):
        """JSON args with different key order should be treated as identical."""
        detector = LoopDetector(max_identical_calls=2)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        wrapped("search", {"a": 1, "b": 2})
        wrapped("search", {"b": 2, "a": 1})  # Same args, different key order
        with pytest.raises(LoopDetectedError):
            wrapped("search", {"a": 1, "b": 2})

class TestBudgetEnforcement:
    def test_allows_within_budget(self):
        detector = LoopDetector(budget_usd=10.0, budget_tokens=10000)
        detector.check_budget(prompt_tokens=1000, completion_tokens=500, cost_usd=0.05)
        detector.check_budget(prompt_tokens=2000, completion_tokens=1000, cost_usd=0.10)

    def test_blocks_on_cost_exceeded(self):
        detector = LoopDetector(budget_usd=0.10)
        detector.check_budget(1000, 500, 0.05)
        with pytest.raises(BudgetExhaustedError) as exc:
            detector.check_budget(2000, 1000, 0.10)  # cumulative 0.15 > 0.10
        assert exc.value.budget_type == "cost"
        assert exc.value.actual == 0.15
        assert exc.value.limit == 0.10

    def test_blocks_on_tokens_exceeded(self):
        detector = LoopDetector(budget_tokens=2000)
        detector.check_budget(1000, 500, 0.05)
        with pytest.raises(BudgetExhaustedError) as exc:
            detector.check_budget(2000, 1000, 0.10)  # cumulative 4500 > 2000
        assert exc.value.budget_type == "tokens"
        assert exc.value.actual == 4500
        assert exc.value.limit == 2000

    def test_none_budget_unlimited(self):
        detector = LoopDetector(budget_usd=None, budget_tokens=None)
        detector.check_budget(100000, 50000, 1000.0)  # No exception

    def test_zero_budget_unlimited(self):
        detector = LoopDetector(budget_usd=0, budget_tokens=0)
        detector.check_budget(100000, 50000, 1000.0)  # No exception

class TestHistoryWindow:
    def test_history_eviction(self):
        detector = LoopDetector(max_identical_calls=3, max_call_history=5)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        # Fill history with different calls
        for i in range(10):
            wrapped("search", {"q": f"q{i}"})
        # The 4th identical call should still be detected despite eviction
        wrapped("search", {"q": "repeat"})
        wrapped("search", {"q": "repeat"})
        wrapped("search", {"q": "repeat"})
        with pytest.raises(LoopDetectedError):
            wrapped("search", {"q": "repeat"})

class TestStats:
    def test_get_stats_returns_correct_counts(self):
        detector = LoopDetector(max_identical_calls=3)
        wrapped = detector.wrap_executor(lambda name, args: "ok")
        wrapped("search", {"q": "a"})
        wrapped("search", {"q": "a"})
        wrapped("search", {"q": "b"})
        stats = detector.get_stats()
        assert stats["total_calls"] == 3
        assert stats["unique_signatures"] == 2
        assert stats["max_consecutive_identical"] == 2


class TestAsyncLoopDetection:
    @pytest.mark.asyncio
    async def test_async_allows_first_call(self):
        detector = LoopDetector(max_identical_calls=3)

        async def async_tool(name, args):
            return f"result_{name}"

        wrapped = detector.wrap_executor(async_tool)
        result = await wrapped("search", {"query": "hello"})
        assert result == "result_search"

    @pytest.mark.asyncio
    async def test_async_blocks_consecutive_identical_calls(self):
        detector = LoopDetector(max_identical_calls=2)

        async def async_tool(name, args):
            return "ok"

        wrapped = detector.wrap_executor(async_tool)
        # Call 1 and 2 succeed
        assert await wrapped("crawl", {"url": "https://example.com"}) == "ok"
        assert await wrapped("crawl", {"url": "https://example.com"}) == "ok"

        # Call 3 triggers LoopDetectedError
        with pytest.raises(LoopDetectedError) as exc_info:
            await wrapped("crawl", {"url": "https://example.com"})

        assert exc_info.value.tool_name == "crawl"
        assert exc_info.value.identical_count == 3
        assert exc_info.value.max_allowed == 2

    @pytest.mark.asyncio
    async def test_async_allows_different_args(self):
        detector = LoopDetector(max_identical_calls=2)

        async def async_tool(name, args):
            return f"searched_{args['q']}"

        wrapped = detector.wrap_executor(async_tool)
        assert await wrapped("search", {"q": "term_1"}) == "searched_term_1"
        assert await wrapped("search", {"q": "term_2"}) == "searched_term_2"
        assert await wrapped("search", {"q": "term_3"}) == "searched_term_3"
        assert await wrapped("search", {"q": "term_4"}) == "searched_term_4"