"""Partition arithmetic and retention floors (docs/audit.md §6) — pure, no database."""

from __future__ import annotations

import datetime as dt

import pytest

from audit.config import Settings
from audit.domain import partitions, retention

_SETTINGS = Settings(
    database_url="sqlite+aiosqlite:///:memory:",
    actor_signing_secret="x",  # type: ignore[arg-type]
    cursor_signing_secret="x",  # type: ignore[arg-type]
)


def test_partition_name_and_bound() -> None:
    assert partitions.partition_name(2026, 9) == "p202609"
    # The exclusive RANGE bound is the first instant of the next month.
    assert partitions.upper_bound(2026, 12) == dt.date(2027, 1, 1)
    assert partitions.upper_bound_literal(2026, 9) == "2026-10-01 00:00:00"


def test_add_months_rolls_the_year() -> None:
    assert partitions.add_months(2026, 11, 3) == (2027, 2)
    assert partitions.add_months(2026, 2, -3) == (2025, 11)


def test_months_to_provision_includes_current_through_ahead() -> None:
    months = partitions.months_to_provision(dt.date(2026, 9, 11), ahead=3)
    assert months == [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]


def test_missing_months_skips_existing() -> None:
    existing = {"p202609", "p202610", "pmax"}
    missing = partitions.missing_months(existing, today=dt.date(2026, 9, 11), ahead=3)
    assert missing == [(2026, 11), (2026, 12)]


def test_parse_partition_name() -> None:
    assert partitions.parse_partition_name("p202609") == (2026, 9)
    assert partitions.parse_partition_name("pmax") is None
    assert partitions.parse_partition_name("p202613") is None  # month 13


def test_is_expired_uses_the_partitions_newest_instant() -> None:
    # A 1-year floor: the month is droppable only once its upper bound is >1y in the past.
    today = dt.date(2027, 10, 2)
    assert partitions.is_expired(2026, 9, today=today, retention_days=365)  # bound 2026-10-01
    assert not partitions.is_expired(2026, 10, today=today, retention_days=365)  # bound 2026-11-01


def test_droppable_never_returns_pmax_and_is_ordered() -> None:
    existing = {"p202601", "p202602", "pmax", "p202609"}
    dropped = partitions.droppable(existing, today=dt.date(2030, 1, 1), retention_days=365)
    assert "pmax" not in dropped
    assert dropped == sorted(dropped)


def test_retention_days_per_category() -> None:
    assert retention.retention_days("security", _SETTINGS) == 7 * 366
    assert retention.retention_days("access", _SETTINGS) == 366
    assert retention.max_retention_days(_SETTINGS) == 7 * 366


def test_unknown_category_has_no_floor() -> None:
    with pytest.raises(ValueError, match="retention floor"):
        retention.retention_days("nope", _SETTINGS)
