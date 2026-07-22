"""
Chat History Auto-Pruning Service.

Implements two-tier pruning:
1. Soft-delete (is_deleted='Y') messages older than inactivity_days of conversation inactivity,
   but always retain last retain_count messages per conversation.
2. Hard-delete (DELETE) soft-deleted messages older than hard_delete_days.

Triggered daily via Celery Beat (chat_prune_task).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_, not_

from backend.models.entities.chat_message import ChatMessage, Conversation
from backend.models.database import SessionLocal
from backend.services.user_preference_service import UserPreferenceService

logger = logging.getLogger(__name__)

DEFAULT_INACTIVITY_DAYS = 7
DEFAULT_HARD_DELETE_DAYS = 30
DEFAULT_RETAIN_COUNT = 10


def get_prune_preferences(db: Session) -> Dict[str, Any]:
    """Get chat prune preferences from user preferences (system defaults)."""
    pref_svc = UserPreferenceService(db)
    return {
        "enabled": pref_svc.get_value("chat.prune_enabled", default=True),
        "inactivity_days": pref_svc.get_value("chat.prune_inactivity_days", default=DEFAULT_INACTIVITY_DAYS),
        "hard_delete_days": pref_svc.get_value("chat.prune_hard_delete_days", default=DEFAULT_HARD_DELETE_DAYS),
        "retain_count": pref_svc.get_value("chat.prune_retain_count", default=DEFAULT_RETAIN_COUNT),
    }


def get_conversations_due_for_soft_delete(
    db: Session,
    inactivity_days: int,
    retain_count: int,
) -> List[Conversation]:
    """
    Find conversations that have been inactive for longer than inactivity_days
    and have more than retain_count messages total.
    """
    cutoff = datetime.utcnow() - timedelta(days=inactivity_days)

    # Subquery: count messages per conversation (excluding already soft-deleted)
    msg_counts = (
        db.query(
            ChatMessage.conversation_id,
            func.count(ChatMessage.id).label("msg_count"),
        )
        .filter(
            ChatMessage.conversation_id.isnot(None),
            ChatMessage.is_deleted == "N",
        )
        .group_by(ChatMessage.conversation_id)
        .subquery()
    )

    conversations = (
        db.query(Conversation)
        .join(msg_counts, Conversation.id == msg_counts.c.conversation_id)
        .filter(
            Conversation.last_message_at < cutoff,
            Conversation.is_deleted == "N",
            msg_counts.c.msg_count > retain_count,
        )
        .all()
    )

    return conversations


def get_messages_to_soft_delete(
    db: Session,
    conversation_id: str,
    retain_count: int,
) -> List[ChatMessage]:
    """
    Get messages to soft-delete for a conversation: all but the last retain_count messages.
    Only considers non-deleted messages.
    """
    # Get the IDs of the last N messages to KEEP
    keep_ids_subq = (
        db.query(ChatMessage.id)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.is_deleted == "N",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(retain_count)
        .subquery()
    )

    # Get messages to delete: non-deleted messages NOT in the keep list
    messages_to_delete = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.is_deleted == "N",
            not_(ChatMessage.id.in_(keep_ids_subq)),
        )
        .all()
    )

    return messages_to_delete


def soft_delete_messages(db: Session, messages: List[ChatMessage], dry_run: bool = False) -> int:
    """Soft-delete a list of messages by setting is_deleted='Y'."""
    if not messages:
        return 0

    count = len(messages)
    if not dry_run:
        for msg in messages:
            msg.is_deleted = "Y"
            msg.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"Soft-deleted {count} messages")
    else:
        logger.info(f"DRY RUN: Would soft-delete {count} messages")

    return count


def get_soft_deleted_messages_due_for_hard_delete(
    db: Session,
    hard_delete_days: int,
) -> List[ChatMessage]:
    """
    Get soft-deleted messages older than hard_delete_days.
    """
    cutoff = datetime.utcnow() - timedelta(days=hard_delete_days)

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.is_deleted == "Y",
            ChatMessage.updated_at < cutoff,
        )
        .all()
    )

    return messages


def hard_delete_messages(db: Session, messages: List[ChatMessage], dry_run: bool = False) -> int:
    """Hard-delete (DELETE) a list of soft-deleted messages."""
    if not messages:
        return 0

    count = len(messages)
    if not dry_run:
        for msg in messages:
            db.delete(msg)
        db.commit()
        logger.info(f"Hard-deleted {count} messages")
    else:
        logger.info(f"DRY RUN: Would hard-delete {count} messages")

    return count


def run_chat_prune_task(
    dry_run: bool = False,
    override_inactivity_days: Optional[int] = None,
    override_hard_delete_days: Optional[int] = None,
    override_retain_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the full two-tier chat pruning task.

    Args:
        dry_run: If True, only report what would be deleted.
        override_inactivity_days: Override chat.prune_inactivity_days.
        override_hard_delete_days: Override chat.prune_hard_delete_days.
        override_retain_count: Override chat.prune_retain_count.

    Returns:
        Dict with soft_deleted_count, hard_deleted_count, conversations_affected, dry_run.
    """
    db: Session = SessionLocal()
    try:
        # Get preferences
        prefs = get_prune_preferences(db)
        if not prefs["enabled"]:
            return {
                "enabled": False,
                "soft_deleted_count": 0,
                "hard_deleted_count": 0,
                "conversations_affected": 0,
                "dry_run": dry_run,
            }

        inactivity_days = override_inactivity_days or prefs["inactivity_days"]
        hard_delete_days = override_hard_delete_days or prefs["hard_delete_days"]
        retain_count = override_retain_count or prefs["retain_count"]

        logger.info(
            f"Starting chat prune task: inactivity_days={inactivity_days}, "
            f"hard_delete_days={hard_delete_days}, retain_count={retain_count}, dry_run={dry_run}"
        )

        # Tier 1: Soft-delete
        conversations = get_conversations_due_for_soft_delete(
            db, inactivity_days, retain_count
        )

        total_soft_deleted = 0
        conversations_affected = 0

        for conv in conversations:
            messages_to_delete = get_messages_to_soft_delete(
                db, conv.id, retain_count
            )
            if messages_to_delete:
                total_soft_deleted += soft_delete_messages(db, messages_to_delete, dry_run)
                conversations_affected += 1

        # Tier 2: Hard-delete
        messages_to_hard_delete = get_soft_deleted_messages_due_for_hard_delete(
            db, hard_delete_days
        )
        total_hard_deleted = hard_delete_messages(db, messages_to_hard_delete, dry_run)

        result = {
            "enabled": True,
            "soft_deleted_count": total_soft_deleted,
            "hard_deleted_count": total_hard_deleted,
            "conversations_affected": conversations_affected,
            "dry_run": dry_run,
            "params": {
                "inactivity_days": inactivity_days,
                "hard_delete_days": hard_delete_days,
                "retain_count": retain_count,
            },
        }

        logger.info(f"Chat prune task completed: {result}")
        return result

    except Exception as exc:
        logger.error(f"Chat prune task failed: {exc}")
        db.rollback()
        raise
    finally:
        db.close()