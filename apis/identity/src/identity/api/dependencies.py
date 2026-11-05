"""Request-scoped database session, bound to the actor's tenant.

The session is opened *inside* ``tenant_scope(current.tenant_id)`` so the
session-level tenant filter (CLAUDE.md §5.3) is armed for every query the request
makes — isolation is structural here, never per-query discipline. The transaction
commits when the handler returns and rolls back on any exception, so a failed request
never leaves a half-written row or an orphaned audit event.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from billing_platform.db import tenant_scope
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor, refresh_current
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY

_LOG = logging.getLogger(__name__)


async def session(request: Request, current: Actor = Depends(actor)) -> AsyncIterator[AsyncSession]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            db.sync_session.info[CAPTURE_KEY] = True
            try:
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    await lock_tenant(db, current.tenant_id)
                await refresh_current(db, request, current)
                if getattr(request.state, "api_token_id", None) is not None:
                    from billing_platform.errors import PermissionDeniedError

                    path = request.url.path
                    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
                        path.startswith("/v1/session/")
                        or "/notification-preferences/" in path
                        or "/identities" in path
                    ):
                        raise PermissionDeniedError("interactive authentication is required")
                    if path.startswith("/v1/api-tokens/") and str(
                        request.path_params.get("token_id")
                    ) != str(request.state.api_token_id):
                        raise PermissionDeniedError("an API token may revoke only itself")
                from identity.services.step_up import enforce_request

                await enforce_request(db, request, current)
                from billing_platform.audit_context import audit_actor

                with audit_actor(current.real_user_id, current.user_id):
                    yield db
                await db.commit()
                await _run_after_commit(request)
            except Exception:
                await db.rollback()
                raise


async def _run_after_commit(request: Request) -> None:
    """Run callbacks registered for *after* a successful commit.

    A generic hook (``request.state.after_commit``) used for side effects that must not
    happen until the write is durable and must never roll it back — today, permission
    cache invalidation. Failures here are swallowed on purpose: the transaction has
    already committed, so raising would turn a successful write into a 500, and every
    current hook is a cache delete whose staleness the TTL already bounds. Log only
    the exception class, never cache keys or connection details.
    """
    hooks = getattr(request.state, "after_commit", None)
    if not hooks:
        return
    for hook in hooks:
        try:
            await hook()
        except Exception as exc:  # commit succeeded; the cache TTL bounds staleness
            _LOG.warning("post-commit hook failed: %s", type(exc).__name__)
