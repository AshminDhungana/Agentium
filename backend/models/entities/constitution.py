"""
Constitution and Ethos management for Agentium.
The Constitution is the supreme law, while Ethos defines individual agent behavior.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, event, Index
from sqlalchemy.orm import relationship, validates
from backend.models.entities.base import BaseEntity
from sqlalchemy.orm import remote
from sqlalchemy.orm import remote, foreign
import enum

class DocumentType(str, enum.Enum):
    """Types of governance documents."""
    CONSTITUTION = "constitution"
    ETHOS = "ethos"



class Constitution(BaseEntity):
    """
    The Supreme Law of Agentium.
    - Only Head of Council (0xxxx) can modify
    - Updated daily via voting process
    - Read-only for all other entities
    - Supports amendment chaining via replaces_version_id
    """
    
    __tablename__ = 'constitutions'
    
    # Document metadata
    version = Column(String(10), nullable=False, unique=True)  # v1.0.0 format (display)
    version_number = Column(Integer, nullable=False, unique=True)  # Sequential: 1, 2, 3...
    document_type = Column(Enum(DocumentType), default=DocumentType.CONSTITUTION, nullable=False)
    
    # Content sections
    preamble = Column(Text, nullable=True)
    articles = Column(Text, nullable=False)  # JSON string of articles
    prohibited_actions = Column(Text, nullable=False)  # JSON array
    sovereign_preferences = Column(Text, nullable=False)  # JSON object - User's preferences
    changelog = Column(Text, nullable=True)  # JSON array documenting changes from previous version
    
    effective_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    amendment_date = Column(DateTime, nullable=True)
    archived_date = Column(DateTime, nullable=True)
    # Authority
    created_by_agentium_id = Column(String(10), nullable=False)  # Usually 00001 (Head of Council)
    
    amendment_of = Column(String(36), ForeignKey('constitutions.id'), nullable=True)
    replaces_version_id = Column(String(36), ForeignKey('constitutions.id'), nullable=True)
    amended_from = relationship(
        "Constitution",
        foreign_keys=[amendment_of],
        remote_side=lambda: Constitution.id,  # Use lambda for deferred evaluation
        back_populates="amendments",
    )

    # Amendments that amend this constitution (one-to-many side) - parent pointing to children
    amendments = relationship(
        "Constitution",
        foreign_keys=[amendment_of],
        back_populates="amended_from",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Version replacement relationships
    # This constitution replaces a previous version (many-to-one)
    replaces_version = relationship(
        "Constitution",
        foreign_keys=[replaces_version_id],
        remote_side=lambda: Constitution.id,  # Use lambda for deferred evaluation
        back_populates="replaced_by",
    )

    # Newer versions that replace this one (one-to-many)
    replaced_by = relationship(
        "Constitution",
        foreign_keys=[replaces_version_id],
        back_populates="replaces_version",
        lazy="dynamic",
    )

    voting_sessions = relationship("AmendmentVoting", back_populates="amendment")
    
    def __init__(self, **kwargs):
        # Auto-generate version strings if not provided
        if 'version' not in kwargs and 'version_number' in kwargs:
            kwargs['version'] = f"v{kwargs['version_number']}.0.0"
        elif 'version' not in kwargs:
            kwargs['version'] = f"v{datetime.utcnow().strftime('%Y.%m.%d.%H%M')}"
        
        # Auto-generate version_number if not provided (get next sequential)
        if 'version_number' not in kwargs:
            # This should be handled by service layer, but default to 1
            kwargs['version_number'] = 1
            
        super().__init__(**kwargs)
    
    @validates('version')
    def validate_version(self, key, version):
        if not version.startswith('v'):
            raise ValueError("Version must start with 'v'")
        return version
    
    @validates('version_number')
    def validate_version_number(self, key, version_number):
        if version_number < 1:
            raise ValueError("Version number must be positive integer")
        return version_number
    
    def get_articles_dict(self) -> Dict[str, Any]:
        """Parse articles JSON to dictionary with normalized article structure."""
        import json
        try:
            articles = json.loads(self.articles) if self.articles else {}
        except json.JSONDecodeError:
            return {}
        
        # Normalize: ensure all article values are {title, content} dicts, not strings
        normalized = {}
        for key, val in articles.items():
            if isinstance(val, str):
                # Convert string content to proper structure
                pretty_title = key.replace("_", " ").title()
                normalized[key] = {"title": pretty_title, "content": val}
            elif isinstance(val, dict):
                # Already a dict, ensure it has required keys
                normalized[key] = {
                    "title": val.get("title", key.replace("_", " ").title()),
                    "content": val.get("content", "")
                }
            else:
                # Unknown type, create empty structure
                normalized[key] = {"title": key.replace("_", " ").title(), "content": str(val) if val else ""}
        
        return normalized
    
    def get_prohibited_actions_list(self) -> List[str]:
        """Parse prohibited actions to list."""
        import json
        try:
            return json.loads(self.prohibited_actions) if self.prohibited_actions else []
        except json.JSONDecodeError:
            return []
    
    def get_sovereign_preferences(self) -> Dict[str, Any]:
        """Parse sovereign preferences to dictionary."""
        import json
        try:
            return json.loads(self.sovereign_preferences) if self.sovereign_preferences else {}
        except json.JSONDecodeError:
            return {}
    
    def get_changelog(self) -> List[Dict[str, Any]]:
        """Parse changelog to list of changes."""
        import json
        try:
            return json.loads(self.changelog) if self.changelog else []
        except json.JSONDecodeError:
            return []
    
    def get_amendment_chain(self) -> List['Constitution']:
        """Get chain of constitutions leading to this one (oldest first)."""
        chain = []
        current = self
        while current.replaces_version:
            chain.insert(0, current.replaces_version)
            current = current.replaces_version
        chain.append(self)
        return chain
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'version': self.version,
            'version_number': self.version_number,
            'document_type': self.document_type.value,
            'preamble': self.preamble,
            'articles': self.get_articles_dict(),
            'prohibited_actions': self.get_prohibited_actions_list(),
            'sovereign_preferences': self.get_sovereign_preferences(),
            'changelog': self.get_changelog(),
            'created_by': self.created_by_agentium_id,
            'amendment_date': self.amendment_date.isoformat() if self.amendment_date else None,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'replaces_version': self.replaces_version.version if self.replaces_version else None,
            'is_archived': self.archived_date is not None,
            'is_active': self.is_active
        })
        return base
    
    def archive(self):
        """Archive this constitution version when new one takes effect."""
        self.archived_date = datetime.utcnow()
        self.is_active = False

        # Table indexes for Phase 0 verification
    __table_args__ = (
        Index('idx_constitution_version', 'version'),           # Quick version lookup
        Index('idx_constitution_version_number', 'version_number'),  # Chronological sorting
        Index('idx_constitution_active', 'is_active'),          # Active constitution queries
        Index('idx_constitution_effective', 'effective_date'),  # Effective date queries
    )


class Ethos(BaseEntity):
    """
    Individual Agent Ethos — the agent's working memory.

    A dynamic, minimal, continuously updated internal state containing:
      - Core identity (mission, values, rules, restrictions, capabilities)
      - Current objective and active plan
      - Relevant constitutional references
      - Temporary reasoning artifacts
      - Task progress markers
      - Outcome summaries and lessons learned

    Created by higher authority, updated by the agent itself, verified by lead.
    Ethos is short-term working cognition; ChromaDB is long-term institutional memory.

    LLM-powered compression flow (Workflow §IDLE / §3):
      Agent.compress_ethos(db)
          → ethos.build_compression_payload()    # serialise working memory for prompt
          → ModelService.generate_with_agent()   # agent calls LLM via its own API key
          → ethos.apply_llm_compression(result)  # write compressed fields back
      Falls back to ethos.prune_obsolete_content() if no model config is available.
    """
    
    __tablename__ = 'ethos'
    
    # Identification
    agent_type = Column(String(20), nullable=False)  # head_of_council, council_member, lead_agent, task_agent
    # agentium_id inherited from BaseEntity (NOT NULL). Format: E0xxxx, E1xxxx for ethos
    
    # Core Identity Content
    mission_statement = Column(Text, nullable=False)
    core_values = Column(Text, nullable=False)  # JSON array
    behavioral_rules = Column(Text, nullable=False)  # JSON array of do's
    restrictions = Column(Text, nullable=False)  # JSON array of don'ts
    capabilities = Column(Text, nullable=False)  # JSON array of what this agent can do
    
    # Working Memory Fields (Workflow §1-§5)
    current_objective = Column(Text, nullable=True)               # Active task objective
    active_plan = Column(Text, nullable=True)                     # JSON: structured execution plan
    constitutional_references = Column(Text, nullable=True)       # JSON: relevant constitutional sections/summary
    task_progress_markers = Column(Text, nullable=True)           # JSON: sub-step progress tracking
    reasoning_artifacts = Column(Text, nullable=True)             # JSON: temporary reasoning notes
    outcome_summary = Column(Text, nullable=True)                 # Last task outcome summary
    lessons_learned = Column(Text, nullable=True)                 # JSON: accumulated lessons
    
    # Authority & versioning
    created_by_agentium_id = Column(String(10), nullable=False)  # Higher authority
    version = Column(Integer, default=1, nullable=False)
    agent_id = Column(String(36), nullable=False)  # Links to specific agent instance
    
    # Verification
    verified_by_agentium_id = Column(String(10), nullable=True)  # Lead/Head who verified
    verified_at = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    
    # Update tracking (agents can update their own ethos)
    last_updated_by_agent = Column(Boolean, default=False)  # True if agent updated itself

    # Environment / host grounding (6.1) — core identity, set at agent creation
    environment_context = Column(Text, nullable=True)

    # Standard working procedure (6.3) — how this agent operates, set at creation
    working_method = Column(Text, nullable=True)
    def get_core_values(self) -> List[str]:
        import json
        val = self.core_values
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_behavioral_rules(self) -> List[str]:
        import json
        val = self.behavioral_rules
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_restrictions(self) -> List[str]:
        import json
        val = self.restrictions
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_capabilities(self) -> List[str]:
        import json
        val = self.capabilities
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def verify(self, verifier_agentium_id: str):
        """Mark ethos as verified by a higher authority."""
        self.verified_by_agentium_id = verifier_agentium_id
        self.verified_at = datetime.utcnow()
        self.is_verified = True
    
    def increment_version(self):
        """Increment version when updated."""
        self.version += 1
        self.last_updated_by_agent = True
    
    # --- Working Memory Accessors (Workflow §1-§5) ---
    
    def get_active_plan(self) -> Optional[Dict[str, Any]]:
        import json
        val = self.active_plan
        if not val:
            return None
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def set_active_plan(self, plan: Dict[str, Any]):
        """Write a structured execution plan into the Ethos."""
        import json
        self.active_plan = json.dumps(plan)
        self.increment_version()
    
    def get_constitutional_references(self) -> List[Dict[str, Any]]:
        import json
        val = self.constitutional_references
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_constitutional_references(self, references: List[Dict[str, Any]]):
        """Update constitutional references in the Ethos."""
        import json
        self.constitutional_references = json.dumps(references)
    
    def get_task_progress(self) -> Dict[str, Any]:
        import json
        val = self.task_progress_markers
        if not val:
            return {}
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_task_progress(self, progress: Dict[str, Any]):
        """Update task progress markers."""
        import json
        self.task_progress_markers = json.dumps(progress)
    
    def get_reasoning_artifacts(self) -> List[str]:
        import json
        val = self.reasoning_artifacts
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_lessons_learned(self) -> List[Dict[str, Any]]:
        import json
        val = self.lessons_learned
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def add_lesson_learned(self, lesson: Dict[str, Any]):
        """Append a lesson learned entry."""
        import json
        lessons = self.get_lessons_learned()
        lessons.append(lesson)
        # Keep only the last 20 lessons to prevent unbounded growth
        self.lessons_learned = json.dumps(lessons[-20:])

    # -----------------------------------------------------------------------
    # LLM Compression Interface (Workflow §IDLE / §3)
    # The agent drives the LLM call; these two methods are the before/after.
    # -----------------------------------------------------------------------

    def build_compression_payload(self) -> Dict[str, Any]:
        """
        Serialise current working memory into a dict ready to be embedded
        inside the LLM compression prompt.

        Called by Agent.compress_ethos() BEFORE the ModelService call so the
        agent can include this in the message it sends to the LLM.

        Returns a plain dict — safe to json.dumps() into a prompt.
        """
        return {
            "agent_type":          self.agent_type,
            "mission_statement":   self.mission_statement,
            "current_objective":   self.current_objective,
            "active_plan":         self.get_active_plan(),
            "task_progress":       self.get_task_progress(),
            "reasoning_artifacts": self.get_reasoning_artifacts(),
            "lessons_learned":     self.get_lessons_learned(),
            "constitutional_refs": self.get_constitutional_references(),
            "outcome_summary":     self.outcome_summary,
            "environment_context": self.environment_context,
        }

    def apply_llm_compression(
        self,
        compressed: Dict[str, Any],
        completed_steps: List[str] = None,
    ) -> None:
        """
        Write the LLM-produced compressed working memory back onto this Ethos.

        Called by Agent.compress_ethos() AFTER the ModelService call returns.
        This method is intentionally dumb — it just applies what the LLM gave
        back. All prompt construction and API calls live in Agent.compress_ethos.

        Expected keys in `compressed` (all optional; missing keys are skipped):
          - reasoning_artifacts  → list  (compressed digest + newest 25% raw)
          - lessons_learned      → list  (consolidated entry + newest 25% raw)
          - constitutional_refs  → list  (deduplicated)
          - outcome_summary      → str   (readable 25% snapshot paragraph)

        Args:
            compressed:      Parsed JSON dict from the LLM response.
            completed_steps: Progress-marker keys to drop before writing
                             (forwarded from Agent.compress_ethos).
        """
        import json

        # ── Step 0: Drop explicitly completed progress markers ───────────────
        if completed_steps and self.task_progress_markers:
            progress = self.get_task_progress()
            for step in completed_steps:
                progress.pop(step, None)
            self.task_progress_markers = json.dumps(progress) if progress else None

        # ── Step 1: Apply compressed reasoning artifacts ─────────────────────
        if "reasoning_artifacts" in compressed:
            self.reasoning_artifacts = json.dumps(compressed["reasoning_artifacts"])

        # ── Step 2: Apply consolidated lessons learned ───────────────────────
        if "lessons_learned" in compressed:
            self.lessons_learned = json.dumps(compressed["lessons_learned"])

        # ── Step 3: Apply deduplicated constitutional references ─────────────
        if "constitutional_refs" in compressed:
            self.constitutional_references = json.dumps(compressed["constitutional_refs"])

        # ── Step 4: Apply outcome summary (25% readable snapshot) ────────────
        # Only update during true idle compression (no completed_steps passed).
        # Mid-task pruning must not overwrite the last full outcome summary.
        if not completed_steps and "outcome_summary" in compressed:
            self.outcome_summary = compressed["outcome_summary"]

        # ── Step 5: Bump version to record this compression cycle ────────────
        self.increment_version()

    def compress(self):
        """
        Hard-clear transient working state after task completion (Workflow §5).
        Retains core identity and outcome/lessons; clears execution artifacts.
        """
        self.active_plan = None
        self.task_progress_markers = None
        self.reasoning_artifacts = None
        self.current_objective = None
        self.increment_version()
    
    def clear_working_state(self):
        """
        Fully reset working state for a fresh task cycle (Workflow §5.4).
        Preserves: mission, values, rules, restrictions, capabilities,
                   constitutional_references, lessons_learned, outcome_summary.
        Clears: objective, plan, progress, reasoning artifacts.
        """
        self.current_objective = None
        self.active_plan = None
        self.task_progress_markers = None
        self.reasoning_artifacts = None

    # -----------------------------------------------------------------------
    # Python-only Fallback Compression (Workflow §IDLE)
    # Used when no model config is available on the agent.
    # -----------------------------------------------------------------------

    def _build_activity_snapshot(self) -> Dict[str, Any]:
        """
        Build a structured snapshot of current agent state.
        Used by the Python-fallback prune_obsolete_content(). The LLM path
        produces a richer, plain-text outcome_summary paragraph instead.
        """
        active_plan = self.get_active_plan()
        progress = self.get_task_progress()
        lessons = self.get_lessons_learned()
        artifacts = self.get_reasoning_artifacts()
        refs = self.get_constitutional_references()

        plan_summary = None
        if active_plan:
            plan_summary = {
                "title": active_plan.get("title") or active_plan.get("objective"),
                "step_count": len(active_plan.get("steps", [])),
                "status": active_plan.get("status"),
            }

        progress_overview = {
            "total_steps": len(progress),
            "completed": sum(1 for v in progress.values() if v in (True, "done", "completed")),
            "step_keys": list(progress.keys()),
        } if progress else None

        recent_lesson_points = []
        for lesson in lessons[-3:]:
            point = lesson.get("key_point") or lesson.get("lesson") or lesson.get("summary")
            if point:
                recent_lesson_points.append(str(point)[:120])

        ref_titles = list({
            ref.get("title") or ref.get("section_id") or str(ref)[:40]
            for ref in refs
            if ref
        })

        return {
            "snapshot_at": datetime.utcnow().isoformat(),
            "agent_type": self.agent_type,
            "current_objective": self.current_objective,
            "active_plan": plan_summary,
            "progress": progress_overview,
            "reasoning_artifact_count": len(artifacts),
            "total_lessons": len(lessons),
            "recent_lesson_points": recent_lesson_points,
            "constitutional_refs": ref_titles,
            "ethos_version": self.version,
        }

    def _compress_reasoning_artifacts(self) -> None:
        """
        Fallback: collapse oldest 75% of reasoning artifacts into a single
        compressed entry; keep newest 25% raw. Skips if ≤ 4 artifacts.
        """
        import json

        artifacts = self.get_reasoning_artifacts()
        if len(artifacts) <= 4:
            return

        keep_raw_count = max(1, len(artifacts) * 25 // 100)
        old_artifacts = artifacts[:-keep_raw_count]
        recent_artifacts = artifacts[-keep_raw_count:]

        compressed_entry = {
            "type": "compressed_reasoning",
            "compressed_at": datetime.utcnow().isoformat(),
            "original_count": len(old_artifacts),
            "digest": " | ".join(str(a)[:100] for a in old_artifacts),
        }

        self.reasoning_artifacts = json.dumps([compressed_entry] + recent_artifacts)

    def _compress_lessons_learned(self) -> None:
        """
        Fallback: collapse oldest 75% of lessons into a consolidated entry;
        keep newest 25% raw. Skips if ≤ 4 lessons.
        """
        import json

        lessons = self.get_lessons_learned()
        if len(lessons) <= 4:
            return

        keep_raw_count = max(1, len(lessons) * 25 // 100)
        old_lessons = lessons[:-keep_raw_count]
        recent_lessons = lessons[-keep_raw_count:]

        key_patterns = list({
            l.get("key_point") or l.get("lesson") or l.get("summary") or str(l)[:80]
            for l in old_lessons
            if l
        })

        consolidated_entry = {
            "type": "consolidated_lessons",
            "compressed_at": datetime.utcnow().isoformat(),
            "source_count": len(old_lessons),
            "key_patterns": key_patterns,
        }

        self.lessons_learned = json.dumps([consolidated_entry] + recent_lessons)

    def _deduplicate_constitutional_references(self) -> None:
        """
        Fallback: deduplicate constitutional references, keeping the most
        recent occurrence of each unique section_id / title.
        """
        import json

        refs = self.get_constitutional_references()
        if not refs:
            return

        seen: Dict[str, Any] = {}
        for ref in refs:
            key = ref.get("section_id") or ref.get("title") or str(ref)[:60]
            seen[key] = ref  # last occurrence wins

        self.constitutional_references = json.dumps(list(seen.values()))

    def prune_obsolete_content(self, completed_steps: List[str] = None):
        """
        Python-only fallback compression using the 75/25 heuristic strategy.

        Only called directly by Agent.compress_ethos() when the agent has no
        model config (no API key). When a key IS configured, the agent uses
        the LLM path instead:

            build_compression_payload() → ModelService → apply_llm_compression()

        75% — Compress historical data:
          - Collapse oldest 75% of reasoning_artifacts into a digest
          - Consolidate oldest 75% of lessons_learned into key patterns
          - Deduplicate constitutional_references
          - Remove explicitly completed progress markers

        25% — Summarise current activity:
          - Write a structured snapshot to outcome_summary
        """
        import json

        # ── Step 1: Remove explicitly completed progress markers ─────────────
        if completed_steps and self.task_progress_markers:
            progress = self.get_task_progress()
            for step in completed_steps:
                progress.pop(step, None)
            self.task_progress_markers = json.dumps(progress) if progress else None

        # ── Step 2 (75%): Compress reasoning artifacts ───────────────────────
        self._compress_reasoning_artifacts()

        # ── Step 3 (75%): Consolidate lessons learned ────────────────────────
        self._compress_lessons_learned()

        # ── Step 4 (75%): Deduplicate constitutional references ──────────────
        self._deduplicate_constitutional_references()

        # ── Step 5 (25%): Write activity snapshot ────────────────────────────
        if not completed_steps:
            snapshot = self._build_activity_snapshot()
            self.outcome_summary = json.dumps(snapshot)

        # ── Bump version ──────────────────────────────────────────────────────
        self.increment_version()

    def get_outcome_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Parse outcome_summary as a dict. Falls back to wrapping raw string
        if it was written in plain-text format by an older code path.
        """
        import json
        if not self.outcome_summary:
            return None
        try:
            parsed = json.loads(self.outcome_summary)
            if isinstance(parsed, dict):
                return parsed
            return {"raw": self.outcome_summary}
        except (json.JSONDecodeError, TypeError):
            return {"raw": self.outcome_summary}

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'agent_type': self.agent_type,
            'agentium_id': self.agentium_id,
            'mission_statement': self.mission_statement,
            'core_values': self.get_core_values(),
            'behavioral_rules': self.get_behavioral_rules(),
            'restrictions': self.get_restrictions(),
            'capabilities': self.get_capabilities(),
            'current_objective': self.current_objective,
            'active_plan': self.get_active_plan(),
            'constitutional_references': self.get_constitutional_references(),
            'task_progress': self.get_task_progress(),
            'outcome_summary': self.get_outcome_snapshot(),
            'lessons_learned': self.get_lessons_learned(),
            'version': self.version,
            'created_by': self.created_by_agentium_id,
            'verified': self.is_verified,
            'verified_by': self.verified_by_agentium_id,
            'agent_id': self.agent_id,
            'environment_context': self.environment_context,
            'working_method': self.working_method,
        })
        return base


@event.listens_for(Constitution, 'after_insert')
def log_constitution_creation(mapper, connection, target):
    """Log when a new constitution is created."""
    from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.GOVERNANCE,
        actor_type="system",
        actor_id=target.created_by_agentium_id,
        action="constitution_created",
        target_type="constitution",
        target_id=target.agentium_id,
        description=f"Constitution v{target.version} (revision {target.version_number}) created",
        after_state={
            'version': target.version,
            'version_number': target.version_number,
            'effective_date': target.effective_date.isoformat() if target.effective_date else None
        },
        created_at=datetime.utcnow()
    )
    # Note: In actual implementation, you'd add this to the session
    # But in event listeners, we use connection.execute or similar

@event.listens_for(Ethos, 'after_update')
def log_ethos_update(mapper, connection, target):
    """Log when an ethos is modified."""
    if target.last_updated_by_agent:
        target.last_updated_by_agent = False  # Reset for next time