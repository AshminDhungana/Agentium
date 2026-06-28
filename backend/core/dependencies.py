"""Shared dependency utilities for the Agentium backend.

The :func:`with_db_session` decorator eliminates the repeated boilerplate
of ``if db: return _func(db) else: with get_db_context() …`` that is
currently duplicated across dozens of service methods.

Usage::

    @with_db_session
    def do_something(self, arg1: str, db: Optional[Session] = None) -> int:
        # `db` is guaranteed to be a valid Session here
        return db.query(...).count()

    @with_db_session
    async def async_do_something(self, arg1: str, db: Optional[Session] = None) -> int:
        return db.query(...).count()

Design notes
------------
- When a caller already passes ``db`` the decorator is a transparent no-op.
- When a caller omits ``db`` a new :class:`~sqlalchemy.orm.Session` is
  created via :data:`backend.models.database.get_db_context`.
- The decorator auto-commits on success and auto-rolls back on exception,
  **only when** it is the one that created the Session (not when the caller
  provided one to keep the caller in control of the transaction boundary).
- ``self`` / ``cls`` parameters are automatically recognised so the decorator
  works unchanged on instance methods, class methods and static functions.
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, cast

from sqlalchemy.orm import Session

from backend.models.database import get_db_context

logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")
_DB_PARAM_NAME: str = "db"


class _NotSet:
    __slots__ = ()


_NOT_SET = _NotSet()


def _is_session(param: Any) -> bool:
    """Check whether *param* is an SQLAlchemy :class:`Session`."""
    return isinstance(param, Session)


def with_db_session(
    func: Callable[_P, _R] | None = None,
    *,
    _param_name: str = _DB_PARAM_NAME,
) -> Callable:
    """Decorate a (sync or async) function to auto-inject a ``db`` Session.

    Parameters
    ----------
    func:
        The callable to wrap.
    _param_name:
        Keyword-only **internal** override for the parameter that holds the
        session.  Defaults to ``"db"``.  Almost never needs changing.

    Returns
    -------
    A wrapper that is ``typing`` / ``mypy`` compatible with the original
    callable but additionally guarantees a valid :class:`Session` for the
    decorated parameter.
    """

    def _decorator(_func: Callable[_P, _R]) -> Callable[_P, _R]:
        sig = inspect.signature(_func)
        param_names = list(sig.parameters)

        # Determine which parameter receives the session (default: "db")
        try:
            db_param_idx = param_names.index(_param_name)
        except ValueError:
            # The function doesn't accept ``db`` – skip wrapping.
            return _func

        # Check whether the function is a coroutine (async)
        is_async = inspect.iscoroutinefunction(_func)

        if is_async:
            @functools.wraps(_func)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> _R:
                bound = sig.bind_partial(*args, **kwargs)
                db_arg: Any = bound.arguments.get(_param_name, _NOT_SET)

                if _param_name in bound.arguments and _is_session(db_arg):
                    # Caller already provided a session – pass through untouched.
                    return await _func(*args, **kwargs)  # type: ignore[arg-type]

                # Create a new session, bind it, then commit/rollback.
                with get_db_context() as db:
                    # Replace or inject the ``db`` kwarg / positional
                    if _param_name in bound.arguments:
                        # Was explicitly passed as e.g. db=None
                        kwargs = {**kwargs, _param_name: db}
                        return await _func(*args, **kwargs)  # type: ignore[arg-type]
                    else:
                        kwargs = {**kwargs, _param_name: db}
                        return await _func(*args, **kwargs)  # type: ignore[arg-type]

            return cast(Callable[_P, _R], _async_wrapper)

        else:
            @functools.wraps(_func)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> _R:
                bound = sig.bind_partial(*args, **kwargs)
                db_arg: Any = bound.arguments.get(_param_name, _NOT_SET)

                if _param_name in bound.arguments and _is_session(db_arg):
                    return _func(*args, **kwargs)

                with get_db_context() as db:
                    if _param_name in bound.arguments:
                        kwargs = {**kwargs, _param_name: db}
                        return _func(*args, **kwargs)
                    else:
                        kwargs = {**kwargs, _param_name: db}
                        return _func(*args, **kwargs)

            return cast(Callable[_P, _R], _sync_wrapper)

    # Support @with_db_session or @with_db_session()
    if func is not None:
        return _decorator(func)
    return _decorator


# Convenience alias for callers that want a *new* session regardless of what
# the caller passed (useful for parallel / async contexts where sessions must
# be fully isolated).
def with_new_db_session(
    func: Callable[_P, _R] | None = None,
    *,
    _param_name: str = _DB_PARAM_NAME,
) -> Callable:
    """Like :func:`with_db_session`, but **always** opens a fresh session.

    The caller-injected ``db`` parameter is ignored and a new session is
    created via :data:`get_db_context`.  Useful in ``asyncio.gather``
    coroutines where each worker must have its own session.

    Example::

        @with_new_db_session
        async def _run_isolated(self, run_id: str, db: Optional[Session] = None) -> ExperimentRun:
            # `db` is always a brand-new session here
            ...
    """

    def _decorator(_func: Callable[_P, _R]) -> Callable[_P, _R]:
        sig = inspect.signature(_func)
        is_async = inspect.iscoroutinefunction(_func)

        if is_async:
            @functools.wraps(_func)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> _R:
                with get_db_context() as db:
                    kwargs = {**kwargs, _param_name: db}
                    return await _func(*args, **kwargs)  # type: ignore[arg-type]

            return cast(Callable[_P, _R], _async_wrapper)
        else:
            @functools.wraps(_func)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> _R:
                with get_db_context() as db:
                    kwargs = {**kwargs, _param_name: db}
                    return _func(*args, **kwargs)

            return cast(Callable[_P, _R], _sync_wrapper)

    if func is not None:
        return _decorator(func)
    return _decorator
