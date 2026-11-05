"""Async source readiness is distinct from an immutable completed manifest."""

import uuid
from typing import Literal

from pydantic import Field

from reporting_contract.contract import Contract, Manifest


class SnapshotStatus(Contract):
    id: uuid.UUID
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "FAILED"]
    attempt: int = Field(ge=0)
    completed_facts: int = Field(ge=0)
    manifest: Manifest | None
    failure_code: str | None
