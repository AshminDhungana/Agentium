"""
Phase 11.3 — Plugin Marketplace Models
======================================
Lifecycle and registry models for external plugins (tools, critics, channels).
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, func, Float, Text, Integer
from sqlalchemy.orm import relationship

from backend.models.entities.base import Base

def _new_uuid() -> str:
    return str(uuid.uuid4())

class Plugin(Base):
    """A plugin available in the marketplace."""
    __tablename__ = "plugins"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    author = Column(String(100), nullable=False)
    version = Column(String(20), nullable=False)
    
    # "channel", "critic", "model_provider", "knowledge_source", "tool"
    plugin_type = Column(String(50), nullable=False, index=True)
    source_url = Column(String(255), nullable=True)
    
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_date = Column(DateTime(timezone=True), nullable=True)
    
    install_count = Column(Integer, default=0, nullable=False)
    rating = Column(Float, default=0.0, nullable=False)
    revenue_share_percent = Column(Float, default=0.0, nullable=False)
    
    config_schema = Column(JSON, nullable=True)
    entry_point = Column(String(255), nullable=False)
    dependencies = Column(JSON, default=list)
    
    # "draft", "submitted", "verified", "published", "deprecated"
    status = Column(String(20), default="draft", nullable=False, index=True)
    
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

class PluginInstallation(Base):
    """A plugin installed matching a local instance configuration."""
    __tablename__ = "plugin_installations"
    
    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    plugin_id = Column(String(36), ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)
    instance_id = Column(String(100), nullable=False, default="local")
    
    config = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    installed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class PluginRevenueLedger(Base):
    """Ledger for recording plugin purchases, subscriptions, and revenue share."""
    __tablename__ = "plugin_revenue_ledger"
    
    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    plugin_id = Column(String(36), ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)
    
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    
    # "purchase", "subscription", "refund", "payout"
    transaction_type = Column(String(20), default="purchase", nullable=False)
    notes = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class PluginReview(Base):
    """A user review for a plugin."""
    __tablename__ = "plugin_reviews"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    plugin_id = Column(String(36), ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    rating = Column(Integer, nullable=False) # 1 to 5
    review_text = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
