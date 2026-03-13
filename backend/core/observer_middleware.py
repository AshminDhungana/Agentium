"""
Observer Read-Only Middleware
=============================
Enforces that any user whose effective role is `observer` can only use safe HTTP methods.
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.auth import verify_token
from backend.models.database import SessionLocal
from backend.models.entities.user import User

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

class ObserverReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow safe methods immediately without checking DB
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # Skip paths that don't require auth like docs or login
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/api/v1/auth/login"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # Let the actual route handlers deal with missing auth
            return await call_next(request)

        token = auth_header.split(" ")[1]
        try:
            payload = verify_token(token)
            if not payload:
                return await call_next(request)
            
            user_id = payload.get("user_id")
            if not user_id:
                return await call_next(request)

            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return await call_next(request)
                
                # If effective role is observer, block state-changing methods
                if user.effective_role == "observer":
                    logger.warning(
                        f"Blocked {request.method} {path} for observer user {user.username}"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "Observer role is read-only. Cannot execute state-changing requests."
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Error in ObserverReadOnlyMiddleware: {e}")
            # Fail open and let route dependency handle invalid tokens
            return await call_next(request)

        return await call_next(request)
