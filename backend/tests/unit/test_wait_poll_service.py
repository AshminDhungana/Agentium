"""Unit tests for WaitPollService — EXECUTION strategy extends Phase 16 wait & poll."""
import pytest
from backend.models.entities.wait_condition import WaitStrategy, WaitConditionStatus


class TestWaitStrategyExecution:
    def test_execution_strategy_exists(self):
        """EXECUTION strategy is available in WaitStrategy enum."""
        assert WaitStrategy.EXECUTION.value == "execution"
        assert "execution" in [s.value for s in WaitStrategy]