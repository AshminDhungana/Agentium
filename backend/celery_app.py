"""
Celery configuration for Agentium background tasks.
"""
import os
from celery import Celery
from celery.signals import worker_ready

# Set Django-like settings module (we use our backend config)
os.environ.setdefault('PYTHONPATH', '/app')

# Create Celery app
celery_app = Celery(
    'agentium',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0'),
    include=[
        'backend.services.tasks.task_executor',
        'backend.services.audit.audit_processor',
        'backend.services.monitoring.health_checks',
    ]
)

# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes max per task
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    result_expires=3600,  # Results expire after 1 hour
    
    # Fix: Use /tmp for celery beat schedule (writable location)
    beat_schedule_filename='/tmp/celerybeat-schedule',
    beat_scheduler='celery.beat.PersistentScheduler',
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'health-check-every-5-minutes': {
        'task': 'backend.services.monitoring.health_checks.run_health_check',
        'schedule': 300.0,  # 5 minutes
    },
    'constitution-daily-review': {
        'task': 'backend.services.tasks.task_executor.daily_constitution_review',
        'schedule': 86400.0,  # 24 hours
    },
    'idle-task-processor': {
        'task': 'backend.services.tasks.task_executor.process_idle_tasks',
        'schedule': 60.0,  # Every minute when idle
    },
}

@worker_ready.connect
def on_worker_ready(**kwargs):
    """Called when Celery worker starts."""
    print("🥬 Celery worker ready for Agentium tasks")


if __name__ == '__main__':
    celery_app.start()