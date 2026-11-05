"""Impersonation session-liveness, tested with no database (docs/identity-schema.md §4.8)."""

from __future__ import annotations

import datetime as dt

import pytest
from billing_platform.errors import PermissionDeniedError

from identity.domain.impersonation import assert_session_usable, is_session_active

_START = dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
_EXPIRES = dt.datetime(2026, 5, 1, 1, tzinfo=dt.UTC)


def test_live_session_is_active() -> None:
    now = dt.datetime(2026, 5, 1, 0, 30, tzinfo=dt.UTC)
    assert is_session_active(ended_at=None, expires_at=_EXPIRES, now=now)
    assert_session_usable(ended_at=None, expires_at=_EXPIRES, now=now)  # no raise


def test_expired_session_is_refused_even_when_not_ended() -> None:
    """The phase exit: an expired session is refused even with ``ended_at`` still null."""
    now = dt.datetime(2026, 5, 1, 2, tzinfo=dt.UTC)  # past expiry
    assert not is_session_active(ended_at=None, expires_at=_EXPIRES, now=now)
    with pytest.raises(PermissionDeniedError):
        assert_session_usable(ended_at=None, expires_at=_EXPIRES, now=now)


def test_ended_session_is_refused() -> None:
    now = dt.datetime(2026, 5, 1, 0, 30, tzinfo=dt.UTC)
    ended = dt.datetime(2026, 5, 1, 0, 20, tzinfo=dt.UTC)
    assert not is_session_active(ended_at=ended, expires_at=_EXPIRES, now=now)
    with pytest.raises(PermissionDeniedError):
        assert_session_usable(ended_at=ended, expires_at=_EXPIRES, now=now)
