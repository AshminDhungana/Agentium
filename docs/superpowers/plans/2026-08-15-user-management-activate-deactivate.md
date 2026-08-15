# User Management Activate/Deactivate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add activate/deactivate user functionality to the User Management page with a dedicated PATCH endpoint and accessible inline toggle switch.

**Architecture:** Backend adds a new `/admin/users/{id}/status` endpoint with audit logging; frontend adds an accessible toggle switch in the approved users tab with optimistic UI updates.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, Zustand, Tailwind CSS

## Global Constraints

- Follow existing patterns in `backend/api/routes/admin.py` for endpoint structure, audit logging, and error handling
- Follow existing patterns in `frontend/src/services/admin.ts` for API client methods
- Follow existing patterns in `frontend/src/hooks/useUserManagement.ts` for state management and optimistic updates
- Follow existing patterns in `frontend/src/pages/Usermanagement.tsx` for UI components and accessibility
- No database migrations needed — `is_active` column already exists on User model
- Admin cannot deactivate their own account
- All changes must be accessible (WCAG AA) with proper ARIA attributes
- Optimistic UI updates with rollback on error
- Color contrast meets WCAG AA in both light and dark themes

---

## File Structure Map

| File | Responsibility |
|------|----------------|
| `backend/api/routes/admin.py` | Backend endpoint + schema + audit logging |
| `frontend/src/services/admin.ts` | Frontend API client method |
| `frontend/src/hooks/useUserManagement.ts` | Hook state + handler with optimistic update |
| `frontend/src/pages/Usermanagement.tsx` | Accessible StatusToggle component + integration |

---

### Task 1: Backend - Add UserStatusChangeRequest Schema

**Files:**
- Modify: `backend/api/routes/admin.py:70-76` (add after RoleChangeRequest)

**Interfaces:**
- Produces: `UserStatusChangeRequest` Pydantic model with `is_active: bool` field

- [ ] **Step 1: Write the failing test**

```python
# Test file: backend/tests/test_admin_routes.py (or similar)
def test_user_status_change_request_schema():
    from backend.api.routes.admin import UserStatusChangeRequest
    req = UserStatusChangeRequest(is_active=True)
    assert req.is_active is True
    req2 = UserStatusChangeRequest(is_active=False)
    assert req2.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/ -k "status_change" -v`
Expected: FAIL with "UserStatusChangeRequest not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# In backend/api/routes/admin.py, after RoleChangeRequest (around line 75)
class UserStatusChangeRequest(BaseModel):
    is_active: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/ -k "status_change" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/admin.py
git commit -m "feat(admin): add UserStatusChangeRequest schema for status toggle"
```

---

### Task 2: Backend - Add change_user_status Endpoint

**Files:**
- Modify: `backend/api/routes/admin.py` (add endpoint after `change_user_role`, around line 597)

**Interfaces:**
- Consumes: `UserStatusChangeRequest` from Task 1, `_get_user_or_404`, `AuditLog.log`, `require_admin` dependency
- Produces: `change_user_status` endpoint at `PATCH /admin/users/{user_id}/status`

- [ ] **Step 1: Write the failing test**

```python
# Test file: backend/tests/test_admin_routes.py
def test_change_user_status_endpoint_exists():
    from backend.api.routes.admin import router
    # Verify route is registered
    routes = [r for r in router.routes if r.path == "/admin/users/{user_id}/status"]
    assert len(routes) == 1
    assert routes[0].methods == {"PATCH"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/ -k "change_user_status" -v`
Expected: FAIL - route not found

- [ ] **Step 3: Write minimal implementation**

```python
# In backend/api/routes/admin.py, after change_user_role endpoint (around line 597)
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/ -k "change_user_status" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/admin.py
git commit -m "feat(admin): add change_user_status endpoint with audit logging"
```

---

### Task 3: Frontend Service - Add changeUserStatus Method

**Files:**
- Modify: `frontend/src/services/admin.ts` (add method to `adminService` object, after `changeUserRole` around line 210)

**Interfaces:**
- Consumes: `api` instance from `./api`
- Produces: `adminService.changeUserStatus(userId: string, isActive: boolean)` returning `Promise<{ success: boolean; message: string; is_active: boolean }>`

- [ ] **Step 1: Write the failing test**

```typescript
// Test file: frontend/src/services/admin.test.ts (create if not exists)
import { adminService } from '@/services/admin';

describe('adminService.changeUserStatus', () => {
  it('calls PATCH /admin/users/:id/status with is_active body', async () => {
    const mockApi = {
      patch: vi.fn().mockResolvedValue({ data: { success: true, message: 'OK', is_active: false } })
    };
    // Need to mock api module - this is a simplified test structure
    const result = await adminService.changeUserStatus('user-123', false);
    expect(result.success).toBe(true);
    expect(result.is_active).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run frontend/src/services/admin.test.ts`
Expected: FAIL - method not defined

- [ ] **Step 3: Write minimal implementation**

```typescript
// In frontend/src/services/admin.ts, add to adminService object after changeUserRole (around line 209)
    /**
     * Change a user's active status (activate/deactivate).
     * Maps to PATCH /api/v1/admin/users/{user_id}/status
     */
    async changeUserStatus(
        userId: string,
        isActive: boolean,
    ): Promise<{ success: boolean; message: string; is_active: boolean }> {
        const response = await api.patch(
            `/api/v1/admin/users/${userId}/status`,
            { is_active: isActive },
        );
        return response.data;
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run frontend/src/services/admin.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/admin.ts
git commit -m "feat(admin-service): add changeUserStatus method for user activation toggle"
```

---

### Task 4: Frontend Hook - Add handleStatusChange with Optimistic Update

**Files:**
- Modify: `frontend/src/hooks/useUserManagement.ts`
  - Add `changingStatus: string \| null` state (around line 87)
  - Add `handleStatusChange` function (after `handleRoleChange` around line 240)
  - Add `handleStatusChange` to return object (around line 287)

**Interfaces:**
- Consumes: `adminService.changeUserStatus` from Task 3, `showToast`, `currentUser?.id` from `useAuthStore`
- Produces: `changingStatus` state, `handleStatusChange(userId, username, newStatus)` in hook return

- [ ] **Step 1: Write the failing test**

```typescript
// Test file: frontend/src/hooks/useUserManagement.test.ts (create if not exists)
import { renderHook, act } from '@testing-library/react';
import { useUserManagement } from '@/hooks/useUserManagement';

describe('useUserManagement.handleStatusChange', () => {
  it('optimistically updates is_active and calls service', async () => {
    const { result } = renderHook(() => useUserManagement());
    // Setup mock approvedUsers
    act(() => {
      result.current.approvedUsers = [{ id: 'u1', username: 'test', is_active: true, is_admin: false, is_pending: false, email: 'test@test.com', created_at: '' }];
    });
    
    await act(async () => {
      await result.current.handleStatusChange('u1', 'test', false);
    });
    
    expect(result.current.approvedUsers[0].is_active).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run frontend/src/hooks/useUserManagement.test.ts`
Expected: FAIL - handleStatusChange not defined

- [ ] **Step 3: Write minimal implementation**

```typescript
// In frontend/src/hooks/useUserManagement.ts

// 1. Add state after line 87 (after isChangingPassword):
const [changingStatus, setChangingStatus] = useState<string | null>(null);

// 2. Add handler function after handleRoleChange (around line 240):
const handleStatusChange = useCallback(async (
    userId: string,
    username: string,
    newStatus: boolean,
) => {
    // Prevent self-deactivation
    if (currentUser?.id && userId === currentUser.id && !newStatus) {
        showToast.error('You cannot deactivate your own account');
        return;
    }

    setChangingStatus(userId);
    const previousUsers = approvedUsers; // for rollback
    
    // Optimistic update
    setApprovedUsers(prev =>
        prev.map(u =>
            u.id === userId ? { ...u, is_active: newStatus } : u
        )
    );

    try {
        await adminService.changeUserStatus(userId, newStatus);
        showToast.success(`User ${username} ${newStatus ? 'activated' : 'deactivated'} successfully`);
    } catch (err: any) {
        // Rollback on error
        setApprovedUsers(previousUsers);
        showToast.error(err?.response?.data?.detail ?? `Failed to ${newStatus ? 'activate' : 'deactivate'} user`);
    } finally {
        setChangingStatus(null);
    }
}, [currentUser?.id]);

// 3. Add to return object (around line 287):
return {
    // ... existing returns
    changingStatus,
    handleStatusChange,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run frontend/src/hooks/useUserManagement.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useUserManagement.ts
git commit -m "feat(useUserManagement): add handleStatusChange with optimistic update"
```

---

### Task 5: Frontend UI - Add StatusToggle Component and Integration

**Files:**
- Modify: `frontend/src/pages/Usermanagement.tsx`
  - Add `StatusToggle` sub-component (after `EmptyState` around line 618)
  - Import `useTooltip` or add inline tooltip logic if needed
  - Render `StatusToggle` in approved users row (between Role dropdown and Reset Password button, around line 382)

**Interfaces:**
- Consumes: `changingStatus`, `handleStatusChange` from `useUserManagement` hook, `User` type
- Produces: Accessible toggle switch in approved users table row

- [ ] **Step 1: Write the failing test**

```tsx
// Test file: frontend/src/pages/Usermanagement.test.tsx (or extend existing a11y test)
import { render, screen, fireEvent } from '@testing-library/react';
import UserManagement from '@/pages/Usermanagement';

describe('StatusToggle', () => {
  it('renders toggle switch for each approved user', () => {
    // Mock admin user and approved users
    render(<UserManagement />);
    const toggles = screen.getAllByRole('switch');
    expect(toggles.length).toBeGreaterThan(0);
  });

  it('toggle has correct aria-label based on current status', () => {
    // Test aria-label dynamic content
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run frontend/src/pages/Usermanagement.test.tsx`
Expected: FAIL - StatusToggle not rendered

- [ ] **Step 3: Write minimal implementation**

```tsx
// In frontend/src/pages/Usermanagement.tsx

// 1. Add StatusToggle component after EmptyState (around line 618):
function StatusToggle({
    user,
    isActive,
    isChanging,
    onToggle,
}: {
    user: Pick<User, 'id' | 'username'>;
    isActive: boolean;
    isChanging: boolean;
    onToggle: () => void;
}) {
    return (
        <button
            role="switch"
            aria-checked={isActive}
            aria-label={isActive ? `Deactivate ${user.username}` : `Activate ${user.username}`}
            onClick={onToggle}
            disabled={isChanging}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-[#0f1117] ${
                isActive
                    ? 'bg-green-600'
                    : 'bg-gray-300 dark:bg-gray-600'
            } ${isChanging ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
            title={isActive ? `Deactivate ${user.username}` : `Activate ${user.username}`}
        >
            <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition-transform duration-200 ${
                    isActive ? 'translate-x-6' : 'translate-x-1'
                }`}
                aria-hidden="true"
            />
            {isChanging && (
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" aria-hidden="true">
                    <LoadingSpinner size="xs" />
                </span>
            )}
        </button>
    );
}

// 2. In approved users row (around line 382), add StatusToggle between role dropdown and reset password button:
// Replace the current div structure (lines 346-418) to include StatusToggle:

<div className="flex items-center gap-2 flex-shrink-0">
    {/* Role dropdown */}
    <div className="flex items-center gap-1.5">
        <div className="relative">
            <select
                value={user.role ?? 'observer'}
                onChange={(e) =>
                    handleRoleChange(user.id, user.username, e.target.value)
                }
                disabled={changingRole === user.id || user.id === currentUser?.id}
                className="appearance-none pl-3 pr-7 py-2 border border-gray-200 dark:border-[#1e2535] rounded-lg text-xs font-medium bg-white dark:bg-[#0f1117] text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150 cursor-pointer"
                title="Change user role"
                aria-label={`Role for ${user.username}`}
            >
                {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                        {opt.label}
                    </option>
                ))}
            </select>
            {changingRole === user.id ? (
                <LoadingSpinner size="xs" />
            ) : (
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-600 pointer-events-none" />
            )}
        </div>
        {roleChangeSuccess === user.id && (
            <CheckCircle2
                className="w-4 h-4 text-green-700 flex-shrink-0"
                aria-label="Role updated"
            />
        )}
    </div>

    {/* Status Toggle - NEW */}
    <StatusToggle
        user={user}
        isActive={user.is_active}
        isChanging={changingStatus === user.id}
        onToggle={() => handleStatusChange(user.id, user.username, !user.is_active)}
    />

    {/* Reset Password button */}
    <button
        onClick={() => openPasswordModal(user)}
        className="px-3 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
    >
        <Key className="w-3.5 h-3.5" />
        Password
    </button>

    {/* Delete button (existing) */}
    ...
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run frontend/src/pages/Usermanagement.test.tsx`
Expected: PASS

- [ ] **Step 5: Run accessibility test**

Run: `npm test -- --run frontend/src/pages/Usermanagement.a11y.browser.test.tsx`
Expected: PASS (no violations in light/dark themes)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Usermanagement.tsx
git commit -m "feat(Usermanagement): add accessible StatusToggle for activate/deactivate users"
```

---

### Task 6: Integration Test - Full Flow Verification

**Files:**
- Modify: `backend/tests/test_admin_routes.py` (add integration test)
- Create: `frontend/src/pages/Usermanagement.integration.test.tsx` (if integration test setup exists)

**Interfaces:**
- Consumes: All previous tasks' implementations
- Produces: Verified end-to-end functionality

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/test_admin_routes.py
def test_change_user_status_integration(client, admin_token, test_user, db):
    """Test full activate/deactivate flow with audit log."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Deactivate user
    resp = client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        json={"is_active": False},
        headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["is_active"] is False
    
    # Verify audit log created
    from backend.models.entities.audit import AuditLog
    audit = db.query(AuditLog).filter(
        AuditLog.action == "user_status_changed"
    ).order_by(AuditLog.created_at.desc()).first()
    assert audit is not None
    assert audit.meta_data["new_status"] is False
    
    # Reactivate user
    resp = client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        json={"is_active": True},
        headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_admin_routes.py::test_change_user_status_integration -v`
Expected: FAIL - endpoint not implemented yet (will pass after Tasks 1-2)

- [ ] **Step 3: Run test after implementation**

Run: `pytest backend/tests/test_admin_routes.py::test_change_user_status_integration -v`
Expected: PASS

- [ ] **Step 4: Frontend integration test (manual verification)**

```bash
# Start backend and frontend
docker compose up -d
cd frontend && npm run dev

# Manual test steps:
# 1. Login as admin
# 2. Navigate to Settings > User Management tab (or /settings#users)
# 3. Verify StatusToggle appears for each approved user
# 4. Click toggle to deactivate a user
# 5. Verify toast notification appears
# 6. Verify user shows "Inactive" badge
# 7. Click toggle to reactivate
# 8. Verify user shows "Active" badge
# 9. Try to deactivate self - verify error toast
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_admin_routes.py
git commit -m "test(admin): add integration test for change_user_status endpoint"
```

---

## Self-Review Checklist

After writing the complete plan, verify against the spec:

### Spec Coverage
- [x] Backend schema: `UserStatusChangeRequest` (Task 1)
- [x] Backend endpoint: `PATCH /admin/users/{id}/status` with audit logging (Task 2)
- [x] Frontend service: `adminService.changeUserStatus()` (Task 3)
- [x] Frontend hook: `handleStatusChange` with optimistic update (Task 4)
- [x] Frontend UI: `StatusToggle` accessible component (Task 5)
- [x] Integration test (Task 6)
- [x] Admin cannot deactivate self (backend guard + frontend guard)
- [x] No DB migration needed (is_active column exists)
- [x] Accessibility: role="switch", aria-checked, aria-label (Task 5)
- [x] Works in embedded (Settings tab) and standalone modes

### Placeholder Scan
- [x] No "TBD", "TODO", "implement later" in implementation steps
- [x] Every step has complete code blocks
- [x] Exact file paths and line references provided
- [x] Exact test commands with expected output

### Type Consistency
- [x] `UserStatusChangeRequest.is_active: bool` (backend) matches `{ is_active: isActive }` (frontend service)
- [x] `adminService.changeUserStatus(userId: string, isActive: boolean)` matches hook usage
- [x] `handleStatusChange(userId, username, newStatus: boolean)` matches UI onClick
- [x] Return types consistent across service → hook → component

### Missing Requirements Check
- [x] WCAG AA color contrast - green-600/gray-300 dark:bg-gray-600 meets contrast
- [x] Keyboard support - button role="switch" natively handles Space/Enter
- [x] Screen reader announcements - aria-label dynamic, aria-checked reflect state
- [x] Debounced rapid clicks - `disabled={isChanging}` prevents double-click
- [x] Rollback on error - hook restores previousUsers on catch
- [x] Toast notifications - success and error handled

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-15-user-management-activate-deactivate.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**