"""
Tool Marketplace Service
Enables tool sharing between Agentium instances.

Workflow:
  LOCAL:   publish_tool() → listing created → browsable by other instances
  REMOTE:  search_marketplace() → import_tool() → Council vote → activate
  RATINGS: rate_tool() → trust_score updated

Security:
  - All imported code goes through ToolFactory.validate_tool_code()
  - Council vote required to import any remote tool
  - Code hash verified on import to detect tampering
  - Yanked tools immediately removed from import availability
"""
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime
import hashlib
import json
import uuid
import os

from backend.models.entities.tool_marketplace_listing import ToolMarketplaceListing
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.tool_factory import ToolFactory


# This instance's unique ID — set via env var or generated once and persisted
INSTANCE_ID = os.getenv("AGENTIUM_INSTANCE_ID", str(uuid.uuid4()))


class ToolMarketplaceService:
    """
    Manages tool publishing, discovery, and cross-instance import.
    """

    def __init__(self, db: Session):
        """Init."""

        self.db = db
        self.factory = ToolFactory()

    # ──────────────────────────────────────────────────────────────
    # PUBLISH (this instance → marketplace)
    # ──────────────────────────────────────────────────────────────

    def publish_tool(
        self,
        tool_name: str,
        display_name: str,
        category: str,
        tags: List[str],
        published_by: str,
    ) -> Dict[str, Any]:
        """
        Publish an activated tool to the marketplace.
        Only Head (0xxxx) or Council (1xxxx) can publish.
        """
        if not (published_by.startswith("0") or published_by.startswith("1")):
            return {"published": False, "error": "Only Head or Council can publish tools"}

        # Tool must be active
        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
            ToolStaging.status == "activated",
        ).first()

        if not staging:
            return {"published": False, "error": f"Tool '{tool_name}' not found or not active"}

        # Get current version's code
        current_version = (
            self.db.query(ToolVersion)
            .filter(ToolVersion.tool_name == tool_name, ToolVersion.is_active == True)
            .first()
        )

        if not current_version:
            return {"published": False, "error": "No active version found for this tool"}

        # Check if already listed
        existing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.tool_name == tool_name,
            ToolMarketplaceListing.publisher_instance_id == INSTANCE_ID,
            ToolMarketplaceListing.is_active == True,
        ).first()

        if existing:
            return {
                "published": False,
                "error": f"Tool '{tool_name}' is already listed. Use update_listing() to republish.",
            }

        # Build listing
        import json as _json
        request_data = _json.loads(staging.request_json)
        code = current_version.code_snapshot
        code_hash = hashlib.sha256(code.encode()).hexdigest()

        listing = ToolMarketplaceListing(
            tool_name=tool_name,
            version_tag=current_version.version_tag,
            publisher_instance_id=INSTANCE_ID,
            published_by_agentium_id=published_by,
            display_name=display_name,
            description=request_data.get("description", ""),
            category=category,
            tags=tags,
            code_snapshot=code,
            code_hash=code_hash,
            parameters_schema=request_data.get("parameters", []),
            authorized_tiers=request_data.get("authorized_tiers", []),
            is_local=True,
            is_imported=False,
        )

        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)

        self._audit("tool_published", tool_name, published_by, {"listing_id": listing.id})

        return {
            "published": True,
            "listing_id": listing.id,
            "tool_name": tool_name,
            "version_tag": current_version.version_tag,
            "code_hash": code_hash,
        }

    # ──────────────────────────────────────────────────────────────
    # BROWSE / SEARCH
    # ──────────────────────────────────────────────────────────────

    def browse_marketplace(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search_query: Optional[str] = None,
        include_remote: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Browse marketplace listings.
        Supports filtering by category, tags, and free-text search.
        """
        q = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.is_active == True,
            ToolMarketplaceListing.yanked_at == None,
        )

        if not include_remote:
            q = q.filter(ToolMarketplaceListing.is_local == True)

        if category:
            q = q.filter(ToolMarketplaceListing.category == category)

        if search_query:
            term = f"%{search_query.lower()}%"
            q = q.filter(
                ToolMarketplaceListing.display_name.ilike(term)
                | ToolMarketplaceListing.description.ilike(term)
                | ToolMarketplaceListing.tool_name.ilike(term)
            )

        total = q.count()
        listings = q.order_by(
            ToolMarketplaceListing.download_count.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()

        # Filter by tags in Python (JSON array containment varies by DB)
        if tags:
            listings = [
                l for l in listings
                if any(tag in (l.tags or []) for tag in tags)
            ]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "listings": [l.to_dict() for l in listings],
        }

    # ──────────────────────────────────────────────────────────────
    # IMPORT (remote listing → this instance)
    # ──────────────────────────────────────────────────────────────

    def import_tool(
        self,
        listing_id: str,
        requested_by: str,
    ) -> Dict[str, Any]:
        """
        Stage a marketplace tool for import.
        - Validates code (security scan)
        - Verifies code hash integrity
        - Returns a proposal for Council vote (same pipeline as tool creation)

        After Council approves, call finalize_import().
        """
        if not (requested_by.startswith("0") or requested_by.startswith("1")):
            return {"staged": False, "error": "Only Head or Council can import marketplace tools"}

        listing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.id == listing_id,
            ToolMarketplaceListing.is_active == True,
        ).first()

        if not listing:
            return {"staged": False, "error": "Listing not found or inactive"}

        if listing.yanked_at:
            return {"staged": False, "error": "This tool has been yanked by its publisher"}

        # Verify code hash integrity
        computed_hash = hashlib.sha256(listing.code_snapshot.encode()).hexdigest()
        if computed_hash != listing.code_hash:
            return {
                "staged": False,
                "error": "Code hash mismatch — listing may have been tampered with",
            }

        # Security validation
        validation = self.factory.validate_tool_code(listing.code_snapshot)
        if not validation["valid"]:
            return {
                "staged": False,
                "error": f"Security validation failed: {validation['error']}",
            }

        # Check not already imported
        existing = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == listing.tool_name,
        ).first()

        if existing:
            return {
                "staged": False,
                "error": f"A tool named '{listing.tool_name}' already exists on this instance",
            }

        return {
            "staged": True,
            "listing_id": listing_id,
            "tool_name": listing.tool_name,
            "version_tag": listing.version_tag,
            "publisher_instance_id": listing.publisher_instance_id,
            "code_hash": listing.code_hash,
            "requires_council_vote": True,
            "note": "Submit this as a ToolCreationRequest via ToolCreationService to complete import",
            "import_payload": {
                "tool_name": listing.tool_name,
                "description": listing.description,
                "code_template": listing.code_snapshot,
                "parameters": listing.parameters_schema,
                "authorized_tiers": listing.authorized_tiers,
                "rationale": f"Imported from marketplace listing {listing_id}",
                "created_by_agentium_id": requested_by,
            },
        }

    def finalize_import(
        self,
        listing_id: str,
        staging_id: str,
    ) -> Dict[str, Any]:
        """
        Called after Council approves an import.
        Marks the listing as imported on this instance.
        """
        listing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.id == listing_id,
        ).first()

        if not listing:
            return {"finalized": False, "error": "Listing not found"}

        # Track import
        listing.download_count += 1
        listing.is_imported = True

        self.db.commit()

        return {
            "finalized": True,
            "tool_name": listing.tool_name,
            "download_count": listing.download_count,
        }

    # ──────────────────────────────────────────────────────────────
    # RATE
    # ──────────────────────────────────────────────────────────────

    def rate_tool(
        self,
        listing_id: str,
        rated_by: str,
        rating: float,
    ) -> Dict[str, Any]:
        """
        Rate a marketplace tool (1.0 - 5.0).
        Any agent tier can rate.
        """
        if not 1.0 <= rating <= 5.0:
            return {"rated": False, "error": "Rating must be between 1.0 and 5.0"}

        listing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.id == listing_id,
            ToolMarketplaceListing.is_active == True,
        ).first()

        if not listing:
            return {"rated": False, "error": "Listing not found"}

        listing.rating_sum += rating
        listing.rating_count += 1
        listing.trust_score = min(1.0, listing.average_rating / 5.0)

        self.db.commit()

        return {
            "rated": True,
            "listing_id": listing_id,
            "new_average": listing.average_rating,
            "total_ratings": listing.rating_count,
            "trust_score": listing.trust_score,
        }

    # ──────────────────────────────────────────────────────────────
    # YANK (retract a listing)
    # ──────────────────────────────────────────────────────────────

    def yank_listing(
        self,
        listing_id: str,
        yanked_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Retract a tool from the marketplace.
        Only Head or the original publisher can yank.
        Does NOT remove already-imported copies from other instances.
        """
        listing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.id == listing_id,
            ToolMarketplaceListing.publisher_instance_id == INSTANCE_ID,
        ).first()

        if not listing:
            return {"yanked": False, "error": "Listing not found or not owned by this instance"}

        if not (yanked_by.startswith("0") or yanked_by == listing.published_by_agentium_id):
            return {"yanked": False, "error": "Only Head or the publisher can yank a listing"}

        listing.yanked_at = datetime.utcnow()
        listing.yank_reason = reason
        listing.is_active = False

        self.db.commit()

        self._audit("tool_listing_yanked", listing.tool_name, yanked_by, {"reason": reason})

        return {
            "yanked": True,
            "tool_name": listing.tool_name,
            "reason": reason,
        }

    # ──────────────────────────────────────────────────────────────
    # UPDATE LISTING (republish with new version)
    # ──────────────────────────────────────────────────────────────

    def update_listing(
        self,
        tool_name: str,
        updated_by: str,
    ) -> Dict[str, Any]:
        """
        Refresh a marketplace listing to reflect the tool's latest active version.
        """
        if not (updated_by.startswith("0") or updated_by.startswith("1")):
            return {"updated": False, "error": "Only Head or Council can update listings"}

        listing = self.db.query(ToolMarketplaceListing).filter(
            ToolMarketplaceListing.tool_name == tool_name,
            ToolMarketplaceListing.publisher_instance_id == INSTANCE_ID,
            ToolMarketplaceListing.is_active == True,
        ).first()

        if not listing:
            return {"updated": False, "error": "No active listing for this tool on this instance"}

        current_version = (
            self.db.query(ToolVersion)
            .filter(ToolVersion.tool_name == tool_name, ToolVersion.is_active == True)
            .first()
        )

        if not current_version:
            return {"updated": False, "error": "No active version found"}

        new_code = current_version.code_snapshot
        new_hash = hashlib.sha256(new_code.encode()).hexdigest()

        listing.code_snapshot = new_code
        listing.code_hash = new_hash
        listing.version_tag = current_version.version_tag

        self.db.commit()

        return {
            "updated": True,
            "tool_name": tool_name,
            "new_version_tag": current_version.version_tag,
            "new_code_hash": new_hash,
        }

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _audit(self, action: str, tool_name: str, actor: str, details: dict):
        """Audit."""

        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="agent",
            actor_id=actor,
            action=action,
            target_type="tool_listing",
            target_id=tool_name,
            description=f"{action} for tool '{tool_name}'",
            after_state=details,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        self.db.add(audit)
        self.db.commit()