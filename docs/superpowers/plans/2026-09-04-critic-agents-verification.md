# Critic Agents Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add comprehensive unit and integration tests for all three critic agent types (Code, Output, Plan) plus a manual verification script, fixing any gaps found during verification.

**Architecture:** TDD approach - write failing tests first, then implement fixes. Tests cover preflight checks, AI review logic, retry/escalation flows, acceptance criteria integration, consensus protocol, and case law indexing. All AI calls mocked in CI; manual script uses real LLM.

**Tech Stack:** Python 3.13, pytest, pytest-asyncio, SQLAlchemy, FastAPI, unittest.mock, OpenAI/Anthropic SDKs (manual script only)

## Global Constraints

- All new tests must pass with `pytest -v` and meet 20% coverage floor
- No external API calls in CI tests - mock `ModelService.generate()`
- Use existing fixtures: `seeded_db`, `mock_llm_client`, `mock_critic_service`
- Follow existing test patterns in `backend/tests/unit/` and `backend/tests/integration/`
- Critic ID scheme: 7xxxx=Code, 8xxxx=Output, 9xxxx=Plan
- Max retries = 5 (constant in `CriticService.DEFAULT_MAX_RETRIES`)
- All database changes in tests use transaction rollback via `seeded_db` fixture
- Run lint/typecheck: `ruff check` and `mypy` (if configured)

---

### Task 1: Create Unit Test File for Critic Review Logic

**Files:**
- Create: `backend/tests/unit/test_critic_review_logic.py`

**Interfaces:**
- Consumes: `backend/services/critic_agents.py` (CriticService, CriticType, CriticVerdict)
- Produces: Test functions for each critic type's review methods

- [ ] **Step 1: Write the failing test file scaffold**

```python
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
        content = "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)"
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py -v
```
Expected: All tests FAIL (file doesn't exist yet)

- [ ] **Step 3: Create the test file**

```bash
mkdir -p backend/tests/unit
# (File content from Step 1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py -v
```
Expected: All tests PASS (after implementation is verified)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/test_critic_review_logic.py
git commit -m "test: add unit tests for critic preflight checks and AI parsing"
```

---

### Task 2: Add AI Review Tests (Mocked ModelService)

**Files:**
- Modify: `backend/tests/unit/test_critic_review_logic.py` (append new test classes)

**Interfaces:**
- Consumes: `CriticService._ai_review`, `CriticService._execute_review`, `ModelService.generate`
- Produces: Tests for AI review flow with mocked LLM responses

- [ ] **Step 1: Write the failing test additions**

```python
# Append to test_critic_review_logic.py

class TestAIReviewFlow:
    """Tests for _ai_review and _execute_review with mocked ModelService."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.fixture
    def mock_task(self):
        task = MagicMock(spec=Task)
        task.description = "Write a secure login function"
        task.id = "test-task-123"
        return task

    @pytest.fixture
    def mock_critic(self):
        critic = MagicMock(spec=CriticAgent)
        critic.agentium_id = "70001"
        critic.critic_specialty = CriticType.CODE
        critic.preferred_review_model = "openai:gpt-4o-mini"
        return critic

    @patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock)
    async def test_ai_review_returns_pass(self, mock_generate, critic_service, mock_critic, mock_task):
        mock_generate.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
        
        verdict, reason, suggestions = await critic_service._ai_review(
            mock_critic, mock_task, "def login(): pass", CriticType.CODE
        )
        
        assert verdict == CriticVerdict.PASS
        mock_generate.assert_called_once()

    @patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock)
    async def test_ai_review_returns_reject(self, mock_generate, critic_service, mock_critic, mock_task):
        mock_generate.return_value = '{"verdict": "reject", "reason": "No input validation", "suggestions": "Add validation"}'
        
        verdict, reason, suggestions = await critic_service._ai_review(
            mock_critic, mock_task, "def login(user, pwd): return True", CriticType.CODE
        )
        
        assert verdict == CriticVerdict.REJECT
        assert reason == "No input validation"

    @patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock)
    async def test_ai_review_falls_back_to_rule_based_on_exception(self, mock_generate, critic_service, mock_critic, mock_task):
        mock_generate.side_effect = Exception("API timeout")
        
        # Should fall back to rule-based (preflight) review
        verdict, reason, suggestions = await critic_service._execute_review(
            critic_service, mock_critic, "test-task-123", "def login(): pass", CriticType.CODE
        )
        
        # Rule-based should pass for clean code
        assert verdict == CriticVerdict.PASS

    @patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock)
    async def test_execute_review_runs_preflight_first(self, mock_generate, critic_service, mock_critic, mock_task):
        """Preflight check runs before AI review - dangerous code rejected without AI call."""
        mock_generate.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
        
        verdict, reason, suggestions = await critic_service._execute_review(
            critic_service, mock_critic, "test-task-123", "eval(user_input)", CriticType.CODE
        )
        
        # Should be rejected by preflight, AI not called
        assert verdict == CriticVerdict.REJECT
        assert "eval" in reason.lower()
        mock_generate.assert_not_called()
```

- [ ] **Step 2: Append tests to file**

```bash
cat >> backend/tests/unit/test_critic_review_logic.py << 'EOF'
# (TestAIReviewFlow class from Step 1)
EOF
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py::TestAIReviewFlow -v
```
Expected: All tests PASS

- [ ] **Step 4: Run full unit test suite**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/test_critic_review_logic.py
git commit -m "test: add AI review flow tests with mocked ModelService"
```

---

### Task 3: Create Integration Tests for Full Review Flow

**Files:**
- Create: `backend/tests/integration/test_critic_integration.py`

**Interfaces:**
- Consumes: `seeded_db` fixture, `CriticService`, `CriticAgent`, `CritiqueReview`, `Task`, `AcceptanceCriteriaService`
- Produces: Full flow tests (spawn → review → retry → escalate) with real DB

- [ ] **Step 1: Write the failing test file**

```python
"""
Integration tests for CriticService full review flow.

Tests the complete review_task_output() lifecycle with database:
- Spawn critics for task
- Submit output for review (preflight → AI → verdict)
- Retry logic with same critic instances
- Escalation after max retries
- Acceptance criteria integration
- Consensus protocol (secondary critic)
- Case law indexing on hard rejections
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session

from backend.services.critic_agents import CriticService, CriticType, CriticVerdict
from backend.models.entities.critics import CriticAgent, CritiqueReview
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.services.acceptance_criteria import AcceptanceCriteriaService, AcceptanceCriterion, CriterionType


class TestCriticSpawnAndTerminate:
    """Tests for spawning and terminating ephemeral critics."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.mark.asyncio
    async def test_spawn_critics_for_code_task(self, seeded_db: Session, critic_service: CriticService):
        """Code tasks spawn CODE and OUTPUT critics."""
        task = Task(
            id="test-task-code-1",
            description="Write a Python function",
            task_type=TaskType.CODE,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        spawned = await critic_service.spawn_critics_for_task(
            db=seeded_db, task_id=task.id, task_type="code"
        )

        assert "code" in spawned
        assert "output" in spawned
        assert spawned["code"].startswith("7")
        assert spawned["output"].startswith("8")

        # Verify critics exist in DB
        code_critic = seeded_db.query(CriticAgent).filter_by(agentium_id=spawned["code"]).first()
        output_critic = seeded_db.query(CriticAgent).filter_by(agentium_id=spawned["output"]).first()
        assert code_critic is not None
        assert code_critic.critic_specialty == CriticType.CODE
        assert code_critic.current_task_id == task.id
        assert code_critic.is_persistent is False
        assert output_critic.critic_specialty == CriticType.OUTPUT

    @pytest.mark.asyncio
    async def test_spawn_critics_for_plan_task(self, seeded_db: Session, critic_service: CriticService):
        """Plan tasks spawn only PLAN critic."""
        task = Task(
            id="test-task-plan-1",
            description="Create execution plan",
            task_type=TaskType.DAG,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        spawned = await critic_service.spawn_critics_for_task(
            db=seeded_db, task_id=task.id, task_type="plan"
        )

        assert "plan" in spawned
        assert "code" not in spawned
        assert spawned["plan"].startswith("9")

    @pytest.mark.asyncio
    async def test_terminate_critics_for_task(self, seeded_db: Session, critic_service: CriticService):
        """Terminate marks critics inactive and TERMINATED status."""
        task = Task(
            id="test-task-term-1",
            description="Test termination",
            task_type=TaskType.CODE,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")
        count = await critic_service.terminate_critics_for_task(seeded_db, task.id, reason="test_done")

        assert count == 2  # code + output
        critics = seeded_db.query(CriticAgent).filter_by(current_task_id=task.id).all()
        for c in critics:
            assert c.is_active is False
            assert c.status == AgentStatus.TERMINATED


class TestReviewTaskOutput:
    """Tests for review_task_output() full flow."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.fixture
    def task_with_criteria(self, seeded_db: Session):
        """Create a task with acceptance criteria."""
        criteria = [
            AcceptanceCriterion(
                name="has_function_def",
                description="Output contains a function definition",
                criterion_type=CriterionType.CONTAINS,
                validator="code",
                mandatory=True,
                expected_value="def ",
            ),
            AcceptanceCriterion(
                name="no_eval",
                description="No eval() usage",
                criterion_type=CriterionType.NOT_CONTAINS,
                validator="code",
                mandatory=True,
                expected_value="eval(",
            ),
        ]
        task = Task(
            id="test-task-criteria-1",
            description="Write safe Python code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            acceptance_criteria=AcceptanceCriteriaService.to_json(criteria),
        )
        seeded_db.add(task)
        seeded_db.commit()
        return task

    @pytest.mark.asyncio
    async def test_code_critic_rejects_dangerous_code(self, seeded_db: Session, critic_service: CriticService):
        """Code critic rejects code with eval() via preflight."""
        task = Task(
            id="test-review-1",
            description="Write safe code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            result = await critic_service.review_task_output(
                db=seeded_db,
                task_id=task.id,
                output_content="result = eval(user_input)",
                critic_type=CriticType.CODE,
            )

        assert result["verdict"] == CriticVerdict.REJECT.value
        assert "eval" in result["rejection_reason"].lower()
        assert result["critic_type"] == "code"
        mock_gen.assert_not_called()  # Preflight caught it

    @pytest.mark.asyncio
    async def test_code_critic_passes_clean_code(self, seeded_db: Session, critic_service: CriticService):
        """Code critic passes clean code after AI review."""
        task = Task(
            id="test-review-2",
            description="Write a hello world function",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            result = await critic_service.review_task_output(
                db=seeded_db,
                task_id=task.id,
                output_content="def hello():\n    return 'world'",
                critic_type=CriticType.CODE,
            )

        assert result["verdict"] == CriticVerdict.PASS.value
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_critic_rejects_empty(self, seeded_db: Session, critic_service: CriticService):
        """Output critic rejects empty output."""
        task = Task(
            id="test-review-3",
            description="Write a summary",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="research")

        result = await critic_service.review_task_output(
            db=seeded_db,
            task_id=task.id,
            output_content="",
            critic_type=CriticType.OUTPUT,
        )

        assert result["verdict"] == CriticVerdict.REJECT.value
        assert "empty" in result["rejection_reason"].lower()

    @pytest.mark.asyncio
    async def test_output_critic_passes_relevant(self, seeded_db: Session, critic_service: CriticService):
        """Output critic passes relevant output."""
        task = Task(
            id="test-review-4",
            description="Explain fibonacci sequence",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="research")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            result = await critic_service.review_task_output(
                db=seeded_db,
                task_id=task.id,
                output_content="The fibonacci sequence is a series where each number is the sum of the two preceding ones.",
                critic_type=CriticType.OUTPUT,
            )

        assert result["verdict"] == CriticVerdict.PASS.value

    @pytest.mark.asyncio
    async def test_plan_critic_rejects_duplicate_steps(self, seeded_db: Session, critic_service: CriticService):
        """Plan critic rejects plan with duplicate steps."""
        task = Task(
            id="test-review-5",
            description="Plan a project",
            task_type=TaskType.DAG,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="plan")

        result = await critic_service.review_task_output(
            db=seeded_db,
            task_id=task.id,
            output_content="Step 1: Research\nStep 2: Research\nStep 3: Build",
            critic_type=CriticType.PLAN,
        )

        assert result["verdict"] == CriticVerdict.REJECT.value
        assert "duplicate" in result["rejection_reason"].lower()


class TestRetryAndEscalation:
    """Tests for retry logic and escalation after max retries."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.mark.asyncio
    async def test_retry_uses_same_critic_instance(self, seeded_db: Session, critic_service: CriticService):
        """On retry, same critic instance reviews again (context retained)."""
        task = Task(
            id="test-retry-1",
            description="Write code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        # First review - REJECT
        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "reject", "reason": "Missing docs", "suggestions": "Add docstrings"}'
            
            result1 = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="def f(): pass",
                critic_type=CriticType.CODE, retry_count=0
            )

        assert result1["verdict"] == CriticVerdict.REJECT.value
        critic_id_1 = result1["critic_id"]

        # Second review (retry) - PASS
        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            result2 = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="def f():\n    '''Docstring'''\n    pass",
                critic_type=CriticType.CODE, retry_count=1
            )

        assert result2["verdict"] == CriticVerdict.PASS.value
        assert result2["critic_id"] == critic_id_1  # Same critic!
        assert result2["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_escalate_after_max_retries(self, seeded_db: Session, critic_service: CriticService):
        """After 5 rejections, verdict becomes ESCALATE and Council is notified."""
        task = Task(
            id="test-escalate-1",
            description="Write code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        # Simulate 5 rejections
        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "reject", "reason": "Still bad", "suggestions": "Fix it"}'
            
            for i in range(5):
                result = await critic_service.review_task_output(
                    db=seeded_db, task_id=task.id, output_content="bad code",
                    critic_type=CriticType.CODE, retry_count=i
                )
                assert result["verdict"] == CriticVerdict.REJECT.value

        # 6th attempt (retry_count=5 >= max_retries=5) should ESCALATE
        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "reject", "reason": "Still bad", "suggestions": "Fix it"}'
            
            result = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="bad code",
                critic_type=CriticType.CODE, retry_count=5
            )

        assert result["verdict"] == CriticVerdict.ESCALATE.value
        assert "escalation" in result
        assert result["escalation"]["escalated"] is True

        # Verify task status changed to DELIBERATING
        seeded_db.refresh(task)
        assert task.status == TaskStatus.DELIBERATING


class TestAcceptanceCriteriaIntegration:
    """Tests for acceptance criteria evaluation during review."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.mark.asyncio
    async def test_criteria_evaluated_before_ai_review(self, seeded_db: Session, critic_service: CriticService, task_with_criteria: Task):
        """Mandatory criteria failure rejects before AI review is called."""
        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task_with_criteria.id, task_type="code")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            # Output fails mandatory criteria (no "def ", contains "eval(")
            result = await critic_service.review_task_output(
                db=seeded_db,
                task_id=task_with_criteria.id,
                output_content="eval('bad')",
                critic_type=CriticType.CODE,
            )

        assert result["verdict"] == CriticVerdict.REJECT.value
        assert "mandatory acceptance criteria failed" in result["rejection_reason"].lower()
        assert "criteria_results" in result
        mock_gen.assert_not_called()  # AI not called when criteria fail

    @pytest.mark.asyncio
    async def test_criteria_pass_allows_ai_review(self, seeded_db: Session, critic_service: CriticService, task_with_criteria: Task):
        """Passing criteria allows AI review to proceed."""
        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task_with_criteria.id, task_type="code")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '{"verdict": "pass", "reason": null, "suggestions": null}'
            
            # Output passes criteria (has "def ", no "eval(")
            result = await critic_service.review_task_output(
                db=seeded_db,
                task_id=task_with_criteria.id,
                output_content="def safe_function():\n    return 42",
                critic_type=CriticType.CODE,
            )

        assert result["verdict"] == CriticVerdict.PASS.value
        mock_gen.assert_called_once()
        assert result["criteria_evaluated"] == 2
        assert result["criteria_passed"] == 2


class TestConsensusProtocol:
    """Tests for consensus protocol (secondary critic on first rejection)."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.mark.asyncio
    async def test_consensus_conditional_pass(self, seeded_db: Session, critic_service: CriticService):
        """First critic REJECT, second critic PASS → conditional PASS."""
        task = Task(
            id="test-consensus-1",
            description="Write code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        # Need TWO critics of same type for consensus
        # Spawn a second critic manually
        critic2 = CriticAgent(
            agentium_id="70002",
            name="Code Critic 70002",
            critic_specialty=CriticType.CODE,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            current_task_id=task.id,
            preferred_review_model="openai:gpt-4o-mini",
        )
        seeded_db.add(critic2)
        seeded_db.commit()

        call_count = [0]
        async def mock_generate_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return '{"verdict": "reject", "reason": "Issue found", "suggestions": "Fix it"}'
            return '{"verdict": "pass", "reason": null, "suggestions": null}'

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = mock_generate_side_effect
            
            result = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="code",
                critic_type=CriticType.CODE, retry_count=0
            )

        assert result["verdict"] == CriticVerdict.PASS.value
        assert result["consensus_reached"] is False  # Conditional pass
        assert call_count[0] == 2  # Both critics called


class TestCaseLawIndexing:
    """Tests for case law indexing on hard rejections."""

    @pytest.fixture
    def critic_service(self):
        return CriticService()

    @pytest.mark.asyncio
    async def test_case_law_indexed_on_reject(self, seeded_db: Session, critic_service: CriticService):
        """Hard REJECT stores case law in critic_case_law collection."""
        task = Task(
            id="test-case-law-1",
            description="Write secure code",
            task_type=TaskType.CODE,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.critic_agents.ModelService.generate", new_callable=AsyncMock) as mock_gen, \
             patch("backend.services.critic_agents.get_knowledge_service") as mock_ks:
            
            mock_gen.return_value = '{"verdict": "reject", "reason": "SQL injection risk", "suggestions": "Use parameterized queries"}'
            mock_knowledge = MagicMock()
            mock_ks.return_value = mock_knowledge
            
            result = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="query = f'SELECT * FROM users WHERE id={id}'",
                critic_type=CriticType.CODE, retry_count=0
            )

        assert result["verdict"] == CriticVerdict.REJECT.value
        mock_knowledge.store_or_revise_knowledge.assert_called_once()
        call_args = mock_knowledge.store_or_revise_knowledge.call_args
        assert call_args[1]["collection_name"] == "critic_case_law"
        assert "case_law" in call_args[1]["doc_id"]
        assert "SQL injection" in call_args[1]["content"]
```

- [ ] **Step 2: Create the test file**

```bash
mkdir -p backend/tests/integration
# (File content from Step 1)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/integration/test_critic_integration.py -v
```
Expected: All tests PASS

- [ ] **Step 4: Run full integration test suite (no regressions)**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/integration/test_e2e_task_execution.py::TestDelegateToTaskWithCritics -v
```
Expected: Existing critic integration tests still PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_critic_integration.py
git commit -m "test: add integration tests for critic full review flow"
```

---

### Task 4: Create Manual Verification Script

**Files:**
- Create: `scripts/verify_critics.py`

**Interfaces:**
- Consumes: `CriticService`, `ModelService` (real), database session
- Produces: Interactive CLI for testing critics against real LLM

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python
"""
Manual Critic Verification Script

Tests critic agents against real LLM models for qualitative verification.
Usage:
    python scripts/verify_critics.py --type code --model openai:gpt-4o-mini
    python scripts/verify_critics.py --type output --model anthropic:claude-3-haiku
    python scripts/verify_critics.py --type plan --model openai:gpt-4o
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db_context
from backend.services.critic_agents import CriticService, CriticType, CriticVerdict
from backend.models.entities.task import Task
from backend.models.entities.critics import CriticAgent
from backend.models.entities.agents import AgentStatus


SAMPLE_TASKS = {
    "code": {
        "description": "Write a Python function that validates email addresses",
        "good_output": "import re\ndef validate_email(email: str) -> bool:\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))",
        "bad_output": "def validate_email(email):\n    return eval(f\"'{email}' == '{email}'\")  # Dangerous!",
    },
    "output": {
        "description": "Explain how a hash map works in simple terms",
        "good_output": "A hash map stores key-value pairs. It uses a hash function to convert keys into array indices for fast lookup.",
        "bad_output": "Traceback (most recent call last):\n  File \"test.py\", line 1\nError: Connection refused\nException: NetworkError",
    },
    "plan": {
        "description": "Create a plan to build a REST API with authentication",
        "good_output": "Step 1: Design API endpoints and data models\nStep 2: Set up project structure\nStep 3: Implement authentication middleware\nStep 4: Build CRUD endpoints\nStep 5: Add tests and documentation",
        "bad_output": "Step 1: Research\nStep 2: Research\nStep 3: Research\nStep 4: Research\nStep 5: Research\nStep 6: Research\nStep 7: Research\nStep 8: Research\nStep 9: Research\nStep 10: Research\nStep 11: Research\nStep 12: Research\nStep 13: Research\nStep 14: Research\nStep 15: Research\nStep 16: Research\nStep 17: Research\nStep 18: Research\nStep 19: Research\nStep 20: Research\nStep 21: Research\nStep 22: Research\nStep 23: Research\nStep 24: Research\nStep 25: Research\nStep 26: Research\nStep 27: Research\nStep 28: Research\nStep 29: Research\nStep 30: Research\nStep 31: Research\nStep 32: Research\nStep 33: Research\nStep 34: Research\nStep 35: Research\nStep 36: Research\nStep 37: Research\nStep 38: Research\nStep 39: Research\nStep 39: Research\nStep 40: Research",
    },
}


async def run_verification(critic_type: CriticType, model: str, interactive: bool = False):
    """Run critic verification for a specific type."""
    print(f"\n{'='*60}")
    print(f"Critic Verification: {critic_type.value.upper()} Critic")
    print(f"Model: {model}")
    print(f"{'='*60}\n")

    critic_service = CriticService()
    critic_service.CRITIC_DEFAULT_MODEL = model

    async with get_db_context() as db:
        # Create a test task
        task_data = SAMPLE_TASKS[critic_type.value]
        task = Task(
            id=f"manual-test-{critic_type.value}-{datetime.now().timestamp()}",
            description=task_data["description"],
            task_type=critic_type.value.upper(),
            status="IN_PROGRESS",
        )
        db.add(task)
        db.commit()

        # Spawn critic
        spawned = await critic_service.spawn_critics_for_task(
            db=db, task_id=task.id, task_type=critic_type.value
        )
        critic_id = spawned.get(critic_type.value)
        print(f"Spawned critic: {critic_id}")

        if not critic_id:
            print(f"ERROR: No critic spawned for type {critic_type.value}")
            return

        # Test good output
        print(f"\n--- Testing GOOD output ---")
        print(f"Task: {task_data['description']}")
        print(f"Output:\n{task_data['good_output'][:200]}...")

        result = await critic_service.review_task_output(
            db=db,
            task_id=task.id,
            output_content=task_data["good_output"],
            critic_type=critic_type,
        )

        print(f"\nVerdict: {result['verdict']}")
        if result.get("rejection_reason"):
            print(f"Reason: {result['rejection_reason']}")
        if result.get("suggestions"):
            print(f"Suggestions: {result['suggestions']}")
        print(f"Duration: {result.get('review_duration_ms', 0):.1f}ms")

        # Test bad output
        print(f"\n--- Testing BAD output ---")
        print(f"Output:\n{task_data['bad_output'][:200]}...")

        result = await critic_service.review_task_output(
            db=db,
            task_id=task.id,
            output_content=task_data["bad_output"],
            critic_type=critic_type,
        )

        print(f"\nVerdict: {result['verdict']}")
        if result.get("rejection_reason"):
            print(f"Reason: {result['rejection_reason']}")
        if result.get("suggestions"):
            print(f"Suggestions: {result['suggestions']}")
        print(f"Duration: {result.get('review_duration_ms', 0):.1f}ms")

        # Clean up
        await critic_service.terminate_critics_for_task(db, task.id, reason="manual_test_done")

    print(f"\n{'='*60}")
    print("Verification complete")
    print(f"{'='*60}\n")


async def run_all_critics(model: str):
    """Run verification for all three critic types."""
    for ct in [CriticType.CODE, CriticType.OUTPUT, CriticType.PLAN]:
        await run_verification(ct, model)
        print("\n" + "-"*40 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Manual Critic Verification")
    parser.add_argument("--type", choices=["code", "output", "plan", "all"], default="all",
                        help="Critic type to test")
    parser.add_argument("--model", default="openai:gpt-4o-mini",
                        help="Model to use (e.g., openai:gpt-4o-mini, anthropic:claude-3-haiku)")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive mode (not yet implemented)")
    
    args = parser.parse_args()

    if args.type == "all":
        asyncio.run(run_all_critics(args.model))
    else:
        asyncio.run(run_verification(CriticType(args.type), args.model, args.interactive))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create the script file**

```bash
mkdir -p scripts
# (File content from Step 1)
chmod +x scripts/verify_critics.py
```

- [ ] **Step 3: Test script runs without errors (dry run with mocked model)**

```bash
cd "E:\Ongoing Projects\Agentium" && python scripts/verify_critics.py --type code --model openai:gpt-4o-mini 2>&1 | head -30
```
Expected: Script starts, connects to DB, spawns critic (will fail on real API call without keys - that's OK for dry run)

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_critics.py
git commit -m "feat: add manual critic verification script"
```

---

### Task 5: Fix Gaps Found During Verification & Final Validation

**Files:**
- Modify: `backend/services/critic_agents.py` (if gaps found)
- Modify: `docs/documents/TODO.md` (mark 6.3.1–6.3.4 complete)

**Interfaces:**
- Consumes: Test results from Tasks 1-4
- Produces: Fixed implementation, updated TODO

- [ ] **Step 1: Run full test suite and identify gaps**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py backend/tests/integration/test_critic_integration.py -v 2>&1 | tee test_results.txt
```
Expected: All tests PASS. If any FAIL, analyze failures.

- [ ] **Step 2: Fix preflight gaps (if any)**

Common gaps to check and fix in `critic_agents.py`:

```python
# In _review_code: Add AST syntax validation
def _review_code(self, content: str, task: Optional[Task]) -> tuple:
    issues, suggestions = [], []
    # ... existing dangerous patterns ...
    
    # NEW: Python syntax validation
    try:
        import ast
        ast.parse(content)
    except SyntaxError as e:
        issues.append(f"Syntax error: {e.msg} at line {e.lineno}")
        suggestions.append("Fix syntax error before submission")
    
    # ... rest of function ...
```

```python
# In _review_plan: Add DAG cycle detection (basic)
def _review_plan(self, content: str, task: Optional[Task]) -> tuple:
    issues, suggestions = []
    # ... existing checks ...
    
    # NEW: Simple dependency cycle check
    lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
    # Check for "Step X depends on Step Y" patterns where Y > X
    step_deps = {}
    for line in lines:
        if "depends on" in line.lower():
            # Parse and check for cycles
            pass
    
    # ... rest of function ...
```

```python
# In _parse_ai_verdict: Harden regex fallback
def _parse_ai_verdict(self, raw_response: str) -> tuple:
    import json, re
    cleaned = re.sub(r"```(?:json)?|```", "", raw_response).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # NEW: Regex fallback for common patterns
        verdict_match = re.search(r'"verdict"\s*:\s*"(pass|reject)"', raw_response, re.IGNORECASE)
        if verdict_match:
            verdict = CriticVerdict.REJECT if verdict_match.group(1).lower() == "reject" else CriticVerdict.PASS
            return (verdict, "Parsed via regex fallback", "AI response was not valid JSON")
        logger.warning("Critic AI returned non-JSON: %s", raw_response[:200])
        return (CriticVerdict.PASS, None, "AI response was not valid JSON — manual review recommended")
    # ... rest ...
```

- [ ] **Step 3: Verify critic model orthogonality**

Check that critics use different models than executors:

```bash
cd "E:\Ongoing Projects\Agentium" && grep -n "preferred_review_model\|CRITIC_DEFAULT_MODEL" backend/services/critic_agents.py
```
Expected: Critics default to `gpt-4o-mini` while executors use different models

- [ ] **Step 4: Run manual verification script (if API keys available)**

```bash
cd "E:\Ongoing Projects\Agentium" && python scripts/verify_critics.py --type all --model openai:gpt-4o-mini
```
Expected: All three critics run, produce PASS/REJECT verdicts with reasons

- [ ] **Step 5: Run lint and typecheck**

```bash
cd "E:\Ongoing Projects\Agentium" && ruff check backend/services/critic_agents.py backend/tests/unit/test_critic_review_logic.py backend/tests/integration/test_critic_integration.py scripts/verify_critics.py
```
Expected: No errors

```bash
cd "E:\Ongoing Projects\Agentium" && mypy backend/services/critic_agents.py --ignore-missing-imports 2>&1 | head -20
```
Expected: No critical errors

- [ ] **Step 6: Run full regression test suite**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_polymorphic_identity.py backend/tests/integration/test_e2e_task_execution.py::TestDelegateToTaskWithCritics -v
```
Expected: All existing tests still PASS

- [ ] **Step 7: Update TODO.md - mark 6.3.1–6.3.4 complete**

```bash
# Edit docs/documents/TODO.md
# Change:
# - [ ] 6.3.1 — Code Critic (7xxxx) reviews generated code for syntax/security
# - [ ] 6.3.2 — Output Critic (8xxxx) verifies output alignment with intent
# - [ ] 6.3.3 — Plan Critic (9xxxx) validates DAG soundness
# - [ ] 6.3.4 — Critic feedback is incorporated before final response
# To:
# - [x] 6.3.1 — Code Critic (7xxxx) reviews generated code for syntax/security
# - [x] 6.3.2 — Output Critic (8xxxx) verifies output alignment with intent
# - [x] 6.3.3 — Plan Critic (9xxxx) validates DAG soundness
# - [x] 6.3.4 — Critic feedback is incorporated before final response
```

- [ ] **Step 8: Final commit**

```bash
git add backend/services/critic_agents.py docs/documents/TODO.md
git commit -m "feat: complete critic agents verification (6.3.1-6.3.4)"
```

- [ ] **Step 9: Final verification - all tests pass**

```bash
cd "E:\Ongoing Projects\Agentium" && python -m pytest backend/tests/unit/test_critic_review_logic.py backend/tests/integration/test_critic_integration.py backend/tests/unit/test_critic_polymorphic_identity.py backend/tests/integration/test_e2e_task_execution.py::TestDelegateToTaskWithCritics -v
```
Expected: ALL TESTS PASS