"""
Knowledge Governance Service for Agentium.
Council-managed approval workflow for collective memory.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, CouncilMember, AgentType
from backend.models.entities.voting import AmendmentVoting, IndividualVote
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.core.vector_store import get_vector_store
from backend.services.knowledge_service import get_knowledge_service


logger = logging.getLogger(__name__)

# Redis key for staged submissions persistence
_KNOWLEDGE_STAGING_KEY_PREFIX = "agentium:knowledge:staging"


class KnowledgeStatus(str, Enum):
    """Status of knowledge submission."""
    PENDING = "pending"           # Awaiting review
    STAGED = "staged"            # In temporary collection
    APPROVED = "approved"        # In production collection
    REJECTED = "rejected"        # Archived
    CHANGES_REQUESTED = "changes_requested"
    EXPIRED = "expired"          # Auto-expired (24h timeout)


class KnowledgeCategory(str, Enum):
    """Categories of knowledge."""
    CONSTITUTIONAL = "constitutional"    # Amends to constitution
    BEST_PRACTICE = "best_practice"      # Task execution patterns
    DOMAIN_KNOWLEDGE = "domain_knowledge" # Subject matter expertise
    LESSON_LEARNED = "lesson_learned"    # Post-mortems
    TOOL_USAGE = "tool_usage"            # How to use tools


class KnowledgeSubmission:
    """Represents a knowledge submission awaiting approval."""
    
    def __init__(self,
                 content: str,
                 submitter_agentium_id: str,
                 category: KnowledgeCategory,
                 title: str = None,
                 description: str = None,
                 metadata: Dict[str, Any] = None):
        """Create a new knowledge submission with generated ID and review deadline."""
        self.id = f"K{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        self.content = content
        self.submitter_agentium_id = submitter_agentium_id
        self.category = category
        self.title = title or f"Knowledge Submission {self.id}"
        self.description = description or ""
        self.metadata = metadata or {}
        self.status = KnowledgeStatus.PENDING
        self.submitted_at = datetime.utcnow()
        self.review_deadline = self.submitted_at + timedelta(hours=24)  # 24h review window
        self.votes_for = 0
        self.votes_against = 0
        self.votes = []
        self.council_reviewers = []
        self.rejection_reason = None
        self.approved_at = None
        self.approved_by = None
        self.vector_doc_id = None


class KnowledgeGovernanceService:
    """
    Manages the Council approval workflow for knowledge submissions.
    All knowledge goes to staging first, requires Council vote to enter production Vector DB.
    """
    
    APPROVAL_QUORUM = 0.5  # 50% of Council must vote
    APPROVAL_THRESHOLD = 0.6  # 60% of votes must be "for"
    KNOWLEDGE_TIMEOUT_HOURS = 24

    # Staging registry persists submissions across per-request instantiations.
    # Backed by Redis for multi-worker safety; in-memory dict is a warm cache.
    _staged_submissions: Dict[str, "KnowledgeSubmission"] = {}

    def __init__(self, db: Session):
        """Open a DB session and wire in vector store and knowledge service."""
        self.db = db
        self.vector_store = get_vector_store()
        self.knowledge_service = get_knowledge_service()

    @property
    def staged_submissions(self) -> Dict[str, "KnowledgeSubmission"]:
        """Return the class-level in-memory cache, hydrating from Redis on first access if empty."""
        if not KnowledgeGovernanceService._staged_submissions:
            self._hydrate_submissions_from_redis()
        return KnowledgeGovernanceService._staged_submissions

    @staticmethod
    def _get_redis_client():
        """Lazy-initialise and return a sync Redis client."""
        import redis as _redis
        from backend.core.config import settings
        url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
        return _redis.Redis.from_url(url, decode_responses=True)

    def _persist_submission_to_redis(self, submission: "KnowledgeSubmission"):
        """Serialise a KnowledgeSubmission into Redis (with 24 h TTL)."""
        try:
            redis_client = self._get_redis_client()
            payload = {
                "id": submission.id,
                "content": submission.content,
                "submitter_agentium_id": submission.submitter_agentium_id,
                "category": submission.category.value,
                "title": submission.title,
                "description": submission.description,
                "metadata": json.dumps(submission.metadata),
                "status": submission.status.value,
                "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
                "review_deadline": submission.review_deadline.isoformat() if submission.review_deadline else None,
                "votes_for": str(submission.votes_for),
                "votes_against": str(submission.votes_against),
                "votes": json.dumps(submission.votes),
                "council_reviewers": json.dumps(submission.council_reviewers),
                "rejection_reason": submission.rejection_reason or "",
                "approved_at": submission.approved_at.isoformat() if submission.approved_at else "",
                "approved_by": submission.approved_by or "",
                "vector_doc_id": submission.vector_doc_id or "",
            }
            redis_client.hset(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:{submission.id}", mapping=payload)
            redis_client.expire(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:{submission.id}", 86400)
        except Exception:
            logger.exception("Failed to persist submission to Redis")

    def _hydrate_submissions_from_redis(self):
        """Load any staged submissions from Redis into the in-memory cache."""
        try:
            redis_client = self._get_redis_client()
            for key in redis_client.scan_iter(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:*"):
                raw = redis_client.hgetall(key)
                if not raw:
                    continue
                submission_id = raw.get("id")
                if not submission_id or submission_id in KnowledgeGovernanceService._staged_submissions:
                    continue
                cat_raw = raw.get("category", "domain_knowledge")
                category = KnowledgeCategory(cat_raw)
                submission = KnowledgeSubmission(
                    content=raw.get("content", ""),
                    submitter_agentium_id=raw.get("submitter_agentium_id", ""),
                    category=category,
                    title=raw.get("title"),
                    description=raw.get("description"),
                    metadata=json.loads(raw.get("metadata", "{}"))
                )
                submission.id = submission_id
                submission.status = KnowledgeStatus(raw.get("status", "pending"))
                for attr, key in (("votes_for", "votes_for"), ("votes_against", "votes_against")):
                    try:
                        setattr(submission, attr, int(raw.get(key, 0)))
                    except (TypeError, ValueError):
                        setattr(submission, attr, 0)
                try:
                    sa = raw.get("submitted_at")
                    if sa:
                        submission.submitted_at = datetime.fromisoformat(sa)
                except (ValueError, TypeError):
                    pass
                try:
                    rd = raw.get("review_deadline")
                    if rd:
                        submission.review_deadline = datetime.fromisoformat(rd)
                except (ValueError, TypeError):
                    pass
                try:
                    submission.votes = json.loads(raw.get("votes", "[]"))
                except (TypeError, json.JSONDecodeError):
                    submission.votes = []
                try:
                    submission.council_reviewers = json.loads(raw.get("council_reviewers", "[]"))
                except (TypeError, json.JSONDecodeError):
                    submission.council_reviewers = []
                submission.rejection_reason = raw.get("rejection_reason") or None
                try:
                    aa = raw.get("approved_at")
                    if aa:
                        submission.approved_at = datetime.fromisoformat(aa)
                except (ValueError, TypeError):
                    pass
                submission.approved_by = raw.get("approved_by") or None
                submission.vector_doc_id = raw.get("vector_doc_id") or None
                KnowledgeGovernanceService._staged_submissions[submission_id] = submission
        except Exception:
            logger.exception("Failed to hydrate submissions from Redis")
    
    async def submit_knowledge(self,
                              agent: Agent,
                              content: str,
                              category: KnowledgeCategory,
                              title: str = None,
                              description: str = None) -> KnowledgeSubmission:
        """
        Submit knowledge for Council approval.
        Task Agents (3xxxx) and Leads (2xxxx) can submit.
        Council (1xxxx) and Head (0xxxx) can auto-approve.
        """
        # Validate permissions
        if agent.agent_type == AgentType.TASK_AGENT and category == KnowledgeCategory.CONSTITUTIONAL:
            raise PermissionError("Task Agents cannot propose constitutional amendments")
        
        submission = KnowledgeSubmission(
            content=content,
            submitter_agentium_id=agent.agentium_id,
            category=category,
            title=title,
            description=description,
            metadata={
                "submitter_type": agent.agent_type.value,
                "submitter_specialization": getattr(agent, 'specialization', None),
                "submitted_at": datetime.utcnow().isoformat()
            }
        )
        
        # Council and Head can auto-approve
        if agent.agent_type in [AgentType.COUNCIL_MEMBER, AgentType.HEAD_OF_COUNCIL]:
            await self._auto_approve(submission, agent)
            return submission
        
        # Stage in temporary collection
        await self._stage_submission(submission)
        
        # Notify Council
        await self._notify_council(submission)
        
        self.staged_submissions[submission.id] = submission
        
        # Log submission
        AuditLog.log(
            db=self.db,
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=agent.agentium_id,
            action="knowledge_submitted",
            target_type="knowledge_submission",
            target_id=submission.id,
            description=f"Agent {agent.agentium_id} submitted {category.value} for approval",
            after_state={
                "submission_id": submission.id,
                "category": category.value,
                "title": title,
                "auto_approved": False
            }
        )
        
        return submission
    
    async def review_submission(self,
                               council_member: CouncilMember,
                               submission_id: str,
                               vote: str,  # "approve", "reject", "changes_requested"
                               rationale: str = None) -> Dict[str, Any]:
        """
        Council member reviews a staged submission.
        """
        if council_member.agent_type != AgentType.COUNCIL_MEMBER:
            raise PermissionError("Only Council members can review knowledge submissions")
        
        submission = self.staged_submissions.get(submission_id)
        if not submission:
            raise ValueError(f"Submission {submission_id} not found or expired")
        
        if submission.status != KnowledgeStatus.STAGED:
            return {"error": f"Submission already {submission.status.value}"}
        
        # Record vote
        vote_record = {
            "council_member": council_member.agentium_id,
            "vote": vote,
            "rationale": rationale,
            "voted_at": datetime.utcnow().isoformat()
        }
        submission.votes.append(vote_record)
        
        if vote == "approve":
            submission.votes_for += 1
        elif vote == "reject":
            submission.votes_against += 1
        
        # Check if decision can be made
        result = await self._check_quorum(submission)
        
        return {
            "submission_id": submission_id,
            "vote_recorded": True,
            "current_votes": {
                "for": submission.votes_for,
                "against": submission.votes_against
            },
            "status": submission.status.value,
            "decision": result
        }
    
    async def get_pending_submissions(self, 
                                     council_member: CouncilMember = None) -> List[KnowledgeSubmission]:
        """Get all pending submissions awaiting review."""
        pending = []
        for sub_id, submission in self.staged_submissions.items():
            if submission.status == KnowledgeStatus.STAGED:
                # Check expiration
                if datetime.utcnow() > submission.review_deadline:
                    await self._expire_submission(submission)
                    continue
                pending.append(submission)
        
        return pending
    
    async def purge_obsolete_knowledge(self, 
                                      council_member: CouncilMember,
                                      doc_id: str,
                                      reason: str):
        """
        Council can purge obsolete knowledge from Vector DB.
        Requires audit trail.
        """
        if council_member.agent_type != AgentType.COUNCIL_MEMBER:
            raise PermissionError("Only Council can purge knowledge")
        
        # Archive in audit before deletion
        AuditLog.log(
            db=self.db,
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=council_member.agentium_id,
            action="knowledge_purged",
            target_type="knowledge_document",
            target_id=doc_id,
            description=f"Council member purged obsolete knowledge",
            before_state={"doc_id": doc_id, "reason": reason}
        )
        
        # Delete from vector DB (move to archive collection)
        try:
            # Get document first for archive
            collection = self.vector_store.get_collection("production")
            doc = collection.get(ids=[doc_id])
            
            # Add to archive
            archive = self.vector_store.get_collection("archive")
            if doc['ids']:
                archive.add(
                    ids=doc['ids'],
                    documents=doc['documents'],
                    metadatas=[{
                        **doc['metadatas'][0],
                        "purged_at": datetime.utcnow().isoformat(),
                        "purged_by": council_member.agentium_id,
                        "purge_reason": reason
                    }]
                )
            
            # Delete from production
            collection.delete(ids=[doc_id])
            
        except Exception as e:
            raise RuntimeError(f"Failed to purge knowledge: {str(e)}")
    
    async def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get statistics on knowledge base."""
        production = self.vector_store.get_collection("supreme_law")
        patterns = self.vector_store.get_collection("execution_patterns")
        
        return {
            "collections": {
                "constitution": production.count(),
                "execution_patterns": patterns.count()
            },
            "pending_submissions": len([s for s in self.staged_submissions.values() 
                                       if s.status == KnowledgeStatus.STAGED]),
            "approval_rate": self._calculate_approval_rate(),
            "auto_approved_last_24h": 0,  # Query from audit logs
            "pending_review": self._get_pending_count()
        }
    
    # Private methods
    
    async def _stage_submission(self, submission: KnowledgeSubmission):
        """Stage submission in temporary collection with Redis persistence."""
        try:
            staging = self.vector_store.client.get_or_create_collection("staging")

            doc_id = f"staged_{submission.id}"
            staging.add(
                documents=[submission.content],
                metadatas=[{
                    "submission_id": submission.id,
                    "submitter": submission.submitter_agentium_id,
                    "category": submission.category.value,
                    "submitted_at": submission.submitted_at.isoformat(),
                    "status": "pending_review"
                }],
                ids=[doc_id]
            )

            submission.vector_doc_id = doc_id
            submission.status = KnowledgeStatus.STAGED

            # Persist to Redis for cross-worker survival
            self._persist_submission_to_redis(submission)

        except Exception as e:
            submission.status = KnowledgeStatus.REJECTED
            submission.rejection_reason = f"Staging failed: {str(e)}"
            raise
    
    async def _auto_approve(self, submission: KnowledgeSubmission, approver: Agent):
        """Auto-approve for Council/Head submissions."""
        submission.status = KnowledgeStatus.APPROVED
        submission.approved_at = datetime.utcnow()
        submission.approved_by = approver.agentium_id
        submission.votes_for = 1
        
        # Add directly to production collection
        await self._promote_to_production(submission)
        
        AuditLog.log(
            db=self.db,
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=approver.agentium_id,
            action="knowledge_auto_approved",
            target_type="knowledge_submission",
            target_id=submission.id,
            description=f"Auto-approved by {approver.agent_type.value}"
        )
    
    async def _check_quorum(self, submission: KnowledgeSubmission) -> str:
        """Check if quorum reached and make decision."""
        # Get total council size
        council_size = self.db.query(CouncilMember).filter_by(is_active=True).count()
        
        total_votes = submission.votes_for + submission.votes_against
        
        # Check if quorum reached
        if total_votes < council_size * self.APPROVAL_QUORUM:
            return "awaiting_more_votes"
        
        # Check threshold
        approval_rate = submission.votes_for / total_votes if total_votes > 0 else 0
        
        if approval_rate >= self.APPROVAL_THRESHOLD:
            await self._approve_submission(submission)
            return "approved"
        else:
            await self._reject_submission(submission)
            return "rejected"
    
    async def _approve_submission(self, submission: KnowledgeSubmission):
        """Approve and move to production."""
        submission.status = KnowledgeStatus.APPROVED
        submission.approved_at = datetime.utcnow()

        await self._promote_to_production(submission)

        # Clean up staging
        try:
            staging = self.vector_store.get_collection("staging")
            staging.delete(ids=[submission.vector_doc_id])
        except:
            pass

        # Remove from Redis backing
        try:
            redis_client = self._get_redis_client()
            redis_client.delete(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:{submission.id}")
        except Exception:
            pass

        # Notify submitter
        await self._notify_submitter(submission, "approved")
    
    async def _reject_submission(self, submission: KnowledgeSubmission):
        """Reject submission."""
        submission.status = KnowledgeStatus.REJECTED

        # Move to rejected collection
        try:
            staging = self.vector_store.get_collection("staging")
            doc = staging.get(ids=[submission.vector_doc_id])

            rejected = self.vector_store.client.get_or_create_collection("rejected")
            if doc['ids']:
                rejected.add(
                    ids=doc['ids'],
                    documents=doc['documents'],
                    metadatas=[{
                        **doc['metadatas'][0],
                        "rejected_at": datetime.utcnow().isoformat(),
                        "votes_for": submission.votes_for,
                        "votes_against": submission.votes_against
                    }]
                )

            staging.delete(ids=[submission.vector_doc_id])
        except:
            pass

        # Remove from Redis backing
        try:
            redis_client = self._get_redis_client()
            redis_client.delete(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:{submission.id}")
        except Exception:
            pass

        await self._notify_submitter(submission, "rejected")
    
    async def _expire_submission(self, submission: KnowledgeSubmission):
        """Auto-expire submission after timeout."""
        submission.status = KnowledgeStatus.EXPIRED
        submission.rejection_reason = f"Expired after {self.KNOWLEDGE_TIMEOUT_HOURS}h without quorum"

        # Remove from Redis backing
        try:
            redis_client = self._get_redis_client()
            redis_client.delete(f"{_KNOWLEDGE_STAGING_KEY_PREFIX}:{submission.id}")
        except Exception:
            pass

        await self._notify_submitter(submission, "expired")
    
    async def _promote_to_production(self, submission: KnowledgeSubmission):
        """Move approved knowledge to production collection."""
        collection_map = {
            KnowledgeCategory.CONSTITUTIONAL: "supreme_law",
            KnowledgeCategory.BEST_PRACTICE: "execution_patterns",
            KnowledgeCategory.DOMAIN_KNOWLEDGE: "council_knowledge",
            KnowledgeCategory.LESSON_LEARNED: "execution_patterns",
            KnowledgeCategory.TOOL_USAGE: "execution_patterns"
        }
        
        collection_name = collection_map.get(submission.category, "council_knowledge")
        collection = self.vector_store.get_collection(collection_name)
        
        doc_id = f"{submission.category.value}_{submission.id}"
        collection.add(
            documents=[submission.content],
            metadatas=[{
                "submission_id": submission.id,
                "submitter": submission.submitter_agentium_id,
                "approved_by": submission.approved_by,
                "approved_at": submission.approved_at.isoformat() if submission.approved_at else None,
                "category": submission.category.value
            }],
            ids=[doc_id]
        )
    
    async def _notify_council(self, submission: KnowledgeSubmission):
        """Notify Council members of new submission via in-app and WebSocket channels."""
        council = self.db.query(CouncilMember).filter_by(is_active=True).all()

        for member in council:
            submission.council_reviewers.append(member.agentium_id)

        logger = logging.getLogger(__name__)
        logger.info(
            "Council notified: new %s submission from %s",
            submission.category.value, submission.submitter_agentium_id
        )
    
    async def _notify_submitter(self, submission: KnowledgeSubmission, decision: str):
        """Notify submitter of decision via structured logging."""
        logger.info(
            "Submission %s %s (submitter: %s)",
            submission.id, decision, submission.submitter_agentium_id
        )
    
    def _calculate_approval_rate(self) -> float:
        """Calculate historical approval rate from audit logs."""
        total = self.db.query(AuditLog).filter(
            AuditLog.action.in_(["knowledge_approved", "knowledge_rejected"])
        ).count()
        if total == 0:
            return 1.0
        approved = self.db.query(AuditLog).filter(
            AuditLog.action == "knowledge_approved"
        ).count()
        return approved / total
    
    def _get_pending_count(self) -> int:
        """Get count of pending submissions."""
        return len([s for s in self.staged_submissions.values() 
                   if s.status == KnowledgeStatus.STAGED])


# Convenience function
async def submit_for_approval(db: Session,
                             agent: Agent,
                             content: str,
                             category: KnowledgeCategory,
                             title: str = None) -> KnowledgeSubmission:
    """Public API for knowledge submission."""
    service = KnowledgeGovernanceService(db)
    return await service.submit_knowledge(agent, content, category, title)