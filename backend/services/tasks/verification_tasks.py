"""
Celery tasks for agent verification.
"""
import asyncio
import logging
from celery import shared_task
from backend.celery_app import celery_app
from backend.models.database import get_db_context
from backend.services.initialization_service import InitializationService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async coroutine, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)
    else:
        # Running in an async context, create a new task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()


@celery_app.task(
    name="backend.services.tasks.verification_tasks.verify_agents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def verify_agents_task(self):
    """
    Periodic task to verify and repair missing genesis agents.
    
    Runs every AGENT_VERIFICATION_INTERVAL_SECONDS (default 300s).
    """
    try:
        with get_db_context() as db:
            init_service = InitializationService(db)
            result = _run_async(init_service.verify_and_repair(db))
            logger.info(f"Periodic agent verification: {result['status']} - checked: {result['checked']}, recreated: {result['recreated']}")
            return result
    except Exception as e:
        logger.error(f"Agent verification task failed: {e}")
        # Retry on transient failures
        raise self.retry(exc=e)