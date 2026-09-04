#!/usr/bin/env python
"""
Manual Critic Verification Script

Tests critic agents against real LLM models for qualitative verification.
Usage:
    python scripts/verify_critics.py --type code --model openai:gpt-4o-mini
    python scripts/verify_critics.py --type output --model anthropic:claude-3-haiku
    python scripts/verify_critics.py --type plan --model openai:gpt-4o
    python scripts/verify_critics.py --type all --model openai:gpt-4o-mini
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db_context
from backend.services.critic_agents import CriticService, CriticType, CriticVerdict
from backend.models.entities.task import Task
from backend.models.entities.critics import CriticAgent
from backend.models.entities.agents import AgentStatus


SAMPLE_TASKS = {
    "code": {
        "description": "Write a Python function that validates email addresses",
        "good_output": "import re\ndef validate_email(email: str) -> bool:\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))",
        "bad_output": "def validate_email(email):\n    return eval(f\"'{email}' == '{email}'\")  # Dangerous!",
    },
    "output": {
        "description": "Explain how a hash map works in simple terms",
        "good_output": "A hash map stores key-value pairs. It uses a hash function to convert keys into array indices for fast lookup.",
        "bad_output": "Traceback (most recent call last):\n  File \"test.py\", line 1\nError: Connection refused\nException: NetworkError",
    },
    "plan": {
        "description": "Create a plan to build a REST API with authentication",
        "good_output": "Step 1: Design API endpoints and data models\nStep 2: Set up project structure\nStep 3: Implement authentication middleware\nStep 4: Build CRUD endpoints\nStep 5: Add tests and documentation",
        "bad_output": "Step 1: Research\nStep 2: Research\nStep 3: Research\nStep 4: Research\nStep 5: Research\nStep 6: Research\nStep 7: Research\nStep 8: Research\nStep 9: Research\nStep 10: Research\nStep 11: Research\nStep 12: Research\nStep 13: Research\nStep 14: Research\nStep 15: Research\nStep 16: Research\nStep 17: Research\nStep 18: Research\nStep 19: Research\nStep 20: Research\nStep 21: Research\nStep 22: Research\nStep 23: Research\nStep 24: Research\nStep 25: Research\nStep 26: Research\nStep 27: Research\nStep 28: Research\nStep 29: Research\nStep 30: Research\nStep 31: Research\nStep 32: Research\nStep 33: Research\nStep 34: Research\nStep 35: Research\nStep 36: Research\nStep 37: Research\nStep 38: Research\nStep 39: Research\nStep 39: Research\nStep 40: Research",
    },
}


async def run_verification(critic_type: CriticType, model: str, interactive: bool = False):
    """Run critic verification for a specific type."""
    print(f"\n{'='*60}")
    print(f"Critic Verification: {critic_type.value.upper()} Critic")
    print(f"Model: {model}")
    print(f"{'='*60}\n")

    critic_service = CriticService()
    critic_service.CRITIC_DEFAULT_MODEL = model

    async with get_db_context() as db:
        # Create a test task
        task_data = SAMPLE_TASKS[critic_type.value]
        task = Task(
            id=f"manual-test-{critic_type.value}-{datetime.now().timestamp()}",
            description=task_data["description"],
            task_type=critic_type.value.upper(),
            status="IN_PROGRESS",
        )
        db.add(task)
        db.commit()

        # Spawn critic
        spawned = await critic_service.spawn_critics_for_task(
            db=db, task_id=task.id, task_type=critic_type.value
        )
        critic_id = spawned.get(critic_type.value)
        print(f"Spawned critic: {critic_id}")

        if not critic_id:
            print(f"ERROR: No critic spawned for type {critic_type.value}")
            return

        # Test good output
        print(f"\n--- Testing GOOD output ---")
        print(f"Task: {task_data['description']}")
        print(f"Output:\n{task_data['good_output'][:200]}...")

        result = await critic_service.review_task_output(
            db=db,
            task_id=task.id,
            output_content=task_data["good_output"],
            critic_type=critic_type,
        )

        print(f"\nVerdict: {result['verdict']}")
        if result.get("rejection_reason"):
            print(f"Reason: {result['rejection_reason']}")
        if result.get("suggestions"):
            print(f"Suggestions: {result['suggestions']}")
        print(f"Duration: {result.get('review_duration_ms', 0):.1f}ms")

        # Test bad output
        print(f"\n--- Testing BAD output ---")
        print(f"Output:\n{task_data['bad_output'][:200]}...")

        result = await critic_service.review_task_output(
            db=db,
            task_id=task.id,
            output_content=task_data["bad_output"],
            critic_type=critic_type,
        )

        print(f"\nVerdict: {result['verdict']}")
        if result.get("rejection_reason"):
            print(f"Reason: {result['rejection_reason']}")
        if result.get("suggestions"):
            print(f"Suggestions: {result['suggestions']}")
        print(f"Duration: {result.get('review_duration_ms', 0):.1f}ms")

        # Clean up
        await critic_service.terminate_critics_for_task(db, task.id, reason="manual_test_done")

    print(f"\n{'='*60}")
    print("Verification complete")
    print(f"{'='*60}\n")


async def run_all_critics(model: str):
    """Run verification for all three critic types."""
    for ct in [CriticType.CODE, CriticType.OUTPUT, CriticType.PLAN]:
        await run_verification(ct, model)
        print("\n" + "-"*40 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Manual Critic Verification")
    parser.add_argument("--type", choices=["code", "output", "plan", "all"], default="all",
                        help="Critic type to test")
    parser.add_argument("--model", default="openai:gpt-4o-mini",
                        help="Model to use (e.g., openai:gpt-4o-mini, anthropic:claude-3-haiku)")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive mode (not yet implemented)")
    
    args = parser.parse_args()

    if args.type == "all":
        asyncio.run(run_all_critics(args.model))
    else:
        asyncio.run(run_verification(CriticType(args.type), args.model, args.interactive))


if __name__ == "__main__":
    main()