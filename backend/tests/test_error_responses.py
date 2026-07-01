"""Integration tests for typed exception hierarchy and error response envelope."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from backend.core.exceptions import (
    AgentiumError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    TooLargeError,
    RateLimitError,
    InternalServerError,
    ServiceUnavailableError,
)
from backend.core.error_responses import register_error_handlers


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/bad-request")
    def _bad_req():
        raise BadRequestError("Invalid input", code="INVALID_INPUT")

    @app.get("/not-found")
    def _not_found():
        raise NotFoundError("User missing", code="USER_NOT_FOUND")

    @app.get("/forbidden")
    def _forbidden():
        raise ForbiddenError("No admin access", code="ADMIN_ONLY")

    @app.get("/unauthorized")
    def _unauthorized():
        raise UnauthorizedError("Missing token", code="TOKEN_MISSING")

    @app.get("/rate-limit")
    def _rate_limit():
        raise RateLimitError("Too fast", code="RATE_LIMITED", detail={"retry_after": 60})

    @app.get("/conflict")
    def _conflict():
        raise ConflictError("Already exists", code="DUPLICATE")

    @app.get("/too-large")
    def _too_large():
        raise TooLargeError("Payload too large", code="PAYLOAD_TOO_LARGE")

    @app.get("/internal")
    def _internal():
        raise InternalServerError("Boom", code="INTERNAL")

    @app.get("/service-unavailable")
    def _service_unavailable():
        raise ServiceUnavailableError("Down", code="DOWN")

    return TestClient(app)


def assert_envelope(data: dict, *, error: str, code: str):
    assert data.get("error") == error
    assert data.get("code") == code
    assert "detail" in data


def test_bad_request(client):
    resp = client.get("/bad-request")
    assert resp.status_code == 400
    assert_envelope(resp.json(), error="Invalid input", code="INVALID_INPUT")


def test_not_found(client):
    resp = client.get("/not-found")
    assert resp.status_code == 404
    assert_envelope(resp.json(), error="User missing", code="USER_NOT_FOUND")


def test_forbidden(client):
    resp = client.get("/forbidden")
    assert resp.status_code == 403
    assert_envelope(resp.json(), error="No admin access", code="ADMIN_ONLY")


def test_unauthorized(client):
    resp = client.get("/unauthorized")
    assert resp.status_code == 401
    assert_envelope(resp.json(), error="Missing token", code="TOKEN_MISSING")


def test_rate_limit(client):
    resp = client.get("/rate-limit")
    assert resp.status_code == 429
    assert_envelope(resp.json(), error="Too fast", code="RATE_LIMITED")
    assert resp.json()["detail"] == {"retry_after": 60}


def test_conflict(client):
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert_envelope(resp.json(), error="Already exists", code="DUPLICATE")


def test_too_large(client):
    resp = client.get("/too-large")
    assert resp.status_code == 413
    assert_envelope(resp.json(), error="Payload too large", code="PAYLOAD_TOO_LARGE")


def test_internal(client):
    resp = client.get("/internal")
    assert resp.status_code == 500
    assert_envelope(resp.json(), error="Boom", code="INTERNAL")


def test_service_unavailable(client):
    resp = client.get("/service-unavailable")
    assert resp.status_code == 503
    assert_envelope(resp.json(), error="Down", code="DOWN")


def test_inherits_fastapi_http_exception():
    err = BadRequestError("msg", code="C")
    assert isinstance(err, HTTPException)
    assert err.status_code == 400
