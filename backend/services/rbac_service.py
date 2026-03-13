"""
RBAC Service
Provides core logic for role-based access control and capability delegation.
"""
from typing import List, Optional, Set
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.models.entities.user import (
    User,
    ROLE_PRIMARY_SOVEREIGN,
    ROLE_DEPUTY_SOVEREIGN,
    ROLE_OBSERVER,
)
from backend.models.entities.delegation import Delegation


# Define available capabilities
CAPABILITY_VETO = "veto"
CAPABILITY_CONFIGURE_AGENTS = "configure_agents"
CAPABILITY_EXECUTE_TASKS = "execute_tasks"
CAPABILITY_MANAGE_USERS = "manage_users"

VALID_CAPABILITIES = {
    CAPABILITY_VETO,
    CAPABILITY_CONFIGURE_AGENTS,
    CAPABILITY_EXECUTE_TASKS,
    CAPABILITY_MANAGE_USERS,
}

# Role-based default capabilities
ROLE_CAPABILITIES = {
    ROLE_PRIMARY_SOVEREIGN: VALID_CAPABILITIES,
    ROLE_DEPUTY_SOVEREIGN: {CAPABILITY_VETO, CAPABILITY_CONFIGURE_AGENTS, CAPABILITY_EXECUTE_TASKS},
    ROLE_OBSERVER: set(),  # Read-only
}


class RBACService:
    @staticmethod
    def get_effective_permissions(user: User) -> Set[str]:
        """Combine base role permissions with active delegations."""
        permissions = set(ROLE_CAPABILITIES.get(user.effective_role, set()))
        
        # Add capabilities from active delegations
        for delegation in user.delegations_received:
            if delegation.is_active:
                permissions.update(delegation.capabilities)
                
        return permissions

    @staticmethod
    def has_permission(user: User, capability: str) -> bool:
        """Check if user has a specific capability."""
        return capability in RBACService.get_effective_permissions(user)

    @staticmethod
    def delegate_capabilities(
        db: Session,
        grantor: User,
        grantee_id: str,
        capabilities: List[str],
        expires_at: Optional[datetime] = None,
        reason: Optional[str] = None
    ) -> Delegation:
        """Create a new delegation of capabilities."""
        if not grantor.is_sovereign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Primary Sovereign can delegate capabilities."
            )
            
        grantee = db.query(User).filter(User.id == grantee_id).first()
        if not grantee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Grantee user not found."
            )
            
        # Validate capabilities
        invalid_caps = set(capabilities) - VALID_CAPABILITIES
        if invalid_caps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid capabilities: {invalid_caps}"
            )
            
        delegation = Delegation(
            grantor_id=grantor.id,
            grantee_id=grantee.id,
            capabilities=capabilities,
            expires_at=expires_at,
            reason=reason
        )
        
        db.add(delegation)
        db.commit()
        db.refresh(delegation)
        return delegation

    @staticmethod
    def revoke_delegation(db: Session, actor: User, delegation_id: str) -> Delegation:
        """Revoke an active delegation."""
        delegation = db.query(Delegation).filter(Delegation.id == delegation_id).first()
        if not delegation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Delegation not found."
            )
            
        # Only Sovereign or the original grantor can revoke
        if not actor.is_sovereign and actor.id != delegation.grantor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to revoke this delegation."
            )
            
        delegation.revoke()
        db.commit()
        db.refresh(delegation)
        return delegation

    @staticmethod
    def transfer_emergency_override(
        db: Session,
        current_sovereign: User,
        new_sovereign_id: str,
        reason: str
    ) -> Delegation:
        """Transfer primary sovereign role in an emergency."""
        if not current_sovereign.is_sovereign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Primary Sovereign can transfer authority."
            )
            
        new_sovereign = db.query(User).filter(User.id == new_sovereign_id).first()
        if not new_sovereign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found."
            )
            
        # Record the emergency delegation (full capabilities)
        delegation = Delegation(
            grantor_id=current_sovereign.id,
            grantee_id=new_sovereign.id,
            capabilities=list(VALID_CAPABILITIES),
            reason=reason,
            is_emergency=True
        )
        db.add(delegation)
        
        # Swap roles
        current_sovereign.role = ROLE_DEPUTY_SOVEREIGN
        new_sovereign.role = ROLE_PRIMARY_SOVEREIGN
        # Backward compatibility
        current_sovereign.is_admin = False
        new_sovereign.is_admin = True
        
        db.commit()
        db.refresh(delegation)
        db.refresh(current_sovereign)
        db.refresh(new_sovereign)
        
        return delegation

    @staticmethod
    def expire_stale_delegations(db: Session) -> int:
        """Scan and auto-revoke any delegations that have passed their expiry time."""
        now = datetime.utcnow()
        stale_delegations = db.query(Delegation).filter(
            Delegation.revoked_at == None,
            Delegation.expires_at != None,
            Delegation.expires_at < now
        ).all()
        
        count = 0
        for delegation in stale_delegations:
            delegation.revoke()
            count += 1
            
        if count > 0:
            db.commit()
            
        return count

