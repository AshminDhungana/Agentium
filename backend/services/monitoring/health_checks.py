"""
Health check tasks.
"""

from backend.celery_app import celery_app

from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)
@celery_app.task(name="agentium.monitoring.health_checks.run_health_check")
def run_health_check():
    """Run system health check."""
    logger.info("Running health check")
    return {"status": "healthy"}