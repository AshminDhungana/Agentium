"""
Amendment Service - Constitutional Amendment Lifecycle for Agentium.

Handles the full pipeline:
  1. Council member proposes amendment (markdown diff)
  2. Requires 2 Council sponsors
  3. Configurable debate window (default 48h)
  4. Democratic vote (60% quorum via AmendmentVoting)
  5. If passed: update PostgreSQL, update Vector DB, broadcast via Message Bus
  6. If failed: rollback, log, notify

Integration points:
  - AmendmentVoting entity (voting.py)
  - Constitution entity (constitution.py)
  - VectorStore (vector_store.py)
  - MessageBus (message_bus.py)
  - AuditLog (audit.py)
"""

import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.models.entities.constitution import Constitution, DocumentType
from backend.models.entities.voting import (
    AmendmentVoting, AmendmentStatus, VoteType,
)
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.agents import Agent, AgentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_VOTING_PERIOD_HOURS = 48
REQUIRED_SPONSORS = 2
QUORUM_PERCENTAGE = 60       # 60% of eligible voters must participate
SUPERMAJORITY_THRESHOLD = 66  # 66% of votes must be FOR to pass

DEBATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "docs_ministry", "debates",
)


# ---------------------------------------------------------------------------
# Amendment Service
# ---------------------------------------------------------------------------

class AmendmentService:
    """
    Manages the full lifecycle of constitutional amendments.

    Usage::

        svc = AmendmentService(db)
        proposal = await svc.propose_amendment(
            proposer_id="10001",
            title="Add Privacy Article",
            diff_markdown="+ Article 8: All agents shall respect data privacy...",
            rationale="Privacy is a fundamental right in Agentium.",
        )

        await svc.sponsor_amendment(proposal["amendment_id"], sponsor_id="10002")
        # ... voting happens ...
        result = await svc.conclude_voting(amendment_voting_id)
    """

    def __init__(self, db: Session):
        self.db = db
        self._message_bus = None
        self._vector_store = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        """Lazy-load dependencies."""
        try:
            from backend.services.message_bus import get_message_bus
            self._message_bus = await get_message_bus()
        except Exception as exc:
            logger.warning("MessageBus unavailable: %s", exc)

        try:
            from backend.core.vector_store import get_vector_store
            self._vector_store = get_vector_store()
        except Exception as exc:
            logger.warning("VectorStore unavailable: %s", exc)

    # ------------------------------------------------------------------
    # 1. Propose Amendment
    # ------------------------------------------------------------------

    async def propose_amendment(
        self,
        proposer_id: str,
        title: str,
        diff_markdown: str,
        rationale: str,
        voting_period_hours: int = DEFAULT_VOTING_PERIOD_HOURS,
        affected_articles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new amendment proposal.

        Only Council members (1xxxx) can propose amendments.
        The proposer automatically becomes the first sponsor.

        Returns:
            dict with amendment_id, status, and sponsor info.

        Raises:
            PermissionError: If proposer is not a Council member.
            ValueError: If no active constitution exists.
        """
        # Validate proposer is Council tier
        if not proposer_id.startswith("1") and not proposer_id.startswith("0"):
            raise PermissionError(
                f"Only Council members (1xxxx) or Head (0xxxx) can propose amendments. "
                f"Agent {proposer_id} is unauthorized."
            )

        # Verify proposer exists in DB
        proposer = (
            self.db.query(Agent)
            .filter_by(agentium_id=proposer_id, is_active=True)
            .first()
        )
        if not proposer:
            raise ValueError(f"Agent {proposer_id} not found or inactive.")

        # Get current active constitution
        current_constitution = (
            self.db.query(Constitution)
            .filter_by(is_active=True)
            .order_by(Constitution.version_number.desc())
            .first()
        )
        if not current_constitution:
            raise ValueError("No active constitution found. Cannot propose amendment.")

        # Get eligible voters (all active Council members)
        eligible_voters = self._get_eligible_voters()

        # Create AmendmentVoting record
        amendment_voting = AmendmentVoting(
            amendment_id=current_constitution.id,
            eligible_voters=eligible_voters,
            required_votes=max(1, int(len(eligible_voters) * QUORUM_PERCENTAGE / 100)),
            supermajority_threshold=SUPERMAJORITY_THRESHOLD,
            status=AmendmentStatus.PROPOSED,
        )

        # Store proposal metadata in discussion thread
        amendment_voting.add_discussion_entry(
            proposer_id,
            f"PROPOSAL: {title}\n\nRationale: {rationale}\n\n"
            f"Affected articles: {affected_articles or 'New addition'}\n\n"
            f"Voting period: {voting_period_hours} hours"
        )

        self.db.add(amendment_voting)
        self.db.flush()  # Get the ID

        # Store the diff markdown as debate document
        self._store_debate_document(
            amendment_voting.id, title, diff_markdown, proposer_id
        )

        # Proposer is first sponsor
        sponsors = [proposer_id]
        self.db.flush()

        # Audit log
        self._log_amendment_action(
            actor_id=proposer_id,
            action="amendment_proposed",
            description=(
                f"Amendment proposed: '{title}' by {proposer_id}. "
                f"Sponsors: {sponsors}. Voting period: {voting_period_hours}h."
            ),
            amendment_id=amendment_voting.id,
        )

        self.db.commit()

        return {
            "amendment_id": amendment_voting.id,
            "agentium_id": amendment_voting.agentium_id,
            "status": AmendmentStatus.PROPOSED.value,
            "title": title,
            "proposer": proposer_id,
            "sponsors": sponsors,
            "sponsors_needed": REQUIRED_SPONSORS - len(sponsors),
            "eligible_voters": eligible_voters,
            "voting_period_hours": voting_period_hours,
        }

    # ------------------------------------------------------------------
    # 2. Sponsor Amendment
    # ------------------------------------------------------------------

    async def sponsor_amendment(
        self,
        amendment_id: str,
        sponsor_id: str,
    ) -> Dict[str, Any]:
        """
        Add a Council member as sponsor for a proposed amendment.

        When the required number of sponsors is reached, the amendment
        transitions to DELIBERATING status and the debate clock starts.

        Returns:
            dict with updated sponsor count and status.

        Raises:
            PermissionError: If sponsor is not a Council member.
            ValueError: If amendment not found or not in PROPOSED status.
        """
        if not sponsor_id.startswith("1") and not sponsor_id.startswith("0"):
            raise PermissionError("Only Council members or Head can sponsor amendments.")

        amendment = self.db.query(AmendmentVoting).filter_by(id=amendment_id).first()
        if not amendment:
            raise ValueError(f"Amendment {amendment_id} not found.")
        if amendment.status != AmendmentStatus.PROPOSED:
            raise ValueError(
                f"Amendment is in '{amendment.status.value}' status, cannot add sponsors."
            )

        # Extract existing sponsors from discussion thread
        sponsors = self._extract_sponsors(amendment)

        if sponsor_id in sponsors:
            raise ValueError(f"Agent {sponsor_id} has already sponsored this amendment.")

        sponsors.append(sponsor_id)

        amendment.add_discussion_entry(
            sponsor_id,
            f"SPONSOR: {sponsor_id} endorses this amendment ({len(sponsors)}/{REQUIRED_SPONSORS} sponsors)"
        )

        # If we have enough sponsors, start deliberation
        if len(sponsors) >= REQUIRED_SPONSORS:
            amendment.status = AmendmentStatus.DELIBERATING
            amendment.add_discussion_entry(
                "System",
                f"Sponsor threshold reached ({REQUIRED_SPONSORS}). "
                f"Amendment entering deliberation phase."
            )

            self._log_amendment_action(
                actor_id=sponsor_id,
                action="amendment_deliberation_started",
                description=f"Amendment {amendment_id} entered deliberation with {len(sponsors)} sponsors.",
                amendment_id=amendment_id,
            )
        else:
            self._log_amendment_action(
                actor_id=sponsor_id,
                action="amendment_sponsored",
                description=f"Amendment {amendment_id} sponsored by {sponsor_id}. {len(sponsors)}/{REQUIRED_SPONSORS}.",
                amendment_id=amendment_id,
            )

        self.db.commit()

        return {
            "amendment_id": amendment_id,
            "status": amendment.status.value,
            "sponsors": sponsors,
            "sponsors_needed": max(0, REQUIRED_SPONSORS - len(sponsors)),
        }

    # ------------------------------------------------------------------
    # 3. Start Voting
    # ------------------------------------------------------------------

    async def start_voting(self, amendment_id: str) -> Dict[str, Any]:
        """
        Transition from DELIBERATING to VOTING.

        Can only be called after the debate window or by Head of Council override.

        Returns:
            dict with voting session info.
        """
        amendment = self.db.query(AmendmentVoting).filter_by(id=amendment_id).first()
        if not amendment:
            raise ValueError(f"Amendment {amendment_id} not found.")

        if amendment.status != AmendmentStatus.DELIBERATING:
            raise ValueError(
                f"Amendment must be in DELIBERATING status to start voting. "
                f"Current: {amendment.status.value}"
            )

        amendment.start_voting()

        self._log_amendment_action(
            actor_id="System",
            action="amendment_voting_started",
            description=f"Voting opened for amendment {amendment_id}.",
            amendment_id=amendment_id,
        )

        self.db.commit()

        return {
            "amendment_id": amendment_id,
            "status": AmendmentStatus.VOTING.value,
            "started_at": amendment.started_at.isoformat() if amendment.started_at else None,
            "eligible_voters": amendment.eligible_voters,
            "required_votes": amendment.required_votes,
            "supermajority_threshold": amendment.supermajority_threshold,
        }

    # ------------------------------------------------------------------
    # 4. Cast Vote (delegates to AmendmentVoting entity)
    # ------------------------------------------------------------------

    async def cast_vote(
        self,
        amendment_id: str,
        voter_id: str,
        vote: VoteType,
        rationale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cast a vote on an amendment. Wraps AmendmentVoting.cast_vote().

        Returns:
            dict with vote result and current tally.
        """
        amendment = self.db.query(AmendmentVoting).filter_by(id=amendment_id).first()
        if not amendment:
            raise ValueError(f"Amendment {amendment_id} not found.")

        vote_record = amendment.cast_vote(voter_id, vote, rationale)

        self._log_amendment_action(
            actor_id=voter_id,
            action="amendment_vote_cast",
            description=(
                f"Vote cast on amendment {amendment_id}: {vote.value}. "
                f"Tally: FOR={amendment.votes_for} AGAINST={amendment.votes_against} "
                f"ABSTAIN={amendment.votes_abstain}"
            ),
            amendment_id=amendment_id,
        )

        self.db.commit()

        return {
            "amendment_id": amendment_id,
            "voter": voter_id,
            "vote": vote.value,
            "tally": {
                "for": amendment.votes_for,
                "against": amendment.votes_against,
                "abstain": amendment.votes_abstain,
            },
        }

    # ------------------------------------------------------------------
    # 5. Conclude Voting
    # ------------------------------------------------------------------

    async def conclude_voting(self, amendment_id: str) -> Dict[str, Any]:
        """
        Conclude voting and execute the result.

        If PASSED: ratify the amendment (PostgreSQL + Vector DB + broadcast).
        If FAILED: rollback (log + notify).

        Returns:
            dict with conclusion result.
        """
        amendment = self.db.query(AmendmentVoting).filter_by(id=amendment_id).first()
        if not amendment:
            raise ValueError(f"Amendment {amendment_id} not found.")

        # Conclude using entity logic
        voting_result = amendment.conclude()

        if voting_result["result"] == "passed":
            ratification = await self._ratify_amendment(amendment)
            result = {**voting_result, **ratification, "status": "ratified"}
        else:
            await self._rollback_amendment(amendment)
            result = {**voting_result, "status": "rejected"}

        self._log_amendment_action(
            actor_id="System",
            action=f"amendment_{result['status']}",
            description=(
                f"Amendment {amendment_id} concluded: {result['status']}. "
                f"FOR={voting_result['votes_for']} AGAINST={voting_result['votes_against']}"
            ),
            amendment_id=amendment_id,
        )

        self.db.commit()
        return result

    # ------------------------------------------------------------------
    # 6. Ratify Amendment
    # ------------------------------------------------------------------

    async def _ratify_amendment(
        self, amendment: AmendmentVoting
    ) -> Dict[str, Any]:
        """
        Execute a passed amendment:
          1. Create new Constitution version in PostgreSQL
          2. Update Vector DB with new articles
          3. Broadcast law change via Message Bus
        """
        # Get the current constitution being amended
        current = self.db.query(Constitution).filter_by(id=amendment.amendment_id).first()
        if not current:
            raise ValueError("Cannot ratify: original constitution not found.")

        # Extract the diff from debate document
        diff_content = self._load_debate_document(amendment.id)

        # Create new constitution version
        new_version_number = (current.version_number + 1) if hasattr(current, 'version_number') else 2
        new_version = f"{new_version_number}.0"

        new_constitution = Constitution(
            agentium_id=f"C{new_version_number:04d}",
            name=current.name if hasattr(current, 'name') else "Constitution of Agentium",
            version=new_version,
            version_number=new_version_number,
            content=self._apply_diff(
                current.content if hasattr(current, 'content') else "",
                diff_content,
            ),
            created_by=current.created_by if hasattr(current, 'created_by') else "00001",
            replaces_version_id=current.id,
            ratified_by_vote_id=amendment.id,
        )

        # Copy structured fields if they exist
        if hasattr(current, 'articles') and current.articles:
            new_constitution.articles = current.articles
        if hasattr(current, 'prohibited_actions') and current.prohibited_actions:
            new_constitution.prohibited_actions = current.prohibited_actions
        if hasattr(current, 'sovereign_preferences') and current.sovereign_preferences:
            new_constitution.sovereign_preferences = current.sovereign_preferences

        # Archive old constitution
        current.archive()

        self.db.add(new_constitution)
        self.db.flush()
        
        try:
            from backend.services.config_versioning import ConfigVersioningService
            content_dict = {
                "name": new_constitution.name,
                "version": new_constitution.version,
                "version_number": new_constitution.version_number,
                "content": new_constitution.content,
                "articles": new_constitution.articles,
                "prohibited_actions": new_constitution.prohibited_actions,
                "sovereign_preferences": new_constitution.sovereign_preferences
            }
            ConfigVersioningService.commit_snapshot("constitution_article", new_constitution.id, "System", content_dict)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Config versioning failed: {exc}")

        # Update amendment status
        amendment.status = AmendmentStatus.RATIFIED

        # ---- Update Vector DB ----
        vector_updated = False
        if self._vector_store:
            try:
                self._vector_store.add_constitution_article(
                    article_id=f"constitution_v{new_version_number}",
                    content=new_constitution.content if hasattr(new_constitution, 'content') else str(diff_content),
                    metadata={
                        "version": new_version,
                        "version_number": new_version_number,
                        "ratified_at": datetime.utcnow().isoformat(),
                        "amendment_id": amendment.id,
                        "type": "amendment",
                    },
                )
                vector_updated = True
            except Exception as exc:
                logger.error("Failed to update Vector DB on ratification: %s", exc)

        # ---- Broadcast via Message Bus ----
        broadcast_sent = False
        if self._message_bus:
            try:
                from backend.models.schemas.messages import AgentMessage

                broadcast_msg = AgentMessage(
                    sender_id="00001",
                    recipient_id="broadcast",
                    message_type="notification",
                    route_direction="broadcast",
                    content=(
                        f"📜 CONSTITUTIONAL AMENDMENT RATIFIED\n"
                        f"Version {new_version} is now in effect.\n"
                        f"Amendment ID: {amendment.id}\n"
                        f"Vote: FOR={amendment.votes_for} / AGAINST={amendment.votes_against}"
                    ),
                    payload={
                        "event": "constitution_amended",
                        "new_version": new_version,
                        "amendment_id": amendment.id,
                    },
                    priority="critical",
                )
                await self._message_bus.broadcast_from_head(broadcast_msg)
                broadcast_sent = True
            except Exception as exc:
                logger.error("Failed to broadcast amendment ratification: %s", exc)

        return {
            "new_constitution_id": new_constitution.id,
            "new_version": new_version,
            "vector_db_updated": vector_updated,
            "broadcast_sent": broadcast_sent,
        }

    # ------------------------------------------------------------------
    # 7. Rollback (failed vote)
    # ------------------------------------------------------------------

    async def _rollback_amendment(self, amendment: AmendmentVoting):
        """Handle a failed amendment vote – no DB changes, just log and notify."""
        amendment.status = AmendmentStatus.REJECTED
        amendment.add_discussion_entry(
            "System",
            "Amendment REJECTED. No constitutional changes applied. "
            "The current constitution remains in effect."
        )

        # Notify via Message Bus if available
        if self._message_bus:
            try:
                from backend.models.schemas.messages import AgentMessage

                msg = AgentMessage(
                    sender_id="00001",
                    recipient_id="broadcast",
                    message_type="notification",
                    route_direction="broadcast",
                    content=(
                        f"📜 Amendment {amendment.id} was REJECTED by democratic vote. "
                        f"FOR={amendment.votes_for} / AGAINST={amendment.votes_against}. "
                        f"No changes to constitution."
                    ),
                    priority="normal",
                )
                await self._message_bus.broadcast_from_head(msg)
            except Exception as exc:
                logger.warning("Failed to broadcast rejection: %s", exc)

    # ------------------------------------------------------------------
    # 8. Query Amendment History
    # ------------------------------------------------------------------

    async def get_amendment_history(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get amendment history ordered by most recent.

        Returns:
            List of amendment summaries.
        """
        amendments = (
            self.db.query(AmendmentVoting)
            .order_by(AmendmentVoting.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": a.id,
                "agentium_id": a.agentium_id,
                "status": a.status.value,
                "votes_for": a.votes_for,
                "votes_against": a.votes_against,
                "votes_abstain": a.votes_abstain,
                "result": a.final_result,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "ended_at": a.ended_at.isoformat() if a.ended_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in amendments
        ]

    async def get_amendment_detail(
        self, amendment_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get full detail for a single amendment including debate document."""
        amendment = self.db.query(AmendmentVoting).filter_by(id=amendment_id).first()
        if not amendment:
            return None

        detail = amendment.to_dict()
        detail["debate_document"] = self._load_debate_document(amendment_id)
        detail["sponsors"] = self._extract_sponsors(amendment)
        return detail

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _get_eligible_voters(self) -> List[str]:
        """Get all active Council members eligible to vote."""
        council_members = (
            self.db.query(Agent)
            .filter(
                Agent.agent_type.in_([AgentType.COUNCIL_MEMBER, AgentType.HEAD_OF_COUNCIL]),
                Agent.is_active == True,
            )
            .all()
        )
        return [m.agentium_id for m in council_members]

    def _extract_sponsors(self, amendment: AmendmentVoting) -> List[str]:
        """Extract sponsor IDs from the discussion thread."""
        sponsors = []
        thread = amendment.discussion_thread or []
        for entry in thread:
            msg = entry.get("message", "")
            agent = entry.get("agent", "")
            if msg.startswith("PROPOSAL:") and agent:
                sponsors.append(agent)
            elif msg.startswith("SPONSOR:") and agent:
                sponsors.append(agent)
        return list(dict.fromkeys(sponsors))  # Deduplicate preserving order

    def _store_debate_document(
        self,
        amendment_id: str,
        title: str,
        diff_markdown: str,
        proposer_id: str,
    ):
        """Store the amendment diff as a debate document."""
        os.makedirs(DEBATES_DIR, exist_ok=True)

        filename = f"{amendment_id}_{datetime.utcnow().strftime('%Y%m%d')}.md"
        filepath = os.path.join(DEBATES_DIR, filename)

        content = (
            f"# Amendment Proposal: {title}\n\n"
            f"**Proposed by:** {proposer_id}\n"
            f"**Date:** {datetime.utcnow().isoformat()}\n"
            f"**Amendment ID:** {amendment_id}\n\n"
            f"---\n\n"
            f"## Proposed Changes\n\n"
            f"```diff\n{diff_markdown}\n```\n"
        )

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:
            logger.warning("Failed to write debate document: %s", exc)

    def _load_debate_document(self, amendment_id: str) -> Optional[str]:
        """Load the debate document for an amendment."""
        if not os.path.isdir(DEBATES_DIR):
            return None

        for filename in os.listdir(DEBATES_DIR):
            if filename.startswith(amendment_id):
                filepath = os.path.join(DEBATES_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        return None

    def _apply_diff(self, original_content: str, diff_content: Optional[str]) -> str:
        """
        Apply a markdown diff to the original constitution content.

        For now, appends the amendment text. A full diff engine can be
        integrated later for proper patch application.
        """
        if not diff_content:
            return original_content

        amendment_text = ""
        for line in diff_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("+ ") or stripped.startswith("+\t"):
                amendment_text += stripped[2:] + "\n"
            elif stripped.startswith("- ") or stripped.startswith("-\t"):
                continue  # Skip removed lines for now
            elif not stripped.startswith("```") and not stripped.startswith("#"):
                # Content lines from the debate document itself – skip
                pass

        if amendment_text.strip():
            return original_content + "\n\n---\n\n" + amendment_text.strip()
        return original_content

    def _log_amendment_action(
        self,
        actor_id: str,
        action: str,
        description: str,
        amendment_id: str,
    ):
        """Log amendment-related actions to the audit trail."""
        try:
            audit = AuditLog(
                level=AuditLevel.NOTICE,
                category=AuditCategory.CONSTITUTION,
                actor_type="agent" if actor_id != "System" else "system",
                actor_id=actor_id,
                action=action,
                target_type="amendment",
                target_id=amendment_id,
                description=description,
                agentium_id=f"AM{datetime.utcnow().strftime('%H%M%S')}",
            )
            self.db.add(audit)
        except Exception as exc:
            logger.error("Failed to log amendment action: %s", exc)
