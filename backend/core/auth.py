"""
Authentication utilities for Agentium.
Handles JWT for frontend API and signature verification for webhooks.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import hmac
import hashlib

from backend.core.config import settings

# Password hashing (for future multi-user support)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# JWT Settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT token for frontend authentication."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependency to get current authenticated user from JWT.
    Used for protected API routes.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Normalize the payload to ensure consistent field names
    # Map "sub" to "username" for easier access
    normalized_payload = {
        "user_id": payload.get("user_id"),
        "username": payload.get("sub"),  # "sub" is the standard JWT subject claim
        "is_admin": payload.get("is_admin", False),
        "is_active": payload.get("is_active", True),
        "role": payload.get("role", "user"),
    }
    
    return normalized_payload

async def get_current_active_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Verify user is active."""
    if not current_user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

def verify_slack_signature(request_body: bytes, signature: str, timestamp: str, signing_secret: str) -> bool:
    """
    Verify Slack webhook signature.
    Slack sends: X-Slack-Signature and X-Slack-Request-Timestamp
    """
    if not signature or not timestamp:
        return False
    
    # Check timestamp (prevent replay attacks)
    current_timestamp = int(datetime.utcnow().timestamp())
    request_timestamp = int(timestamp)
    if abs(current_timestamp - request_timestamp) > 300:  # 5 minutes
        return False
    
    # Create basestring
    basestring = f"v0:{timestamp}:{request_body.decode()}"
    
    # Calculate signature
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)

def verify_whatsapp_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """
    Verify WhatsApp webhook signature (Meta).
    Meta sends: X-Hub-Signature-256
    """
    if not signature:
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        app_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

class WebhookAuth:
    """
    Webhook authentication checker.
    Different strategies for different channel types.
    """
    
    @staticmethod
    async def verify_whatsapp(request: Request, channel_config: dict) -> bool:
        """Verify WhatsApp webhook signature."""
        signature = request.headers.get("X-Hub-Signature-256")
        body = await request.body()
        
        app_secret = channel_config.get('app_secret')
        if not app_secret:
            # If no secret configured, accept all (not recommended for production)
            return True
        
        return verify_whatsapp_signature(body, signature, app_secret)
    
    @staticmethod
    async def verify_slack(request: Request, channel_config: dict) -> bool:
        """Verify Slack webhook signature."""
        signature = request.headers.get("X-Slack-Signature")
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        body = await request.body()
        
        signing_secret = channel_config.get('signing_secret')
        if not signing_secret:
            return True
        
        return verify_slack_signature(body, signature, timestamp, signing_secret)
    
    @staticmethod
    async def verify_telegram(request: Request, bot_token: str) -> bool:
        """
        Telegram doesn't sign webhooks, but we can verify by trying to get bot info.
        Or use secret path (which we do via webhook_path).
        """
        # Path-based verification is sufficient for Telegram
        # The webhook URL contains a secret token in the path
        return True
    
    @staticmethod
    def verify_email(request: Request) -> bool:
        """Email webhooks (SendGrid, etc.) use API keys in headers."""
        # Implement if using email receiving services
        return True