"""Verify workflow_tasks.py tasks execute correctly via Celery."""
import sys
import os
import uuid

def verify_workflow_tasks() -> dict:
    """Verify fire_reminder and execute_deferred_subtask work via Celery."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    # Import task modules to register tasks
    from backend.services.tasks import workflow_tasks
    from backend.services.tasks import task_executor

    from backend.celery_app import celery_app
    from verification_utils import temp_db_session

    results = {
        "fire_reminder": {"imported": False, "executed": False, "db_update": False, "details": {}},
        "execute_deferred_subtask": {"imported": False, "executed": False, "db_update": False, "details": {}},
        "status": "fail"
    }

    # Test fire_reminder
    fire_reminder = celery_app.tasks.get('agentium.tasks.workflow_tasks.fire_reminder')
    if fire_reminder:
        results["fire_reminder"]["imported"] = True
        try:
            with temp_db_session() as db:
                # Ensure we have an active channel
                from backend.models.entities.channels import ExternalChannel, ChannelStatus
                channel = db.query(ExternalChannel).filter(
                    ExternalChannel.status == ChannelStatus.ACTIVE
                ).first()

                if not channel:
                    # Create a test channel
                    channel = ExternalChannel(
                        name="test_verification_channel",
                        channel_type="test",
                        status=ChannelStatus.ACTIVE,
                        config="{}"
                    )
                    db.add(channel)
                    db.commit()
                    db.refresh(channel)

                # Execute task
                async_result = fire_reminder.apply_async(args=["Test reminder message"])
                task_result = async_result.get(timeout=15)

                results["fire_reminder"]["executed"] = True
                results["fire_reminder"]["details"]["result"] = task_result

                # Verify ExternalMessage was created
                from backend.models.entities.channels import ExternalMessage
                msg = db.query(ExternalMessage).filter(
                    ExternalMessage.content.like("%Test reminder message%")
                ).order_by(ExternalMessage.created_at.desc()).first()

                if msg:
                    results["fire_reminder"]["db_update"] = True
                    results["fire_reminder"]["details"]["message_id"] = str(msg.id)
                    # Cleanup
                    db.delete(msg)
                    db.commit()
                else:
                    results["fire_reminder"]["details"]["error"] = "ExternalMessage not created"

        except Exception as e:
            results["fire_reminder"]["details"]["error"] = str(e)

    # Test execute_deferred_subtask
    exec_deferred = celery_app.tasks.get('agentium.tasks.workflow_tasks.execute_deferred_subtask')
    if exec_deferred:
        results["execute_deferred_subtask"]["imported"] = True
        try:
            with temp_db_session() as db:
                from backend.models.entities.workflow import WorkflowExecution, WorkflowSubTask
                from datetime import datetime

                # Create test workflow execution
                wf_id = f"test_wf_{uuid.uuid4().hex[:8]}"
                workflow = WorkflowExecution(
                    workflow_id=wf_id,
                    status="running",
                    context_data={},
                    original_message="Verification test"
                )
                db.add(workflow)

                # Create subtask
                subtask = WorkflowSubTask(
                    workflow_id=wf_id,
                    intent="test_intent",
                    params={"test": "value"},
                    step_index=0,
                    status="pending"
                )
                db.add(subtask)
                db.commit()

                # Execute task
                async_result = exec_deferred.apply_async(args=[wf_id, "test_intent", {"test": "value"}])
                task_result = async_result.get(timeout=15)

                results["execute_deferred_subtask"]["executed"] = True
                results["execute_deferred_subtask"]["details"]["result"] = task_result

                # Verify subtask updated
                db.refresh(subtask)
                if subtask.status == "completed" and subtask.result is not None:
                    results["execute_deferred_subtask"]["db_update"] = True
                    results["execute_deferred_subtask"]["details"]["subtask_status"] = subtask.status
                else:
                    results["execute_deferred_subtask"]["details"]["error"] = f"Subtask not updated: status={subtask.status}"

                # Verify workflow context_data updated
                db.refresh(workflow)
                if workflow.context_data and "test_intent" in workflow.context_data:
                    results["execute_deferred_subtask"]["details"]["workflow_context_updated"] = True

                # Cleanup
                db.delete(subtask)
                db.delete(workflow)
                db.commit()

        except Exception as e:
            results["execute_deferred_subtask"]["details"]["error"] = str(e)

    # Overall status
    fire_ok = results["fire_reminder"]["imported"] and results["fire_reminder"]["executed"]
    exec_ok = results["execute_deferred_subtask"]["imported"] and results["execute_deferred_subtask"]["executed"]

    if fire_ok and exec_ok:
        results["status"] = "pass"
    elif fire_ok or exec_ok:
        results["status"] = "warn"
    else:
        results["status"] = "fail"

    return results