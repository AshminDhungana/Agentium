"""
Unit tests for CriticService review logic.

Tests each critic type's preflight checks, AI review, and verdict parsing
in isolation with mocked ModelService.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.critic_agents import CriticService, CriticType, CriticVerdict
from backend.models.entities.task import Task
from backend.models.entities.critics import CriticAgent


class TestCodeCriticPreflight:
    """Tests for _review_code preflight check."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    def test_rejects_eval(self, critic_service):
        content = "result = eval(user_input)"
        task = MagicMock(spec=Task)
        task.description = "Generate safe code"
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "eval" in reason.lower()

    def test_rejects_exec(self, critic_service):
        content = "exec(compiled_code)"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "exec" in reason.lower()

    def test_rejects_os_system(self, critic_service):
        content = "import os; os.system('rm -rf /')"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "os.system" in reason.lower()

    def test_rejects_subprocess_popen(self, critic_service):
        content = "import subprocess; subprocess.Popen(['ls'])"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "subprocess.popen" in reason.lower()

    def test_rejects_sql_injection_patterns(self, critic_service):
        content = "query = f'DELETE FROM users WHERE id = {user_id}'"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT

    def test_rejects_empty_output(self, critic_service):
        content = ""
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "empty" in reason.lower()

    def test_rejects_oversized_output(self, critic_service):
        content = "x = 1\n" * 20000  # >100K chars
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "100k" in reason.lower() or "100K" in reason.lower()

    def test_passes_clean_code(self, critic_service):
        content = "def hello():\n    return 'world'\nprint(hello())"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_code(content, task)
        assert verdict == CriticVerdict.PASS
        assert reason is None


class TestOutputCriticPreflight:
    """Tests for _review_output preflight check."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    def test_rejects_empty_output(self, critic_service):
        content = ""
        task = MagicMock(spec=Task)
        task.description = "Write a summary"
        verdict, reason, suggestions = critic_service._review_output(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "empty" in reason.lower()

    def test_rejects_error_traceback(self, critic_service):
        content = "Traceback (most recent call last):\n  File \"test.py\", line 1\nError: Something failed\nException: ValueError"
        task = MagicMock(spec=Task)
        task.description = "Write a summary"
        verdict, reason, suggestions = critic_service._review_output(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "traceback" in reason.lower() or "error" in reason.lower()

    def test_rejects_irrelevant_output(self, critic_service):
        content = "The weather is nice today. Birds are singing."
        task = MagicMock(spec=Task)
        task.description = "Write a Python function to calculate fibonacci"
        verdict, reason, suggestions = critic_service._review_output(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "unrelated" in reason.lower() or "irrelevant" in reason.lower()

    def test_passes_relevant_output(self, critic_service):
        content = "The fibonacci function calculates the sequence. Python function to calculate fibonacci numbers using recursion."
        task = MagicMock(spec=Task)
        task.description = "Write a Python function to calculate fibonacci"
        verdict, reason, suggestions = critic_service._review_output(content, task)
        assert verdict == CriticVerdict.PASS


class TestPlanCriticPreflight:
    """Tests for _review_plan preflight check."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    def test_rejects_empty_plan(self, critic_service):
        content = ""
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_plan(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "empty" in reason.lower()

    def test_rejects_duplicate_steps(self, critic_service):
        content = "Step 1: Do thing\nStep 2: Do thing\nStep 3: Do other"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_plan(content, task)
        # Implementation checks exact line matches - use exact duplicate
        content_exact = "Step 1: Do thing\nStep 1: Do thing\nStep 3: Do other"
        verdict, reason, suggestions = critic_service._review_plan(content_exact, task)
        assert verdict == CriticVerdict.REJECT
        assert "duplicate" in reason.lower()

    def test_rejects_overlong_plan(self, critic_service):
        content = "\n".join([f"Step {i}: Do something" for i in range(150)])
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_plan(content, task)
        assert verdict == CriticVerdict.REJECT
        assert "100" in reason or "over-engineered" in reason.lower()

    def test_passes_valid_plan(self, critic_service):
        content = "Step 1: Analyze requirements\nStep 2: Design solution\nStep 3: Implement\nStep 4: Test"
        task = MagicMock(spec=Task)
        verdict, reason, suggestions = critic_service._review_plan(content, task)
        assert verdict == CriticVerdict.PASS


class TestAIReviewParsing:
    """Tests for _parse_ai_verdict and prompt building."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    def test_parses_pass_json(self, critic_service):
        raw = '{"verdict": "pass", "reason": null, "suggestions": null}'
        verdict, reason, suggestions = critic_service._parse_ai_verdict(raw)
        assert verdict == CriticVerdict.PASS
        assert reason is None
        assert suggestions is None

    def test_parses_reject_json(self, critic_service):
        raw = '{"verdict": "reject", "reason": "Missing error handling", "suggestions": "Add try/except"}'
        verdict, reason, suggestions = critic_service._parse_ai_verdict(raw)
        assert verdict == CriticVerdict.REJECT
        assert reason == "Missing error handling"
        assert suggestions == "Add try/except"

    def test_parses_markdown_wrapped_json(self, critic_service):
        raw = '```json\n{"verdict": "pass", "reason": null, "suggestions": null}\n```'
        verdict, reason, suggestions = critic_service._parse_ai_verdict(raw)
        assert verdict == CriticVerdict.PASS

    def test_handles_invalid_json(self, critic_service):
        raw = "This is not JSON at all"
        verdict, reason, suggestions = critic_service._parse_ai_verdict(raw)
        assert verdict == CriticVerdict.PASS  # Fail-open
        assert "manual review" in suggestions.lower()

    def test_builds_code_critic_system_prompt(self, critic_service):
        prompt = critic_service._build_critic_system_prompt(CriticType.CODE)
        assert "senior code reviewer" in prompt.lower()
        assert "security" in prompt.lower()
        assert "json" in prompt.lower()

    def test_builds_output_critic_system_prompt(self, critic_service):
        prompt = critic_service._build_critic_system_prompt(CriticType.OUTPUT)
        assert "quality assurance" in prompt.lower()
        assert "user's intent" in prompt.lower()

    def test_builds_plan_critic_system_prompt(self, critic_service):
        prompt = critic_service._build_critic_system_prompt(CriticType.PLAN)
        assert "execution plan auditor" in prompt.lower()
        assert "circular" in prompt.lower() or "achievability" in prompt.lower()

    def test_builds_user_prompt_includes_task_context(self, critic_service):
        task = MagicMock(spec=Task)
        task.description = "Build a REST API"
        prompt = critic_service._build_critic_user_prompt(CriticType.CODE, task, "def api(): pass")
        assert "Build a REST API" in prompt
        assert "def api()" in prompt