# tests/api/test_auth_verify_sovereign.py
# Fix 1 regression (TODO 12.4.2): POST /api/v1/auth/verify must return the
# persisted user's sovereign fields (DB truth), not the JWT claims.
#
# The bug: login embeds the RAW role column ("observer" for the default
# admin) in the JWT, and /verify built its response from JWT claims. On page
# refresh, the frontend's deriveIsSovereign() saw role="observer" -> false ->
# SovereignRoute kicked the sovereign back to "/".
from datetime import datetime, timezone

from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.database import get_db
from backend.core.auth import create_access_token
from backend.models.entities.user import User


async def _make_sovereign(db_session) -> User:
    admin = db_session.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_admin=True,
            is_active=True,
            is_pending=False,
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
    return admin


async def test_verify_returns_sovereign_fields_from_db(db_session):
    admin = await _make_sovereign(db_session)

    # JWT carries role="observer" (the raw-column bug simulation) — the
    # response must still return DB truth for the sovereign fields.
    token = create_access_token(data={
        "sub": admin.username,
        "user_id": admin.id,
        "role": "observer",
        "is_admin": True,
        "is_active": True,
    })

    async def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    user = resp.json()["user"]
    assert user["is_sovereign"] is True
    assert user["role"] == "primary_sovereign"
    assert user["is_admin"] is True


async def test_verify_for_nonadmin_still_has_db_role(db_session):
    suffix = f"{datetime.now(timezone.utc).timestamp():.0f}"
    user_row = User(
        username=f"plainuser_{suffix}",
        email=f"plain_{suffix}@agentium.local",
        hashed_password=User.hash_password("password123"),
        is_admin=False,
        is_active=True,
        is_pending=False,
        # Non-observer role: ObserverReadOnlyMiddleware 403s POST /verify for
        # observers, so the DB-role passthrough is only reachable via a valid
        # non-observer role. deputy_sovereign also pins the 12.4.2 boundary —
        # sovereign-adjacent but NOT primary_sovereign.
        role="deputy_sovereign",
    )
    db_session.add(user_row)
    db_session.commit()
    db_session.refresh(user_row)

    token = create_access_token(data={
        "sub": user_row.username,
        "user_id": user_row.id,
        "role": "deputy_sovereign",
        "is_admin": False,
        "is_active": True,
    })

    async def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    user = resp.json()["user"]
    # Non-admin: effective_role == the raw role column — unchanged behavior.
    assert user["is_sovereign"] is False
    assert user["role"] == "deputy_sovereign"
