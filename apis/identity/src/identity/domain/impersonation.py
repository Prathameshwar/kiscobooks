"""The rule that an impersonation session is usable only while live.

docs/identity-schema.md §4.8, docs/roles-permissions.md §1.6. The exit criterion: an
expired session is refused **even when ``ended_at`` is still null** — the sweeper closes
it eventually, but the hard ceiling (``expires_at``) is enforced on every use. No
framework, no ORM: the caller passes the two timestamps and ``now``.
"""

from __future__ import annotations

import datetime as dt

from billing_platform.errors import PermissionDeniedError


def is_session_active(
    *, ended_at: dt.datetime | None, expires_at: dt.datetime, now: dt.datetime
) -> bool:
    """Live means not explicitly ended and not past its expiry."""
    return ended_at is None and now < expires_at


def assert_session_usable(
    *, ended_at: dt.datetime | None, expires_at: dt.datetime, now: dt.datetime
) -> None:
    """403 if the session has ended or expired — the check every impersonated request
    makes before honouring the ``on_behalf_of`` context."""
    if not is_session_active(ended_at=ended_at, expires_at=expires_at, now=now):
        raise PermissionDeniedError("this impersonation session has ended or expired")
