import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field
from reporting_contract.contract import Contract

from reports.schemas.report_parameters import SourceParameters


class Gstr3bParameters(SourceParameters):
    registration_id: uuid.UUID
    period: str = Field(pattern=r"^20[0-9]{2}-(?:(?:0[1-9]|1[0-2])|Q[1-4])$")


class GstContext(Contract):
    calculation_version: int = Field(ge=1)
    registrations: list[dict[str, Any]]
    can_configure: bool
    can_capture: bool
    can_review: bool
    can_prepare: bool
    rule_version: str


class GstReviewRequest(Contract):
    state: Literal["REVIEWED", "EXTERNALLY_FILED"]
    reference: str = Field(min_length=1, max_length=120)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    filed_date: dt.date | None = None


class GstReviewItem(GstReviewRequest):
    id: uuid.UUID
    job_id: uuid.UUID
    created_at: dt.datetime


class GstReviewHistory(Contract):
    items: list[GstReviewItem]
