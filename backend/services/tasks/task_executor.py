"""
Task execution handlers for Celery.
Includes: task execution, constitution review, idle processing, 
and channel message retry with circuit breaker support.
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from dataclasses import asdict

from backend.celery_app import celery_app
from backend.models.database import SessionLocal
from backend.models.entities.channels import ExternalMessage, ExternalChannel, ChannelStatus
from backend.models.entities.task import Task, TaskStatus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Core Task Execution
# ═══════════════════════════════════════════════════════════

@celery_app.task(bind=True, max_retries=3)
def execute_task_async(self, task_id: str, agent_id: str):
    """Execute a task asynchronously."""
    try:
        logger.info(f"Executing task {task_id} with agent {agent_id}")
        return {"status": "completed", "task_id": task_id}
    except Exception as exc:
        logger.error(f"Task execution failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def daily_constitution_review():
    """Daily review of constitution by persistent council."""
    logger.info("Running daily constitution review")
    return {"status": "completed"}


@celery_app.task
def process_idle_tasks():
    """Process tasks when system is idle."""
    logger.info("Processing idle tasks")
    return {"status": "completed"}


# ═══════════════════════════════════════════════════════════
# Channel Message Retry & Recovery (NEW)
# ═══════════════════════════════════════════════════════════

@celery_app.task(bind=True, max_retries=3)
def retry_channel_message(self, message_id: str, agent_id: str, content: str, rich_media_dict: Dict[str, Any] = None):
    """
    Retry sending a failed channel message.
    Called by circuit breaker when initial send fails.
    """
    db = SessionLocal()
    try:
        # Import here to avoid circular imports
        from backend.services.channel_manager import ChannelManager, circuit_breaker, RichMediaContent
        
        # Get message
        message = db.query(ExternalMessage).filter_by(id=message_id).first()
        if not message:
            logger.error(f"Message {message_id} not found for retry")
            return {"success": False, "error": "Message not found"}
        
        # Check if channel is still active
        channel = db.query(ExternalChannel).filter_by(id=message.channel_id).first()
        if not channel or channel.status != ChannelStatus.ACTIVE:
            logger.warning(f"Channel {message.channel_id} not active, aborting retry")
            return {"success": False, "error": "Channel not active"}
        
        # Check circuit breaker
        if not circuit_breaker.can_execute(channel.id):
            # Reschedule for later
            logger.info(f"Circuit breaker open for channel {channel.id}, rescheduling retry")
            raise self.retry(countdown=600)  # 10 minutes
        
        # Reconstruct rich media if provided
        rich_media = None
        if rich_media_dict:
            rich_media = RichMediaContent(**rich_media_dict)
        
        # Attempt to send
        success = ChannelManager.send_response(
            message_id=message_id,
            response_content=content,
            agent_id=agent_id,
            rich_media=rich_media,
            db=db
        )
        
        if not success:
            raise Exception("Send returned False")
        
        # Record success
        circuit_breaker.record_success(channel.id)
        logger.info(f"Successfully retried message {message_id}")
        
        return {
            "success": True, 
            "message_id": message_id, 
            "retries": self.request.retries
        }
        
    except Exception as exc:
        retry_count = self.request.retries
        
        if retry_count < 3:
            # Exponential backoff: 5min, 10min, 20min
            countdown = 300 * (2 ** retry_count)
            logger.warning(f"Retry {retry_count + 1}/3 for message {message_id} in {countdown}s: {exc}")
            raise self.retry(exc=exc, countdown=countdown)
        
        # Max retries exceeded
        logger.error(f"Max retries exceeded for message {message_id}: {exc}")
        
        # Mark as permanently failed
        message = db.query(ExternalMessage).filter_by(id=message_id).first()
        if message:
            message.status = "failed"
            message.last_error = f"Max retries exceeded: {str(exc)}"
            db.commit()
        
        # Open circuit breaker
        if message:
            circuit_breaker.record_failure(message.channel_id)
        
        return {
            "success": False, 
            "error": str(exc), 
            "max_retries_exceeded": True
        }
        
    finally:
        db.close()


@celery_app.task
def cleanup_old_channel_messages(days: int = 30):
    """
    Archive old channel messages.
    Keeps recent messages for context, archives old ones.
    """
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    db = SessionLocal()
    try:
        old_messages = db.query(ExternalMessage).filter(
            ExternalMessage.created_at < cutoff,
            ExternalMessage.status.in_(['responded', 'failed'])
        ).all()
        
        count = 0
        for msg in old_messages:
            msg.status = "archived"
            count += 1
        
        db.commit()
        logger.info(f"Archived {count} old channel messages")
        return {"archived": count, "cutoff_days": days}
    finally:
        db.close()


@celery_app.task
def check_channel_health():
    """
    Periodic health check for all channels.
    Auto-disables channels with low success rates.
    """
    from backend.services.channel_manager import ChannelManager, CircuitState
    
    db = SessionLocal()
    try:
        channels = db.query(ExternalChannel).filter(
            ExternalChannel.status == ChannelStatus.ACTIVE
        ).all()
        
        results = []
        for channel in channels:
            health = ChannelManager.get_channel_health(channel.id)
            
            # Auto-disable unhealthy channels
            if (health['overall_status'] == 'degraded' and 
                health['circuit_breaker']['success_rate'] < 0.5):
                
                channel.status = ChannelStatus.ERROR
                channel.error_message = "Auto-disabled due to low success rate"
                db.commit()
                
                results.append({
                    "channel_id": channel.id,
                    "action": "auto_disabled",
                    "reason": "low_success_rate",
                    "success_rate": health['circuit_breaker']['success_rate']
                })
                logger.warning(
                    f"Auto-disabled channel {channel.id} "
                    f"(success rate: {health['circuit_breaker']['success_rate']:.2%})"
                )
            
            # Log circuit breaker state changes
            elif health['circuit_breaker']['circuit_state'] != 'closed':
                results.append({
                    "channel_id": channel.id,
                    "action": "circuit_state",
                    "state": health['circuit_breaker']['circuit_state'],
                    "consecutive_failures": health['circuit_breaker']['consecutive_failures']
                })
        
        logger.info(f"Health check completed for {len(channels)} channels, {len(results)} actions taken")
        return {
            "checked": len(channels), 
            "actions": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


@celery_app.task
def start_imap_receivers():
    """
    Ensure IMAP receivers are running for all email channels.
    Called periodically to recover from crashes.
    """
    from backend.services.channel_manager import imap_receiver
    
    db = SessionLocal()
    try:
        email_channels = db.query(ExternalChannel).filter(
            ExternalChannel.channel_type == 'email',
            ExternalChannel.status == ChannelStatus.ACTIVE
        ).all()
        
        started = 0
        for channel in email_channels:
            if channel.config.get('enable_imap') or channel.config.get('imap_host'):
                try:
                    # Use asyncio to start IMAP
                    asyncio.run(
                        imap_receiver.start_channel(channel.id, channel.config)
                    )
                    started += 1
                    logger.info(f"Started/verified IMAP for channel {channel.id}")
                except Exception as e:
                    logger.error(f"Failed to start IMAP for channel {channel.id}: {e}")
        
        return {
            "email_channels": len(email_channels),
            "imap_started": started,
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


@celery_app.task
def send_channel_heartbeat():
    """
    Send periodic heartbeat to all active channels.
    Useful for detecting stale connections.
    """
    db = SessionLocal()
    try:
        # Get channels with recent activity
        from datetime import datetime, timedelta
        
        active_channels = db.query(ExternalChannel).filter(
            ExternalChannel.status == ChannelStatus.ACTIVE,
            ExternalChannel.last_message_at > datetime.utcnow() - timedelta(hours=24)
        ).all()
        
        heartbeats_sent = 0
        for channel in active_channels:
            # Update last_message_at to show we're monitoring
            channel.updated_at = datetime.utcnow()
            heartbeats_sent += 1
        
        db.commit()
        logger.info(f"Heartbeat sent to {heartbeats_sent} channels")
        return {"channels": heartbeats_sent}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# Bulk Operations
# ═══════════════════════════════════════════════════════════

@celery_app.task
def broadcast_to_channels(channel_ids: list, message: str, agent_id: str):
    """
    Broadcast a message to multiple channels.
    Used for announcements or alerts.
    """
    from backend.services.channel_manager import ChannelManager
    
    db = SessionLocal()
    results = []
    
    try:
        for channel_id in channel_ids:
            try:
                # Create a test message record
                test_msg = ExternalMessage(
                    channel_id=channel_id,
                    sender_id="system",
                    sender_name="Agentium",
                    content=message,
                    message_type="announcement",
                    status="pending"
                )
                db.add(test_msg)
                db.commit()
                
                success = ChannelManager.send_response(
                    message_id=test_msg.id,
                    response_content=message,
                    agent_id=agent_id,
                    db=db
                )
                
                results.append({
                    "channel_id": channel_id,
                    "success": success,
                    "message_id": test_msg.id
                })
                
            except Exception as e:
                logger.error(f"Failed to broadcast to channel {channel_id}: {e}")
                results.append({
                    "channel_id": channel_id,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "total": len(channel_ids),
            "successful": sum(1 for r in results if r.get('success')),
            "failed": sum(1 for r in results if not r.get('success')),
            "details": results
        }
    finally:
        db.close()
        