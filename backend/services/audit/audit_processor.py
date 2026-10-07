"""
Audit log processing.
"""

from backend.celery_app import celery_app

from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)
@celery_app.task(name="agentium.audit.audit_processor.process_audit_batch")
def process_audit_batch():
    """Process batch of audit logs."""
    logger.info("Processing audit batch")
    return {"status": "completed"}