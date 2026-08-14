"""
Unit tests for RBACService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from backend.models.entities.user import (
    User,
    ROLE_PRIMARY_SOVEREIGN,
    ROLE_DEPUTY_SOVEREIGN,
    ROLE_OBSERVER,
)
from backend.models.entities.delegation import Delegation
from backend.services.rbac_service import (
    RBACService,
    CAPABILITY_VETO,
    CAPABILITY_CONFIGURE_AGENTS,
    CAPABILITY_EXECUTE_TASKS,
    CAPABILITY_MANAGE_USERS,
    VALID_CAPABILITIES,
)
from backend.core.exceptions import BadRequestError, ForbiddenError, NotFoundError


def test_2_4_2_get_effective_permissions_sovereign():
    """Primary Sovereign has all valid capabilities."""
    user = User(username="sovereign", is_admin=True, role=ROLE_PRIMARY_SOVEREIGN)
    user.delegations_received = []
    perms = RBACService.get_effective_permissions(user)
    assert perms == VALID_CAPABILITIES


def test_2_4_2_get_effective_permissions_observer_with_delegation():
    """Observer gets base permissions + active delegated capabilities."""
    user = User(username="observer", is_admin=False, role=ROLE_OBSERVER)
    del1 = Delegation(
        grantor_id="grantor-1",
        grantee_id="user-1",
        capabilities=[CAPABILITY_VETO],
        revoked_at=None,
        expires_at=None,
    )
    user.delegations_received = [del1]
    
    perms = RBACService.get_effective_permissions(user)
    assert perms == {CAPABILITY_VETO}
    assert RBACService.has_permission(user, CAPABILITY_VETO) is True
    assert RBACService.has_permission(user, CAPABILITY_MANAGE_USERS) is False


def test_assign_role_success():
    """Assigning a role updates the user's role and is_admin flag."""
    actor = User(id="sovereign-1", username="admin", is_admin=True, role=ROLE_PRIMARY_SOVEREIGN)
    target = User(id="user-1", username="user1", is_admin=False, role=ROLE_OBSERVER)

    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.first.return_value = target

    updated = RBACService.assign_role(
        db=db_mock,
        actor=actor,
        target_user_id="user-1",
        new_role=ROLE_DEPUTY_SOVEREIGN,
    )

    assert updated.role == ROLE_DEPUTY_SOVEREIGN
    assert updated.is_admin is False
    assert db_mock.commit.called


def test_assign_role_invalid_role_raises_bad_request():
    """Assigning an invalid role name raises BadRequestError."""
    actor = User(id="sovereign-1", username="admin", is_admin=True, role=ROLE_PRIMARY_SOVEREIGN)

    db_mock = MagicMock()
    with pytest.raises(BadRequestError):
        RBACService.assign_role(
            db=db_mock,
            actor=actor,
            target_user_id="user-1",
            new_role="invalid_super_role",
        )


def test_assign_role_non_admin_raises_forbidden():
    """Non-admin and non-sovereign user cannot assign roles."""
    actor = User(id="user-2", username="user2", is_admin=False, role=ROLE_OBSERVER)

    db_mock = MagicMock()
    with pytest.raises(ForbiddenError):
        RBACService.assign_role(
            db=db_mock,
            actor=actor,
            target_user_id="user-1",
            new_role=ROLE_DEPUTY_SOVEREIGN,
        )


def test_expire_stale_delegations():
    """Stale expired delegations are marked revoked."""
    now = datetime.utcnow()
    del_expired = Delegation(
        id="del-1",
        grantor_id="g1",
        grantee_id="g2",
        capabilities=["veto"],
        expires_at=now - timedelta(hours=1),
        revoked_at=None,
    )
    
    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.all.return_value = [del_expired]

    count = RBACService.expire_stale_delegations(db_mock)
    assert count == 1
    assert del_expired.revoked_at is not None
    assert db_mock.commit.called
