#!/usr/bin/env python
"""
Verify all task names in beat_schedule match actual @celery_app.task definitions.
"""
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all modules in the include list to register their tasks
INCLUDE_MODULES = [
    "backend.services.tasks.task_executor",
    "backend.services.tasks.scheduled_task_dispatcher",
    "backend.services.tasks.workflow_tasks",
    "backend.services.tasks.reindex_knowledge",
    "backend.services.tasks.verification_tasks",
    "backend.services.audit.audit_processor",
    "backend.services.monitoring.health_checks",
    "backend.services.workflow_engine",
]

for module in INCLUDE_MODULES:
    __import__(module)

from backend.celery_app import celery_app

def verify_beat_schedule():
    beat_schedule = celery_app.conf.beat_schedule
    registered_tasks = set(celery_app.tasks.keys())

    print(f"Registered tasks: {len(registered_tasks)}")
    print(f"Beat schedule entries: {len(beat_schedule)}")

    mismatches = []
    for schedule_name, config in beat_schedule.items():
        task_name = config.get("task")
        if task_name and task_name not in registered_tasks:
            mismatches.append({
                "schedule": schedule_name,
                "expected_task": task_name,
                "available_tasks": [t for t in registered_tasks if task_name.split(".")[-1] in t]
            })
            print(f"[MISMATCH] {schedule_name} -> {task_name}")
        else:
            print(f"[OK] {schedule_name} -> {task_name}")

    return mismatches

if __name__ == "__main__":
    mismatches = verify_beat_schedule()
    if mismatches:
        print(f"\n{len(mismatches)} task name mismatch(es) found")
        sys.exit(1)
    else:
        print("\nAll beat schedule task names match registered tasks")
        sys.exit(0)