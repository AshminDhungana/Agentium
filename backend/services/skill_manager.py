"""
Skill lifecycle management service.
Handles creation, retrieval, updating, and governance of skills.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.models.entities.skill import SkillSchema, SkillDB, SkillSubmission, CHROMA_CHAR_LIMIT
from backend.models.entities.task import Task
from backend.models.entities.agents import Agent
from backend.core.vector_store import get_vector_store
from backend.services.knowledge_governance import KnowledgeGovernanceService

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Central service for skill CRUD operations and ChromaDB integration.
    """

    def __init__(self):
        self.vector_store = get_vector_store()
        self._knowledge_gov = None
        self.collections = {
            "constitutional": "constitutional_skills",
            "agent": "agent_skills",
            "tools": "tool_skills",
            "practices": "best_practices"
        }

    @property
    def knowledge_gov(self):
        """Lazy initialization of KnowledgeGovernanceService with fresh db session."""
        if self._knowledge_gov is None:
            from backend.models.database import SessionLocal
            from backend.services.knowledge_governance import KnowledgeGovernanceService
            db = SessionLocal()
            self._knowledge_gov = KnowledgeGovernanceService(db)
        return self._knowledge_gov

    # ═══════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _build_and_check_document(skill: SkillSchema) -> str:
        """
        Build the ChromaDB document string for *skill* and emit a structured
        warning if the content was clipped to CHROMA_CHAR_LIMIT.

        Call this exactly once per create/update so we never encode and store
        different strings for the embedding vs the document field.
        """
        doc = skill.to_chroma_document()
        if len(doc) == CHROMA_CHAR_LIMIT:
            # to_chroma_document clips to CHROMA_CHAR_LIMIT when content overflows
            logger.warning(
                "[SkillManager] Skill '%s' (id=%s) was clipped to %d chars before "
                "ChromaDB storage. Original content exceeded the embedding window. "
                "Shorten description/steps/code_template to avoid information loss.",
                skill.skill_name,
                skill.skill_id,
                CHROMA_CHAR_LIMIT,
            )
        return doc

    # ═══════════════════════════════════════════════════════════
    # CREATE Operations
    # ═══════════════════════════════════════════════════════════

    def create_skill(
        self,
        skill_data: Dict[str, Any],
        creator_agent: Agent,
        db: Session,
        auto_verify: bool = False
    ) -> SkillSchema:
        """
        Create a new skill from task execution or manual creation.

        Flow:
        1. Validate skill data against schema
        2. Build ChromaDB document (single call — reused for embed + storage)
        3. Check constitution compliance
        4. Store in ChromaDB
        5. Store metadata in PostgreSQL
        6. Submit for Council review (unless auto_verify)
        """
        try:
            skill_id = self._generate_skill_id(creator_agent)

            skill = SkillSchema(
                skill_id=skill_id,
                skill_name=skill_data.get("skill_name"),
                display_name=skill_data.get("display_name"),
                skill_type=skill_data.get("skill_type"),
                domain=skill_data.get("domain"),
                tags=skill_data.get("tags", []),
                complexity=skill_data.get("complexity", "intermediate"),
                description=skill_data.get("description"),
                prerequisites=skill_data.get("prerequisites", []),
                steps=skill_data.get("steps", []),
                code_template=skill_data.get("code_template"),
                examples=skill_data.get("examples", []),
                common_pitfalls=skill_data.get("common_pitfalls", []),
                validation_criteria=skill_data.get("validation_criteria", []),
                version="1.0.0",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                creator_tier=creator_agent.agent_type.value,
                creator_id=creator_agent.agentium_id,
                parent_skill_id=skill_data.get("parent_skill_id"),
                task_origin=skill_data.get("task_origin"),
                success_rate=skill_data.get("success_rate", 0.0),
                usage_count=0,
                constitution_compliant=False,  # Will be checked below
                verification_status="verified" if auto_verify else "pending",
                verified_by=creator_agent.agentium_id if auto_verify else None,
                chroma_collection=self.collections["agent"]
            )

            # Build document once — shared for compliance check, embedding, and storage
            chroma_doc = self._build_and_check_document(skill)

            # Check constitution compliance
            is_compliant, violations = self.knowledge_gov.check_constitutional_compliance(
                chroma_doc
            )
            skill.constitution_compliant = is_compliant

            if not is_compliant and not auto_verify:
                skill.verification_status = "rejected"
                skill.rejection_reason = f"Constitutional violations: {violations}"

            # Store in ChromaDB
            chroma_id = f"{skill_id}_v{skill.version}"
            collection = self.vector_store.get_collection(skill.chroma_collection)

            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(skill.embedding_model)
            embedding = model.encode(chroma_doc)

            collection.add(
                ids=[chroma_id],
                embeddings=[embedding.tolist()],
                documents=[chroma_doc],
                metadatas=[skill.to_chroma_metadata()]
            )

            # Store metadata in PostgreSQL
            skill_db = SkillDB(
                skill_id=skill_id,
                skill_name=skill.skill_name,
                display_name=skill.display_name,
                skill_type=skill.skill_type,
                domain=skill.domain,
                tags=skill.tags,
                complexity=skill.complexity,
                chroma_id=chroma_id,
                chroma_collection=skill.chroma_collection,
                creator_tier=skill.creator_tier,
                creator_id=skill.creator_id,
                parent_skill_id=skill.parent_skill_id,
                task_origin=skill.task_origin,
                success_rate=skill.success_rate,
                constitution_compliant=skill.constitution_compliant,
                verification_status=skill.verification_status,
                verified_by=skill.verified_by
            )
            db.add(skill_db)
            db.commit()

            # Submit to Council if pending and constitutionally compliant
            if not auto_verify and is_compliant:
                self._submit_for_review(skill, creator_agent, db)

            logger.info("Created skill %s by %s", skill_id, creator_agent.agentium_id)
            return skill

        except Exception as e:
            logger.error("Failed to create skill: %s", e)
            raise

    def _generate_skill_id(self, creator_agent: Agent) -> str:
        """Generate unique skill ID based on creator tier."""
        tier_prefix = creator_agent.agentium_id[0]  # 0, 1, 2, 3, etc.
        import uuid
        short_uuid = str(uuid.uuid4().int)[:3]
        return f"skill_{tier_prefix}xxxx_{short_uuid}"

    def _submit_for_review(self, skill: SkillSchema, submitter: Agent, db: Session):
        """Submit skill to Council for review."""
        submission = SkillSubmission(
            submission_id=f"sub_{skill.skill_id}",
            skill_id=skill.skill_id,
            submitted_by=submitter.agentium_id,
            skill_data=skill.dict()
        )
        db.add(submission)
        db.commit()

        from backend.services.message_bus import message_bus
        message_bus.publish("skill.submission.pending", {
            "submission_id": submission.submission_id,
            "skill_id": skill.skill_id,
            "skill_name": skill.display_name
        })

    # ═══════════════════════════════════════════════════════════
    # RETRIEVE Operations (RAG)
    # ═══════════════════════════════════════════════════════════

    def search_skills(
        self,
        query: str,
        agent_tier: str,
        db: Session,
        filters: Optional[Dict] = None,
        n_results: int = 5,
        min_success_rate: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for skills with tier-based access control.

        Args:
            query: Natural language search query
            agent_tier: Tier of requesting agent (affects access)
            filters: Additional metadata filters (domain, skill_type, etc.)
            n_results: Number of unique skills to return after deduplication
            min_success_rate: Minimum quality threshold

        Returns:
            List of skill matches with relevance scores, sorted best-first.
        """
        try:
            where_clause = self._build_access_filter(agent_tier, min_success_rate)
            if filters:
                where_clause = {"$and": [where_clause, filters]}

            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            query_embedding = model.encode(query)

            all_results = []
            for collection_name in ["agent_skills", "best_practices", "constitutional_skills"]:
                try:
                    collection = self.vector_store.get_collection(collection_name)
                    results = collection.query(
                        query_embeddings=[query_embedding.tolist()],
                        n_results=n_results,
                        where=where_clause,
                        include=["documents", "metadatas", "distances"]
                    )

                    if results and results['ids'][0]:
                        for doc_id, doc, meta, dist in zip(
                            results['ids'][0],
                            results['documents'][0],
                            results['metadatas'][0],
                            results['distances'][0]
                        ):
                            skill_db = db.query(SkillDB).filter_by(chroma_id=doc_id).first()

                            all_results.append({
                                "skill_id": meta.get("skill_id"),
                                "chroma_id": doc_id,
                                "relevance_score": max(0.0, 1.0 - dist),
                                "semantic_distance": dist,
                                # content_preview: full stored doc (already capped at CHROMA_CHAR_LIMIT)
                                "content_preview": doc,
                                "metadata": meta,
                                "db_record": skill_db.to_dict() if skill_db else None,
                                "collection": collection_name
                            })

                            if skill_db:
                                skill_db.retrieval_count += 1
                                skill_db.last_retrieved = datetime.utcnow()

                except Exception as col_err:
                    logger.warning("search_skills: collection '%s' query failed: %s", collection_name, col_err)

            db.commit()

            # Sort by relevance descending, then deduplicate by skill_id
            # keeping the highest-scoring hit when a skill appears in multiple collections
            all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
            seen_ids: set = set()
            unique_results = []
            for r in all_results:
                sid = r["skill_id"]
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    unique_results.append(r)

            return unique_results[:n_results]

        except Exception as e:
            logger.error("Skill search failed: %s", e)
            return []

    def _build_access_filter(self, agent_tier: str, min_success_rate: float) -> Dict:
        """Build ChromaDB where clause based on agent tier and quality threshold."""
        conditions = [
            {"success_rate": {"$gte": min_success_rate}},
            {"constitution_compliant": {"$eq": True}},
        ]

        if agent_tier == "task":
            conditions.append({"verification_status": {"$eq": "verified"}})
        elif agent_tier in ["lead", "council", "head"]:
            conditions.append({"verification_status": {"$in": ["verified", "pending"]}})

        return {"$and": conditions}

    def get_skill_by_id(self, skill_id: str, db: Session) -> Optional[SkillSchema]:
        """Retrieve full skill by ID."""
        skill_db = db.query(SkillDB).filter_by(skill_id=skill_id).first()
        if not skill_db:
            return None

        collection = self.vector_store.get_collection(skill_db.chroma_collection)
        result = collection.get(ids=[skill_db.chroma_id], include=["documents", "metadatas"])

        if result and result['ids']:
            meta = result['metadatas'][0]
            return SkillSchema(**meta)

        return None

    # ═══════════════════════════════════════════════════════════
    # UPDATE Operations
    # ═══════════════════════════════════════════════════════════

    def update_skill(
        self,
        skill_id: str,
        updates: Dict[str, Any],
        updater_agent: Agent,
        db: Session
    ) -> SkillSchema:
        """
        Create new version of existing skill (immutable history).
        """
        current = self.get_skill_by_id(skill_id, db)
        if not current:
            raise ValueError(f"Skill {skill_id} not found")

        if updater_agent.agent_type.value not in ["council", "head"]:
            if current.creator_id != updater_agent.agentium_id:
                raise PermissionError("Can only update own skills unless Council/Head")

        major, minor, patch = current.version.split(".")
        new_version = f"{major}.{minor}.{int(patch) + 1}"

        updated_data = current.dict()
        updated_data.update(updates)
        updated_data["version"] = new_version
        updated_data["updated_at"] = datetime.utcnow()
        updated_data["parent_skill_id"] = skill_id

        new_skill = SkillSchema(**updated_data)

        # Build document once — shared for embedding and storage
        chroma_doc = self._build_and_check_document(new_skill)

        chroma_id = f"{skill_id}_v{new_version}"
        collection = self.vector_store.get_collection(new_skill.chroma_collection)

        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(new_skill.embedding_model)
        embedding = model.encode(chroma_doc)

        collection.add(
            ids=[chroma_id],
            embeddings=[embedding.tolist()],
            documents=[chroma_doc],
            metadatas=[new_skill.to_chroma_metadata()]
        )

        skill_db = SkillDB(
            skill_id=skill_id,
            skill_name=new_skill.skill_name,
            display_name=new_skill.display_name,
            skill_type=new_skill.skill_type,
            domain=new_skill.domain,
            tags=new_skill.tags,
            complexity=new_skill.complexity,
            chroma_id=chroma_id,
            chroma_collection=new_skill.chroma_collection,
            creator_tier=new_skill.creator_tier,
            creator_id=new_skill.creator_id,
            parent_skill_id=skill_id,
            success_rate=new_skill.success_rate,
            constitution_compliant=new_skill.constitution_compliant,
            verification_status="pending" if updater_agent.agent_type.value == "task" else "verified"
        )
        db.add(skill_db)
        db.commit()

        logger.info("Updated skill %s to version %s", skill_id, new_version)
        return new_skill

    # ═══════════════════════════════════════════════════════════
    # USAGE tracking
    # ═══════════════════════════════════════════════════════════

    def record_skill_usage(self, skill_id: str, success: bool, db: Session):
        """Update success rate and usage count based on execution outcome."""
        skill_db = db.query(SkillDB).filter_by(skill_id=skill_id).first()
        if not skill_db:
            return

        skill_db.usage_count += 1

        # Exponential moving average: recent outcomes weighted more heavily
        if success:
            skill_db.success_rate = (skill_db.success_rate * 0.9) + (1.0 * 0.1)
        else:
            skill_db.success_rate = skill_db.success_rate * 0.9

        db.commit()

    # ═══════════════════════════════════════════════════════════
    # DELETE Operations (Soft Delete)
    # ═══════════════════════════════════════════════════════════

    def deprecate_skill(
        self,
        skill_id: str,
        reason: str,
        deprecator: Agent,
        db: Session
    ):
        """Mark skill as deprecated (Council/Head only)."""
        if deprecator.agent_type.value not in ["council", "head"]:
            raise PermissionError("Only Council/Head can deprecate skills")

        skill_db = db.query(SkillDB).filter_by(skill_id=skill_id).first()
        if not skill_db:
            raise ValueError(f"Skill {skill_id} not found")

        skill_db.verification_status = "rejected"

        collection = self.vector_store.get_collection(skill_db.chroma_collection)
        collection.update(
            ids=[skill_db.chroma_id],
            metadatas={"verification_status": "rejected", "deprecation_reason": reason}
        )

        from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
        AuditLog.log(
            db=db,
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=deprecator.agentium_id,
            action="skill_deprecated",
            target_type="skill",
            target_id=skill_id,
            description=f"Skill deprecated: {reason}"
        )

        db.commit()


# Global instance
skill_manager = SkillManager()