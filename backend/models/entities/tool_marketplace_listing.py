"""
Tool Marketplace Listing Entity
Represents a tool published to (or imported from) the Agentium marketplace.
Enables tool sharing between Agentium instances.
"""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, Float, JSON
from .base import BaseEntity
from datetime import datetime


class ToolMarketplaceListing(BaseEntity):
    """
    A published tool listing in the marketplace.
    Can be local (this instance published it) or remote (imported from another instance).
    """
    __tablename__ = 'tool_marketplace_listings'

    # Identity
    tool_name = Column(String(100), nullable=False, index=True)
    version_tag = Column(String(20), nullable=False)             # Published version e.g. "v2.1.0"
    publisher_instance_id = Column(String(100), nullable=False)  # UUID of originating Agentium instance
    published_by_agentium_id = Column(String(10), nullable=True) # Agent who published (local only)

    # Listing content
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)                 # "data", "web", "file", "comms", etc.
    tags = Column(JSON, default=list)                            # ["csv", "pandas", "analysis"]

    # Code payload (signed for integrity)
    code_snapshot = Column(Text, nullable=False)
    code_hash = Column(String(64), nullable=False)               # SHA-256 of code_snapshot
    parameters_schema = Column(JSON, default=dict)               # Tool parameter definitions
    authorized_tiers = Column(JSON, default=list)

    # Marketplace metadata
    is_local = Column(Boolean, default=True)                     # Published BY this instance
    is_imported = Column(Boolean, default=False)                 # Pulled FROM another instance
    import_source_url = Column(String(500), nullable=True)       # Remote instance URL if imported

    # Trust & ratings
    is_verified = Column(Boolean, default=False)                 # Manually reviewed
    trust_score = Column(Float, default=0.0)                     # 0.0 - 1.0, based on usage/votes
    download_count = Column(Integer, default=0)
    rating_sum = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)

    # Lifecycle
    is_active = Column(Boolean, default=True)
    published_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    yanked_at = Column(DateTime, nullable=True)                  # If retracted
    yank_reason = Column(Text, nullable=True)

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.rating_sum / self.rating_count, 2)

    def to_dict(self):
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "version_tag": self.version_tag,
            "publisher_instance_id": self.publisher_instance_id,
            "published_by": self.published_by_agentium_id,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags or [],
            "code_hash": self.code_hash,
            "parameters_schema": self.parameters_schema or {},
            "authorized_tiers": self.authorized_tiers or [],
            "is_local": self.is_local,
            "is_imported": self.is_imported,
            "import_source_url": self.import_source_url,
            "is_verified": self.is_verified,
            "trust_score": self.trust_score,
            "download_count": self.download_count,
            "average_rating": self.average_rating,
            "rating_count": self.rating_count,
            "is_active": self.is_active,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "yanked_at": self.yanked_at.isoformat() if self.yanked_at else None,
            "yank_reason": self.yank_reason,
        }