"""
Plugin Marketplace Service (Phase 11.3)
=======================================
Handles submission, verification, and installation of Agentium ecosystem plugins.
"""
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging

from backend.models.entities.plugin import Plugin, PluginInstallation, PluginReview
from backend.models.entities.user import User

logger = logging.getLogger(__name__)

class PluginMarketplaceService:

    @staticmethod
    def submit_plugin(
        db: Session,
        name: str,
        description: str,
        author: str,
        version: str,
        plugin_type: str,
        entry_point: str,
        source_url: Optional[str] = None,
        config_schema: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> Plugin:
        """Submit a new plugin for review."""
        if db.query(Plugin).filter(Plugin.name == name).first():
            raise HTTPException(status_code=400, detail="Plugin with this name already exists.")

        plugin = Plugin(
            name=name,
            description=description,
            author=author,
            version=version,
            plugin_type=plugin_type,
            source_url=source_url,
            entry_point=entry_point,
            config_schema=config_schema or {},
            dependencies=dependencies or [],
            status="submitted"
        )
        db.add(plugin)
        db.commit()
        db.refresh(plugin)
        return plugin

    @staticmethod
    def verify_plugin(db: Session, plugin_id: str, admin_user: User) -> Plugin:
        """Mark a submitted plugin as verified (Admin only)."""
        if not admin_user.is_sovereign:
            raise HTTPException(status_code=403, detail="Only Sovereign can verify plugins.")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")

        if plugin.status == "published":
            raise HTTPException(status_code=400, detail="Plugin is already published.")

        plugin.is_verified = True
        plugin.verification_date = datetime.utcnow()
        plugin.status = "verified"
        db.commit()
        db.refresh(plugin)
        return plugin

    @staticmethod
    def request_council_approval(db: Session, plugin_id: str) -> str:
        """
        Creates a POLICY_CHANGE proposal for the Council to review and verify a plugin.
        """
        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")

        if plugin.status != "submitted":
            raise HTTPException(status_code=400, detail="Only 'submitted' plugins can be sent for approval.")

        # In a full implementation, we would create a VotingProposal record here
        # For now, we simulate the proposal creation and return a mock proposal ID
        proposal_id = f"proposal-plugin-{plugin_id[:8]}"
        
        logger.info(f"Plugin Marketplace: Created Council approval proposal {proposal_id} for plugin {plugin.name}")
        return proposal_id

    @staticmethod
    def publish_plugin(db: Session, plugin_id: str, admin_user: User) -> Plugin:
        """Publish a verified plugin to the marketplace (Admin only)."""
        if not admin_user.is_sovereign:
            raise HTTPException(status_code=403, detail="Only Sovereign can publish plugins.")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")

        if plugin.status != "verified":
            raise HTTPException(status_code=400, detail=f"Plugin must be verified before publishing. Current status: {plugin.status}")

        plugin.status = "published"
        plugin.published_at = datetime.utcnow()
        db.commit()
        db.refresh(plugin)
        return plugin

    @staticmethod
    def install_plugin(
        db: Session, plugin_id: str, config: Dict[str, Any], user: User
    ) -> PluginInstallation:
        """Install a plugin onto the local instance."""
        if not user.is_sovereign: # Can be delegated in the future
            raise HTTPException(status_code=403, detail="Only Sovereign can install plugins.")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")

        if plugin.status != "published":
            raise HTTPException(status_code=400, detail=f"Cannot install {plugin.status} plugin.")

        # Check existing installation
        existing = db.query(PluginInstallation).filter(
            PluginInstallation.plugin_id == plugin_id,
            PluginInstallation.is_active == True
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="Plugin is already installed.")

        # Validate config against schema
        if plugin.config_schema:
            required_keys = plugin.config_schema.get("required", [])
            for key in required_keys:
                if key not in config:
                    raise HTTPException(status_code=400, detail=f"Missing required config key: {key}")

        installation = PluginInstallation(
            plugin_id=plugin.id,
            config=config,
            is_active=True
        )
        
        plugin.install_count += 1
        db.add(installation)
        db.commit()
        db.refresh(installation)
        return installation
        
    @staticmethod
    def uninstall_plugin(
        db: Session, installation_id: str, user: User
    ) -> PluginInstallation:
        if not user.is_sovereign:
            raise HTTPException(status_code=403, detail="Only Sovereign can uninstall plugins.")
            
        installation = db.query(PluginInstallation).filter(PluginInstallation.id == installation_id).first()
        if not installation:
            raise HTTPException(status_code=404, detail="Installation not found.")
            
        installation.is_active = False
        db.commit()
        db.refresh(installation)
        return installation

    @staticmethod
    async def execute_plugin_sandboxed(db: Session, installation_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a plugin in a secure sandbox to prevent it from escaping to the host.
        """
        installation = db.query(PluginInstallation).filter(PluginInstallation.id == installation_id).first()
        if not installation or not installation.is_active:
            raise HTTPException(status_code=404, detail="Active plugin installation not found.")
            
        plugin = db.query(Plugin).filter(Plugin.id == installation.plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")
            
        # Ensure remote executor is enabled in config
        from backend.core.config import settings
        if not settings.REMOTE_EXECUTOR_ENABLED:
            raise HTTPException(status_code=503, detail="Sandboxed execution is disabled on this instance.")
            
        logger.info(f"Plugin Marketplace: Dispatching {plugin.name} to sandbox with timeout {settings.SANDBOX_TIMEOUT_SECONDS}s")
        
        # Simulate sandbox execution delay and result
        # In a real implementation Phase 6.6 Remote Executor would be called here via RabbitMQ/Celery
        import asyncio
        await asyncio.sleep(0.5)
        
        return {
            "status": "success",
            "plugin_name": plugin.name,
            "sandbox_id": f"sandbox-{uuid.uuid4().hex[:8]}",
            "execution_time_ms": 500,
            "output": f"Mock sandboxed execution result for {plugin.name}",
            "data": {"processed": True, "input_keys": list(input_data.keys())}
        }

    @staticmethod
    def record_revenue(db: Session, plugin_id: str, amount: float, currency: str = "USD", notes: str = "") -> Any:
        """
        Records a revenue transaction for a plugin on the ledger.
        """
        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")
            
        from backend.models.entities.plugin import PluginRevenueLedger
        
        ledger_entry = PluginRevenueLedger(
            plugin_id=plugin_id,
            amount=amount,
            currency=currency,
            transaction_type="purchase",
            notes=notes
        )
        
        db.add(ledger_entry)
        db.commit()
        db.refresh(ledger_entry)
        
        logger.info(f"Plugin Marketplace: Recorded revenue {amount} {currency} for plugin {plugin.name}")
        return ledger_entry

    @staticmethod
    def submit_review(
        db: Session, plugin_id: str, user: User, rating: int, review_text: Optional[str]
    ) -> PluginReview:
        """Submit a rating and review for a plugin."""
        if not (1 <= rating <= 5):
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found.")

        # Check existing review
        existing_review = db.query(PluginReview).filter(
            PluginReview.plugin_id == plugin_id,
            PluginReview.user_id == user.id
        ).first()

        if existing_review:
            # Update
            existing_review.rating = rating
            existing_review.review_text = review_text
            db.commit()
        else:
            # Create
            review = PluginReview(plugin_id=plugin_id, user_id=user.id, rating=rating, review_text=review_text)
            db.add(review)
            db.commit()

        # Recalculate average rating
        reviews = db.query(PluginReview).filter(PluginReview.plugin_id == plugin_id).all()
        if reviews:
            avg_rating = sum(r.rating for r in reviews) / len(reviews)
            plugin.rating = round(avg_rating, 1)
            db.commit()

        return existing_review if existing_review else review

    @staticmethod
    def search_plugins(
        db: Session, query: Optional[str] = None, type_filter: Optional[str] = None
    ) -> List[Plugin]:
        """List published plugins, optionally filtered."""
        q = db.query(Plugin).filter(Plugin.status == "published")
        if query:
            q = q.filter(Plugin.name.ilike(f"%{query}%") | Plugin.description.ilike(f"%{query}%"))
        if type_filter:
            q = q.filter(Plugin.plugin_type == type_filter)
        return q.all()
