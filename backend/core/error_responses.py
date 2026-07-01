"""Shared error-response model and FastAPI exception-handler registration.

Intended usage::

    from backend.core.exceptions import BadRequestError

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        if not exists(item_id):
            raise BadRequestError(
                error=f"Item {item_id} not found",
                code="NOT_FOUND",
                detail={"item_id": item_id},
            )
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.exceptions import AgentiumError


class HTTPErrorResponse(BaseModel):
    error: str
    code: str
    detail: dict | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Invalid request payload",
                "code": "VALIDATION_ERROR",
                "detail": {"field": "name", "reason": "required"},
            }
        }


def _make_json(exc: AgentiumError) -> JSONResponse:
    body = HTTPErrorResponse(error=exc.error, code=exc.code, detail=exc._detail)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(), headers=dict(exc.headers or {}))


async def _agentium_error_handler(request: Request, exc: AgentiumError) -> JSONResponse:
    return _make_json(exc)


def make_error_response(status_code: int, error: str, code: str, detail: dict | None = None, headers: dict | None = None) -> JSONResponse:
    body = HTTPErrorResponse(error=error, code=code, detail=detail)
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=dict(headers or {}))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AgentiumError, _agentium_error_handler)
