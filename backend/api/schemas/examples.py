"""Shared OpenAPI response examples for all route modules.

Every route should import the models it needs and reference them
through the ``responses={...}`` parameter.
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SuccessResponseExample(BaseModel):
    """Standard 200/201 success envelope."""
    success: bool = Field(True, description="Whether the operation succeeded.")
    message: str = Field("Operation completed.", description="Human-readable status message.")
    data: Optional[Dict[str, Any]] = Field(None, description="Payload data.")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Resource created successfully.",
                "data": {"id": "550e8400-e29b-41d4-a716-446655440000"},
            }
        }


class ErrorResponseExample(BaseModel):
    """Standard error envelope returned by typed exception handlers."""
    error: str = Field(..., description="Short human-readable error message.")
    code: str = Field(..., description="Machine-readable error code.")
    detail: Optional[Dict[str, Any]] = Field(None, description="Optional extra context.")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Resource not found.",
                "code": "NOT_FOUND",
                "detail": {"resource_id": "550e8400-e29b-41d4-a716-446655440000"},
            }
        }


class PaginatedResponseExample(BaseModel):
    """Standard paginated list envelope."""
    items: list = Field([], description="List of resources.")
    total: int = Field(0, description="Total count of items.")
    page: int = Field(1, description="Current page number (1-based).")
    page_size: int = Field(20, description="Items per page.")

    class Config:
        json_schema_extra = {
            "example": {
                "items": ["...snip..."],
                "total": 100,
                "page": 1,
                "page_size": 20,
            }
        }


def build_responses(success_model: type = None, error_model: type = None):
    """Return a reusable ``responses`` dict for a route decorator.

    Parameters
    ----------
    success_model
        Pydantic model to use for 200/201 success responses.
    error_model
        Pydantic model to use for all error responses (400, 401, 403, etc.).

    Returns
    -------
    dict
        A dict suitable for the ``responses=`` keyword argument of FastAPI
        route decorators.
    """
    err = error_model or ErrorResponseExample
    out = {
        400: {"description": "Bad Request", "model": err},
        401: {"description": "Unauthorized", "model": err},
        403: {"description": "Forbidden", "model": err},
        404: {"description": "Not Found", "model": err},
        429: {"description": "Too Many Requests", "model": err},
        500: {"description": "Internal Server Error", "model": err},
    }
    if success_model:
        out[200] = {"description": "Success", "model": success_model}
        out[201] = {"description": "Created", "model": success_model}
    return out


class ListResponseExample(BaseModel):
    """Standard list response envelope for endpoints returning arrays."""
    items: list = Field([], description="List of resources.")
    total: int = Field(0, description="Total count of items.")

    class Config:
        json_schema_extra = {
            "example": {
                "items": ["..."],
                "total": 42,
            }
        }

