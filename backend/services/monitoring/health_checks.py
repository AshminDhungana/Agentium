"""
Health check tasks.
"""
import logging
from backend.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task
def run_health_check():
    """Run system health check."""
    logger.info("Running health check")
    return {"status": "healthy"}