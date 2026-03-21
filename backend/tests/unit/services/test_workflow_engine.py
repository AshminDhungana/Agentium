import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.workflow_engine import WorkflowEngine
from backend.models.entities.workflow import (
    Workflow, WorkflowVersion, WorkflowExecution, 
    WorkflowStep, WorkflowStatus, WorkflowExecutionStatus
)
import uuid

@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session

@pytest.fixture
def engine(mock_db):
    return WorkflowEngine(mock_db)

@pytest.mark.asyncio
async def test_create_workflow(engine, mock_db):
    name = "Test Workflow"
    description = "Test Description"
    template_json = {"steps": [{"step_index": 0, "type": "TASK"}]}
    cron = "0 * * * *"

    wf = await engine.create_workflow(name, description, template_json, cron)
    
    assert wf is not None
    assert mock_db.add.called
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_update_workflow_template(engine, mock_db):
    wf_id = str(uuid.uuid4())
    mock_wf = Workflow(id=wf_id, name="Old", version=1)
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_wf
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    new_template = {"steps": [{"step_index": 0, "type": "DELAY", "config": {"delay_seconds": 10}}]}
    wf = await engine.update_workflow_template(wf_id, new_template)
    
    assert wf.version == 2
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_trigger_workflow_execution(engine, mock_db):
    wf_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    
    mock_wf = Workflow(id=wf_id, name="Test")
    mock_result_wf = MagicMock()
    mock_result_wf.scalar_one_or_none.return_value = mock_wf
    
    mock_version = WorkflowVersion(id=version_id, workflow_id=wf_id, version=1, template_json={"steps": [{"step_index": 0, "type": "TASK"}]})
    mock_result_version = MagicMock()
    mock_result_version.scalar_one_or_none.return_value = mock_version
    
    mock_db.execute = AsyncMock(side_effect=[mock_result_wf, mock_result_version])
    
    with patch('backend.services.workflow_engine.workflow_step_runner.delay') as mock_celery:
        execution = await engine.trigger_workflow_execution(wf_id, {"target": "userA"})
        assert execution.status == WorkflowExecutionStatus.RUNNING
        assert execution.current_step_index == 0
        mock_celery.assert_called_once()
        assert mock_db.commit.called

@pytest.mark.asyncio
async def test_execute_step_condition_true(engine, mock_db):
    exec_id = str(uuid.uuid4())
    mock_execution = WorkflowExecution(
        id=exec_id, current_step_index=1, status=WorkflowExecutionStatus.RUNNING, context_data={"value": 10}
    )
    
    # Mock database to return the execution
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_execution
    
    # Mock step data (simulating hitting the database for step template)
    mock_version = WorkflowVersion(template_json={
        "steps": [
            {
                "step_index": 1,
                "type": "CONDITION",
                "config": {"condition": "context.value > 5"},
                "on_success_step": 2,
                "on_failure_step": 3
            }
        ]
    })
    mock_result_version = MagicMock()
    mock_result_version.scalar_one_or_none.return_value = mock_version
    
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_result_version])
    
    # Run the step processor
    with patch('backend.services.workflow_engine.workflow_step_runner.delay') as mock_celery:
        # Simulate execution method internally
        await engine._execute_condition_step(mock_execution, mock_version.template_json["steps"][0])
        
        assert mock_execution.current_step_index == 2
        assert mock_db.commit.called
        mock_celery.assert_called_with(exec_id)

@pytest.mark.asyncio
async def test_execute_step_condition_false(engine, mock_db):
    exec_id = str(uuid.uuid4())
    mock_execution = WorkflowExecution(
        id=exec_id, current_step_index=1, status=WorkflowExecutionStatus.RUNNING, context_data={"value": 1}
    )
    
    mock_step = {
        "step_index": 1,
        "type": "CONDITION",
        "config": {"condition": "context.value > 5"},
        "on_success_step": 2,
        "on_failure_step": 3
    }
    
    with patch('backend.services.workflow_engine.workflow_step_runner.delay') as mock_celery:
        await engine._execute_condition_step(mock_execution, mock_step)
        
        assert mock_execution.current_step_index == 3
        mock_celery.assert_called_with(exec_id)

@pytest.mark.asyncio
async def test_eta_calculator(engine, mock_db):
    wf_id = str(uuid.uuid4())
    
    # Mock average duration result
    mock_result = MagicMock()
    mock_result.scalar.return_value = 120.5 # 120.5 seconds average
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    eta = await engine.calculate_workflow_eta(wf_id)
    assert eta == 120.5
