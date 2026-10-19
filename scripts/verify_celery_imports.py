#!/usr/bin/env python
"""
Verify all modules in celery_app.py include list are importable.
"""
import sys
import importlib
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODULES = [
    "backend.services.tasks.task_executor",
    "backend.services.tasks.scheduled_task_dispatcher",
    "backend.services.tasks.workflow_tasks",
    "backend.services.tasks.reindex_knowledge",
    "backend.services.tasks.verification_tasks",
    "backend.services.audit.audit_processor",
    "backend.services.monitoring.health_checks",
    "backend.services.workflow_engine",
]

def verify_imports():
    results = {}
    for module in MODULES:
        try:
            importlib.import_module(module)
            results[module] = {"status": "OK", "error": None}
            print(f"[OK] {module}")
        except Exception as e:
            results[module] = {"status": "FAIL", "error": str(e)}
            print(f"[FAIL] {module}: {e}")
    return results

if __name__ == "__main__":
    results = verify_imports()
    failed = [m for m, r in results.items() if r["status"] == "FAIL"]
    if failed:
        print(f"\n{len(failed)} module(s) failed to import")
        sys.exit(1)
    else:
        print(f"\nAll {len(MODULES)} modules imported successfully")
        sys.exit(0)