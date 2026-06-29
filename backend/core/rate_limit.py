"""
Rate limiting has been consolidated into backend.core.middleware.RateLimitMiddleware.
This file is kept for backward compatibility of imports only.
All rate-limit state is now managed by the unified Redis-backed RateLimitMiddleware.
"""

# Slowapi Limiter removed — replaced by unified RateLimitMiddleware in backend/core/middleware.py.
# If you need a rate-limit reference, import from the middleware instead:
#   from backend.core.middleware import RateLimitMiddleware, RateLimitTier, RateLimitRule
