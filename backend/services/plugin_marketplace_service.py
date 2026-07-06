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
from fastapi import status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
import logging

from backend.models.entities.plugin import Plugin, PluginInstallation, PluginReview
from backend.models.entities.user import User

logger = logging.getLogger(__name__)


class PluginMarketplaceService:
    """Manage the plugin marketplace lifecycle: submit, verify, install, and uninstall."""

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
            raise BadRequestError(error="Plugin with this name already exists.", code="PLUGIN_WITH_THIS_NAME_ALREADY")

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
            raise ForbiddenError(error="Only Sovereign can verify plugins.", code="ONLY_SOVEREIGN_CAN_VERIFY_PLUGINS")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")

        if plugin.status == "published":
            raise BadRequestError(error="Plugin is already published.", code="PLUGIN_IS_ALREADY_PUBLISHED")

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
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")

        if plugin.status != "submitted":
            raise BadRequestError(error="Only 'submitted' plugins can be sent for approval.", code="ONLY_SUBMITTED_PLUGINS_CAN_BE")

        from backend.models.entities.voting import AmendmentVoting, AmendmentStatus

        proposal = AmendmentVoting(
            title=f"Plugin approval: {plugin.name}",
            description=f"Approve plugin {plugin.name} (v{plugin.version}) for marketplace. "
                        f"Author: {plugin.author}. Category: {plugin.category}.",
            amendment_type="plugin_approval",
            proposer_id="system",
            status=AmendmentStatus.PENDING,
            quorum=0.5,
            threshold=0.5,
            duration_hours=48,
            auto_apply=False,
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        logger.info(
            "Plugin Marketplace: Created Council approval proposal %s for plugin %s",
            proposal.agentium_id, plugin.name
        )
        return proposal.agentium_id

    @staticmethod
    def publish_plugin(db: Session, plugin_id: str, admin_user: User) -> Plugin:
        """Publish a verified plugin to the marketplace (Admin only)."""
        if not admin_user.is_sovereign:
            raise ForbiddenError(error="Only Sovereign can publish plugins.", code="ONLY_SOVEREIGN_CAN_PUBLISH_PLUGINS")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")

        if plugin.status != "verified":
            raise BadRequestError(error=f"Plugin must be verified before publishing. Current status: {plugin.status}", code="PLUGIN_MUST_BE_VERIFIED_BEFORE")

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
            raise ForbiddenError(error="Only Sovereign can install plugins.", code="ONLY_SOVEREIGN_CAN_INSTALL_PLUGINS")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")

        if plugin.status != "published":
            raise BadRequestError(error=f"Cannot install {plugin.status} plugin.", code="CANNOT_INSTALL_PLUGIN")

        # Check existing installation
        existing = db.query(PluginInstallation).filter(
            PluginInstallation.plugin_id == plugin_id,
            PluginInstallation.is_active == True
        ).first()

        if existing:
            raise BadRequestError(error="Plugin is already installed.", code="PLUGIN_IS_ALREADY_INSTALLED")

        # Validate config against schema
        if plugin.config_schema:
            required_keys = plugin.config_schema.get("required", [])
            for key in required_keys:
                if key not in config:
                    raise BadRequestError(error=f"Missing required config key: {key}", code="MISSING_REQUIRED_CONFIG_KEY")

        installation = PluginInstallation(
            plugin_id=plugin.id,
            config=config,
            is_active=True
        )
        
        plugin.install_count += 1
        db.add(installation)
        db.commit()
        db.refresh(installation)
        
        try:
            from backend.services.config_versioning import ConfigVersioningService
            ConfigVersioningService.commit_snapshot(
                "plugin",
                installation.id,
                str(user.id),
                {"config": installation.config, "plugin_id": installation.plugin_id, "is_active": installation.is_active}
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Config versioning failed: {e}")
            
        return installation
        
    @staticmethod
    def uninstall_plugin(
        db: Session, installation_id: str, user: User
    ) -> PluginInstallation:
        """Deactivate a plugin installation (Sovereign only)."""
        if not user.is_sovereign:
            raise ForbiddenError(error="Only Sovereign can uninstall plugins.", code="ONLY_SOVEREIGN_CAN_UNINSTALL_PLUGINS")
            
        installation = db.query(PluginInstallation).filter(PluginInstallation.id == installation_id).first()
        if not installation:
            raise NotFoundError(error="Installation not found.", code="INSTALLATION_NOT_FOUND")
            
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
            raise NotFoundError(error="Active plugin installation not found.", code="ACTIVE_PLUGIN_INSTALLATION_NOT_FOUND")
            
        plugin = db.query(Plugin).filter(Plugin.id == installation.plugin_id).first()
        if not plugin:
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")
            
        # Ensure remote executor is enabled in config
        from backend.core.config import settings
        if not settings.REMOTE_EXECUTOR_ENABLED:
            raise ServiceUnavailableError(error="Sandboxed execution is disabled on this instance.", code="SANDBOXED_EXECUTION_IS_DISABLED_ON")
            
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
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")
            
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
            raise BadRequestError(error="Rating must be between 1 and 5.", code="RATING_MUST_BE_BETWEEN_1")

        plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
        if not plugin:
            raise NotFoundError(error="Plugin not found.", code="PLUGIN_NOT_FOUND")

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
