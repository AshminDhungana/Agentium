from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from backend.models.database import get_db
from backend.models.entities.user import User
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedError, ForbiddenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise UnauthorizedError(
                error="Could not validate credentials",
                code="INVALID_CREDENTIALS",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise UnauthorizedError(
            error="Could not validate credentials",
            code="INVALID_CREDENTIALS",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Synchronous database query
    user = db.query(User).filter(User.username == username).first()

    if user is None:
        raise UnauthorizedError(
            error="Could not validate credentials",
            code="USER_NOT_FOUND",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise ForbiddenError(
            error="User account is inactive",
            code="ACCOUNT_INACTIVE",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user."""
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current admin user."""
    if not current_user.is_admin:
        raise ForbiddenError(
            error="Admin access required",
            code="ADMIN_ONLY",
        )
    return current_user