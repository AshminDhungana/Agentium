# User Management Page — Activate/Deactivate Users Design

**Date**: 2026-08-15  
**Status**: Approved  
**Related**: TODO.md section 2.6.2 — "Admin can activate/deactivate users"

---

## 1. Problem Statement

The User Management page (`Usermanagement.tsx`) currently supports:
- ✅ Listing all users (pending + approved tabs)
- ✅ Approve/reject pending users
- ✅ Change user roles via dropdown
- ✅ Reset user passwords
- ✅ Delete users with confirmation

**Missing**: Ability for admins to activate/deactivate approved users by toggling the `is_active` field.

---

## 2. Design Decision

**Approach**: Dedicated PATCH endpoint + inline toggle switch (Approach 1)

### Rationale
- Clean REST semantics — status is independent of role
- Optimistic UI updates for instant feedback
- Matches existing pattern (separate endpoints for approve/reject/delete/role/password)
- Minimal code changes following established patterns
- Accessible toggle with keyboard support and screen reader labels

---

## 3. Backend Changes

### 3.1 New Pydantic Schema
```python
# In backend/api/routes/admin.py
class UserStatusChangeRequest(BaseModel):
    is_active: bool
```

### 3.2 New Endpoint
```python
@router.patch(
    "/admin/users/{user_id}/status",
    summary="Change user active status",
    description="Activate or deactivate a user account. Admin cannot deactivate their own account.",
    responses=build_responses(None),
)
async def change_user_status(
    user_id: str,
    request: UserStatusChangeRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Guard: cannot deactivate own account
    if user_id == admin.get("user_id") and not request.is_active:
        raise BadRequestError(
            error="Cannot deactivate your own account",
            code="CANNOT_DEACTIVATE_YOUR_OWN_ACCOUNT"
        )

    user = _get_user_or_404(db, user_id)
    old_status = user.is_active
    user.is_active = request.is_active
    user.updated_at = datetime.now(timezone.utc)

    # Audit log
    audit_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHORIZATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="user_status_changed",
        target_type="user",
        target_id=str(user.id),
        description=f"Admin changed status for {user.username}: {'Active' if old_status else 'Inactive'} → {'Active' if request.is_active else 'Inactive'}",
        meta_data={
            "target_username": user.username,
            "old_status": old_status,
            "new_status": request.is_active,
        },
    )
    db.add(audit_entry)
    db.commit()

    return {
        "success": True,
        "message": f"User {user.username} {'activated' if request.is_active else 'deactivated'} successfully",
        "is_active": request.is_active,
    }
```

---

## 4. Frontend Changes

### 4.1 Service Layer (`frontend/src/services/admin.ts`)
```typescript
async changeUserStatus(
    userId: string,
    isActive: boolean,
): Promise<{ success: boolean; message: string; is_active: boolean }> {
    const response = await api.patch(
        `/api/v1/admin/users/${userId}/status`,
        { is_active: isActive },
    );
    return response.data;
}
```

### 4.2 Hook (`frontend/src/hooks/useUserManagement.ts`)
- Add `changingStatus: string | null` state (userId being toggled)
- Add `handleStatusChange(userId, username, newStatus)` with optimistic update
- Update both `approvedUsers` and `filteredApprovedUsers` via state mapping
- Toast notification on success/error

### 4.3 UI Component (`frontend/src/pages/Usermanagement.tsx`)
- Add `StatusToggle` sub-component (accessible switch)
- Place between Role dropdown and Reset Password button
- Show loading spinner during request
- Tooltip: "Activate {username}" / "Deactivate {username}"
- Disable for current user (prevent self-deactivation)

---

## 5. Accessibility Requirements

- `<button role="switch" aria-checked={isActive}>` pattern
- `aria-label` dynamically: "Activate {username}" / "Deactivate {username}"
- Keyboard: Space/Enter to toggle, focus visible
- Screen reader announces state change
- Color contrast meets WCAG AA (green/gray with sufficient contrast)

---

## 6. Acceptance Criteria

1. ✅ Admin can toggle any approved user's `is_active` status
2. ✅ UI updates optimistically (instant feedback)
3. ✅ Audit log entry created for each status change
4. ✅ Admin cannot deactivate their own account
5. ✅ Deactivated users cannot log in (backend auth already checks `is_active`)
6. ✅ Accessible toggle with keyboard support and screen reader labels
7. ✅ Works in both embedded (Settings tab) and standalone modes
8. ✅ Debounced rapid clicks handled gracefully (ignore during loading)

---

## 7. Testing

### Unit Tests
- `handleStatusChange` optimistic update / rollback logic
- `adminService.changeUserStatus` request/response shape

### Integration Tests
- Full flow: toggle → API call → audit log → UI update
- Self-deactivation prevention
- Deactivated user login attempt returns 401

### E2E / Accessibility
- axe-core scan on UserManagement component (light/dark themes)
- Keyboard navigation through toggle switches
- Screen reader announcements verified

---

## 8. Rollout

- **No migration needed** — `is_active` column already exists
- **Backward compatible** — new endpoint only, no breaking changes
- **Feature flag not required** — admin-only, safe to enable immediately

---

## 9. Files to Modify

| File | Change Type |
|------|-------------|
| `backend/api/routes/admin.py` | Add schema + endpoint |
| `frontend/src/services/admin.ts` | Add `changeUserStatus` |
| `frontend/src/hooks/useUserManagement.ts` | Add state + handler |
| `frontend/src/pages/Usermanagement.tsx` | Add `StatusToggle` component + render |

---

**Design Approved**: Ready for implementation planning.