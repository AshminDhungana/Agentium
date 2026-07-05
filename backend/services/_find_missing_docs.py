"""Find public methods without docstrings in the specified files."""
import logging


import ast
import sys
from pathlib import Path
from typing import List, Tuple
logger = logging.getLogger(__name__)

FILES = [
    "alert_manager.py", "amendment_service.py", "api_manager.py", "audio_service.py",
    "audit_service.py", "autonomous_learning.py", "capability_registry.py",
    "context_manager.py", "host_access.py", "knowledge_governance.py",
    "knowledge_service.py", "mcp_tool_bridge.py", "message_bus.py",
    "model_allocation.py", "plugin_marketplace_service.py", "predictive_scaling.py",
    "pricing_sync_service.py", "prompt_template_manager.py", "push_notification_service.py",
    "rbac_service.py", "skill_manager.py", "skill_rag.py",
    "user_preference_service.py", "channels/whatsapp_unified.py",
    "idle_tasks/preference_optimizer.py", "tasks/workflow_tasks.py",
]


if __name__ == "__main__":
    base = Path("backend/services")
    for rel_file in FILES:
        file_path = base / rel_file
        if not file_path.exists():
            logger.info(f"NOT FOUND: {rel_file}")
            continue
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.error(f"SYNTAX ERROR in {rel_file}: {e}")
            continue
        # Collect classes and their public methods
        classes = {}
        module_methods = []
        for top in tree.body:
            if isinstance(top, ast.ClassDef):
                class_missing = []
                for item in top.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Public: not starting with _, or special __init__
                        is_public = (not item.name.startswith("_") or item.name == "__init__")
                        if is_public:
                            has_doc = ast.get_docstring(item) is not None
                            if not has_doc:
                                class_missing.append((item.name, item.lineno))
                if class_missing:
                    classes[top.name] = class_missing
            elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_public = not top.name.startswith("_")
                if is_public:
                    has_doc = ast.get_docstring(top) is not None
                    if not has_doc:
                        module_methods.append((top.name, top.lineno))

        total = sum(len(v) for v in classes.values()) + len(module_methods)
        if total > 0:
            logger.info(f"{rel_file}: {total} missing")
            if module_methods:
                for name, lineno in module_methods:
                    logger.info(f"  module {name}@{lineno}")
            for cls_name, methods in classes.items():
                if methods:
                    for name, lineno in methods:
                        logger.info(f"  {cls_name}.{name}@{lineno}")
        else:
            logger.info(f"{rel_file}: 0 missing")