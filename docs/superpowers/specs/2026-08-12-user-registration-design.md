# User Registration Design Document

**Date**: 2026-08-12  
**Feature**: 2.1 — User Registration  
**Status**: Approved

---

## Overview

Implement the user registration flow as specified in TODO.md Section 2.1. The backend and frontend infrastructure is already largely in place; only one minimal change is required.

---

## Current Implementation Status

| Sub-task | Status | Notes |
|----------|--------|-------|
| 2.1.1 `POST /api/v1/auth/register` | ❌ Missing | Only `/signup` exists; need `/register` alias |
| 2.1.2 Duplicate username/email error | ✅ Done | Returns 400 with `USERNAME_OR_EMAIL_ALREADY_REGISTERED` |
| 2.1.3 Password hashing (`User.hash_password`) | ✅ Done | SHA-256 pre-hash + bcrypt |
| 2.1.4 Frontend `SignupPage.tsx` form | ✅ Done | Submits via `authStore.signup()` |
| 2.1.5 Pending user flow (admin approval) | ✅ Done | `is_pending=True`, admin approve/reject endpoints exist |

---

## Required Changes

### 1. Add `/register` Alias Endpoint (2.1.1)

**File**: `backend/api/routes/auth.py`

Add a new endpoint that delegates to the existing `signup` logic:

```python
@router.post(
    "/register",
    response_model=SignupResponse,
    summary="Register a new user account",
    description="Creates a pending user account. Requires admin approval before login.\n\n**Rate limit:** 5 attempts per IP per 5 minutes."
)
async def register(
    request: Request,
    payload: SignupRequest,
    db: Session = Depends(get_db),
):
    """Alias for /signup - creates a pending user account."""
    return await signup(request, payload, db)
```

**Rationale**: 
- Zero behavior change — exact same logic as `/signup`
- Maintains backward compatibility
- Satisfies TODO requirement for `/api/v1/auth/register`

---

## No Other Changes Needed

### Duplicate Detection (2.1.2) ✅
Already implemented at lines 120-126 in `auth.py`:
```python
existing_user = db.query(User).filter(
    (User.username == payload.username) | (User.email == payload.email)
).first()
if existing_user:
    raise BadRequestError(error="Username or email already registered", code="USERNAME_OR_EMAIL_ALREADY_REGISTERED")
```

### Password Hashing (2.1.3) ✅
Already implemented in `backend/models/entities/user.py`:
- `hash_password()`: SHA-256 pre-hash + bcrypt (handles passwords >72 bytes)
- `verify_password()`: Verifies pre-hashed password against bcrypt
- Called in `User.create_user()` (line 167)

### Frontend Form (2.1.4) ✅
`SignupPage.tsx` already:
- Validates client-side (username ≥3 chars, password ≥8 chars, passwords match)
- Calls `authStore.signup()` → POST `/api/v1/auth/signup`
- Shows success toast and redirects to `/login` after 3s
- Displays "awaiting admin approval" message

### Pending User Flow (2.1.5) ✅
- New users: `is_pending=True`, `is_active=False` (User model defaults)
- Login rejects pending users: 403 `ACCOUNT_PENDING_APPROVAL_OR_DEACTIVATED`
- Admin endpoints exist:
  - `GET /admin/users/pending` — list pending users
  - `POST /admin/users/{id}/approve` — activate user
  - `POST /admin/users/{id}/reject` — delete pending user
- Full audit logging for signup, approval, rejection

---

## Testing Plan

### Integration Tests (to be added)
1. **POST `/register` creates user** — verify `is_pending=True`, `is_active=False`
2. **POST `/register` duplicate username** — returns 400 with correct error code
3. **POST `/register` duplicate email** — returns 400 with correct error code
4. **Password hash verification** — stored hash is bcrypt, not plaintext
5. **Pending user cannot login** — returns 403 when `is_pending=True`
6. **Admin approve flow** — `POST /admin/users/{id}/approve` sets `is_pending=False`, `is_active=True`
7. **Admin reject flow** — `POST /admin/users/{id}/reject` deletes user

### Frontend Tests
- Existing `SignupPage.a11y.browser.test.tsx` covers accessibility
- Verify form submits to `/register` alias (update test if needed)

---

## Implementation Notes

- **No database migrations needed** — schema unchanged
- **No frontend changes needed** — form already works; `/register` is backend-only alias
- **Rollback**: Simply remove the `/register` endpoint if issues arise
- **Configuration**: Per user decision, admin approval remains mandatory (no `AUTO_APPROVE_REGISTRATIONS` flag)

---

## Acceptance Criteria

- [ ] `POST /api/v1/auth/register` returns 201 with `SignupResponse` (success, message, user_id)
- [ ] Created user has `is_pending=True`, `is_active=False`
- [ ] Duplicate username/email returns 400 `USERNAME_OR_EMAIL_ALREADY_REGISTERED`
- [ ] Password stored as bcrypt hash (verifiable via `User.verify_password`)
- [ ] Frontend signup form works end-to-end (submit → success toast → redirect)
- [ ] Pending user cannot login (403)
- [ ] Admin can approve/reject via existing endpoints