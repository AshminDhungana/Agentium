"""
Integration tests for CriticService full review flow.

Tests the complete review_task_output() lifecycle with database:
- Spawn critics for task
- Submit output for review (preflight -> AI -> verdict)
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
from backend.services.acceptance_criteria import AcceptanceCriteriaService, AcceptanceCriterion, CriterionValidator


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
            task_type=TaskType.CODE_GENERATION,
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
            task_type=TaskType.PLANNING,
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
            task_type=TaskType.CODE_GENERATION,
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
                metric="has_function_def",
                threshold="def ",
                validator=CriterionValidator.CODE,
                is_mandatory=True,
                description="Output contains a function definition",
            ),
            AcceptanceCriterion(
                metric="no_eval",
                threshold="eval(",
                validator=CriterionValidator.CODE,
                is_mandatory=True,
                description="No eval() usage",
            ),
        ]
        task = Task(
            id="test-task-criteria-1",
            description="Write safe Python code",
            task_type=TaskType.CODE_GENERATION,
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
            task_type=TaskType.CODE_GENERATION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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
            task_type=TaskType.CODE_GENERATION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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
            task_type=TaskType.PLANNING,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="plan")

        result = await critic_service.review_task_output(
            db=seeded_db,
            task_id=task.id,
            output_content="Step 1: Research\nStep 1: Research\nStep 3: Build",
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
            task_type=TaskType.CODE_GENERATION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        # First review - REJECT
        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "reject", "reason": "Missing docs", "suggestions": "Add docstrings"}', "model": "test", "tokens_used": 10}
            
            result1 = await critic_service.review_task_output(
                db=seeded_db, task_id=task.id, output_content="def f(): pass",
                critic_type=CriticType.CODE, retry_count=0
            )

        assert result1["verdict"] == CriticVerdict.REJECT.value
        critic_id_1 = result1["critic_id"]

        # Second review (retry) - PASS
        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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
            task_type=TaskType.CODE_GENERATION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        # Simulate 5 rejections
        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "reject", "reason": "Still bad", "suggestions": "Fix it"}', "model": "test", "tokens_used": 10}
            
            for i in range(5):
                result = await critic_service.review_task_output(
                    db=seeded_db, task_id=task.id, output_content="bad code",
                    critic_type=CriticType.CODE, retry_count=i
                )
                assert result["verdict"] == CriticVerdict.REJECT.value

        # 6th attempt (retry_count=5 >= max_retries=5) should ESCALATE
        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "reject", "reason": "Still bad", "suggestions": "Fix it"}', "model": "test", "tokens_used": 10}
            
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

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}
            
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
        """First critic REJECT, second critic PASS -> conditional PASS."""
        task = Task(
            id="test-consensus-1",
            description="Write code",
            task_type=TaskType.CODE_GENERATION,
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
                return {"content": '{"verdict": "reject", "reason": "Issue found", "suggestions": "Fix it"}', "model": "test", "tokens_used": 10}
            return {"content": '{"verdict": "pass", "reason": null, "suggestions": null}', "model": "test", "tokens_used": 10}

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen:
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
            task_type=TaskType.CODE_GENERATION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
        )
        seeded_db.add(task)
        seeded_db.commit()

        await critic_service.spawn_critics_for_task(db=seeded_db, task_id=task.id, task_type="code")

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen, \
             patch("backend.services.critic_agents.get_knowledge_service") as mock_ks:
            
            mock_gen.return_value = {"content": '{"verdict": "reject", "reason": "SQL injection risk", "suggestions": "Use parameterized queries"}', "model": "test", "tokens_used": 10}
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