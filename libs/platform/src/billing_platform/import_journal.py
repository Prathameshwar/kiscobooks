"""Reusable evidence for resumable owner imports with per-record transactions.

Owners attach these mixins to their existing job tables. Preflight may call owners
outside a transaction; checkpoints belong in the native record transaction.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import Any

from sqlalchemy import JSON, Integer, LargeBinary, String
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.types import UtcDateTime, Uuid7


class RevisionEvidence:
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_format: Mapped[str] = mapped_column(String(10), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    content: Mapped[bytes | None] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql", "mariadb"), nullable=True, deferred=True
    )
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class AttemptEvidence:
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class ResultEvidence:
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class StepBudget:
    """Bound a request by records and elapsed time; callers checkpoint each record."""

    def __init__(self, maximum: int, seconds: float = 35) -> None:
        if not 1 <= maximum <= 200 or not 0 < seconds <= 45:
            raise ValueError("step capacity must be bounded")
        self.maximum, self.deadline, self.used = maximum, time.monotonic() + seconds, 0

    def take(self) -> bool:
        if self.used >= self.maximum or time.monotonic() >= self.deadline:
            return False
        self.used += 1
        return True

    def alive(self) -> bool:
        return time.monotonic() < self.deadline
