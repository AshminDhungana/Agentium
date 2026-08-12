# User Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/register` alias endpoint to `backend/api/routes/auth.py` that mirrors the existing `/signup` behavior for user registration with admin approval flow.

**Architecture:** Minimal change — add a new FastAPI route at `POST /api/v1/auth/register` that delegates to the existing `signup` function. No database, model, or frontend changes needed.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, existing auth infrastructure

## Global Constraints

- Follow existing code style in `backend/api/routes/auth.py`
- Use existing `SignupRequest` / `SignupResponse` models
- Maintain rate limiting (5 attempts per 5 min) and audit logging
- No new dependencies
- No database migrations required

---

### Task 1: Add `/register` Alias Endpoint

**Files:**
- Modify: `backend/api/routes/auth.py` (add new endpoint after line 156)

**Interfaces:**
- Consumes: `SignupRequest`, `SignupResponse`, `signup()` function, `get_db` dependency, `Request`
- Produces: New `POST /api/v1/auth/register` route returning `SignupResponse`

- [ ] **Step 1: Write the failing test**

```python
# File: tests/integration/test_auth_register.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_register_creates_pending_user():
    """POST /register creates user with is_pending=True, is_active=False"""
    response = client.post("/api/v1/auth/register", json={
        "username": "newuser123",
        "email": "newuser123@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "user_id" in data
    assert "awaiting admin approval" in data["message"].lower()

def test_register_duplicate_username_returns_400():
    """Duplicate username returns 400 with correct error code"""
    # First registration
    client.post("/api/v1/auth/register", json={
        "username": "duptest",
        "email": "dup1@example.com",
        "password": "securepassword123"
    })
    # Second registration with same username
    response = client.post("/api/v1/auth/register", json={
        "username": "duptest",
        "email": "dup2@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "USERNAME_OR_EMAIL_ALREADY_REGISTERED"

def test_register_duplicate_email_returns_400():
    """Duplicate email returns 400 with correct error code"""
    client.post("/api/v1/auth/register", json={
        "username": "user1",
        "email": "same@example.com",
        "password": "securepassword123"
    })
    response = client.post("/api/v1/auth/register", json={
        "username": "user2",
        "email": "same@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "USERNAME_OR_EMAIL_ALREADY_REGISTERED"

def test_register_password_is_hashed():
    """Verify stored password is bcrypt hash, not plaintext"""
    from backend.models.database import get_db
    from backend.models.entities.user import User
    
    client.post("/api/v1/auth/register", json={
        "username": "hashtest",
        "email": "hashtest@example.com",
        "password": "plaintextpassword"
    })
    
    db = next(get_db())
    user = db.query(User).filter(User.username == "hashtest").first()
    assert user is not None
    # bcrypt hashes start with $2b$ (version identifier)
    assert user.hashed_password.startswith("$2b$")
    # Verify the hash works
    assert User.verify_password("plaintextpassword", user.hashed_password) is True

def test_register_pending_user_cannot_login():
    """Pending user (is_pending=True) gets 403 on login"""
    client.post("/api/v1/auth/register", json={
        "username": "pendinglogin",
        "email": "pendinglogin@example.com",
        "password": "securepassword123"
    })
    response = client.post("/api/v1/auth/login", json={
        "username": "pendinglogin",
        "password": "securepassword123"
    })
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == "ACCOUNT_PENDING_APPROVAL_OR_DEACTIVATED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_register.py -v`
Expected: FAIL — `POST /api/v1/auth/register` returns 404 (route doesn't exist)

- [ ] **Step 3: Write minimal implementation**

```python
# In backend/api/routes/auth.py, add after the signup function (around line 156)

@router.post(
    "/register",
    response_model=SignupResponse,
    summary="Register a new user account",
    description=(
        "Creates a pending user account. Requires admin approval before login.\n\n"
        "**Rate limit:** 5 attempts per IP per 5 minutes."
    ),
)
async def register(
    request: Request,
    payload: SignupRequest,
    db: Session = Depends(get_db),
):
    """Alias for /signup - creates a pending user account."""
    return await signup(request, payload, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_register.py -v`
Expected: PASS (all 5 tests pass)

- [ ] **Step 5: Run full auth test suite to ensure no regressions**

Run: `pytest tests/integration/test_auth*.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_auth_register.py backend/api/routes/auth.py
git commit -m "feat(auth): add /register alias endpoint for user registration"
```

---

### Task 2: Verify Frontend Integration (No Code Changes)

**Files:**
- Verify: `frontend/src/pages/SignupPage.tsx` (no changes needed)
- Verify: `frontend/src/store/authStore.ts` (no changes needed)

**Interfaces:**
- Consumes: Existing `authStore.signup()` which calls `/api/v1/auth/signup`
- Produces: Confirmation that frontend works end-to-end

- [ ] **Step 1: Manual verification — Start full stack**

```bash
docker compose up -d
# Wait for services to be healthy
```

- [ ] **Step 2: Test frontend signup flow**

1. Open `http://localhost:3000/signup` in browser
2. Fill form: username `frontendtest`, email `frontend@example.com`, password `password123` (twice)
3. Click "Create Account"
4. Verify success toast appears: "Signup request submitted! Awaiting admin approval."
5. Verify redirect to `/login` after 3 seconds
6. Verify login with same credentials shows "Account pending approval" error

- [ ] **Step 3: Verify admin approval flow**

1. Login as admin (`admin` / `admin`)
2. Navigate to admin users page
3. Find pending user `frontendtest`
4. Click approve
5. Verify user can now login successfully

- [ ] **Step 4: Commit (if any config changes needed — unlikely)**

```bash
git commit -m "docs: verify frontend registration flow works with /register alias"
```

---

### Task 3: Update TODO.md Checklist

**Files:**
- Modify: `docs/documents/TODO.md` (Section 2.1)

- [ ] **Step 1: Mark all 2.1 items as complete**

```markdown
- [x] **2.1 — User Registration**
  - [x] 2.1.1 — `POST /api/v1/auth/register` creates new user
  - [x] 2.1.2 — Duplicate username/email returns proper error
  - [x] 2.1.3 — Password is hashed before storage (verify `User.hash_password`)
  - [x] 2.1.4 — Frontend `SignupPage.tsx` form submits correctly
  - [x] 2.1.5 — Pending user flow works (admin approval if configured)
```

- [ ] **Step 2: Commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark Section 2.1 User Registration complete"
```