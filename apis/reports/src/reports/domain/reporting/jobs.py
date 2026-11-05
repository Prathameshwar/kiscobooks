"""Pure fenced job transitions. A lease is valid only until its exact deadline."""

import datetime as dt
from dataclasses import dataclass, replace
from typing import Literal

JobStatus = Literal["QUEUED", "RUNNING", "COMPLETE", "FAILED", "BLOCKED", "CANCELLED"]
TERMINAL = frozenset({"COMPLETE", "BLOCKED", "CANCELLED"})


@dataclass(frozen=True)
class JobState:
    status: JobStatus
    attempt: int = 0
    lease_until: dt.datetime | None = None
    available_at: dt.datetime | None = None


def claim(state: JobState, now: dt.datetime, *, lease_seconds: int = 60) -> JobState:
    if not 5 <= lease_seconds <= 300 or now.tzinfo is None:
        raise ValueError("invalid lease interval")
    if state.status not in {"QUEUED", "RUNNING"}:
        raise ValueError("job is not claimable")
    if state.available_at and state.available_at > now:
        raise ValueError("job is deferred")
    if state.status == "RUNNING" and state.lease_until and state.lease_until > now:
        raise ValueError("job already has a live worker")
    return JobState("RUNNING", state.attempt + 1, now + dt.timedelta(seconds=lease_seconds))


def require_lease(state: JobState, attempt: int, now: dt.datetime) -> None:
    if (
        state.status != "RUNNING"
        or state.attempt != attempt
        or state.lease_until is None
        or state.lease_until <= now
    ):
        raise ValueError("job lease is no longer owned")


def heartbeat(state: JobState, attempt: int, now: dt.datetime, seconds: int = 60) -> JobState:
    require_lease(state, attempt, now)
    if not 5 <= seconds <= 300:
        raise ValueError("invalid lease interval")
    return replace(state, lease_until=now + dt.timedelta(seconds=seconds))


def finish(
    state: JobState, attempt: int, now: dt.datetime, status: JobStatus = "COMPLETE"
) -> JobState:
    require_lease(state, attempt, now)
    if status not in {"COMPLETE", "FAILED", "BLOCKED"}:
        raise ValueError("invalid worker completion state")
    return replace(state, status=status, lease_until=None)


def cancel(state: JobState) -> JobState:
    if state.status in TERMINAL:
        if state.status == "CANCELLED":
            return state
        raise ValueError("completed evidence cannot be cancelled")
    return replace(state, status="CANCELLED", lease_until=None)


def retry(state: JobState, now: dt.datetime, *, maximum_attempts: int = 3) -> JobState:
    if state.status != "FAILED" or state.attempt >= maximum_attempts:
        raise ValueError("job cannot be retried")
    return replace(
        state,
        status="QUEUED",
        lease_until=None,
        available_at=now + dt.timedelta(seconds=min(60, 2**state.attempt)),
    )
