"""Public framework discovery and request contracts, generated into the shared client."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.display import DisplayConfiguration
from billing_platform.listing import PageMeta
from pydantic import Field
from reporting_contract.contract import Contract

from reports.domain.reporting.contracts import ExportDefinition, Format, ReportDefinition, View
from reports.schemas.trial_balance_options import TrialPresentation


class DefinitionDetail(Contract):
    definition: ReportDefinition
    parameter_schema: dict[str, Any]
    formats: tuple[Format, ...] = ()
    export_limits: tuple[ExportDefinition, ...] = ()
    run_enabled: bool = False
    execution_limits: dict[str, int] = Field(default_factory=dict)
    package_limits: dict[str, int] = Field(default_factory=dict)
    navigation: dict[str, Any] = Field(default_factory=dict)


class DefinitionFields(Contract):
    code: str
    version: int
    native: dict[str, Any]
    views: tuple[View, ...]
    formats: tuple[Format, ...]
    export_limits: tuple[ExportDefinition, ...]
    execution_limits: dict[str, int] = Field(default_factory=dict)
    package_limits: dict[str, int] = Field(default_factory=dict)
    navigation: dict[str, Any] = Field(default_factory=dict)


class DefinitionCatalog(Contract):
    items: tuple[DefinitionDetail, ...]


class ParameterValidation(Contract):
    parameters: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)


class ValidatedParameters(Contract):
    code: str
    version: int
    parameters: dict[str, Any]
    parameter_hash: str
    definition_identity: str


class FrameworkRunRequest(Contract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    version: int | None = Field(default=None, ge=1)
    generation_id: uuid.UUID
    parameters: dict[str, Any] = Field(default_factory=dict)
    view: str = Field(default="default", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    execution: Literal["STANDARD", "BULK"] = "STANDARD"
    result_query: "ResultQuery | None" = None


class ResultQuery(Contract):
    q: str | None = Field(default=None, max_length=200)
    sort: str = Field(default="ordinal", min_length=1, max_length=200)
    filters: dict[str, str] = Field(default_factory=dict, max_length=16)


class DrilldownOrigin(Contract):
    parent_id: uuid.UUID
    parent_attempt: int = Field(ge=1)
    ordinal: int | None = Field(default=None, ge=1)
    mapping: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class DrilldownRequest(Contract):
    token: str = Field(max_length=4096)


class DrilldownLink(Contract):
    key: str
    title: str
    token: str
    href: str = ""
    method: Literal["GET", "POST"] = "POST"


class JobDetail(Contract):
    id: uuid.UUID
    generation_id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: Literal["RUN", "EXPORT"]
    code: str
    version: int
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "FAILED", "BLOCKED", "CANCELLED"]
    attempt: int
    completed_rows: int
    created_at: dt.datetime
    failure_code: str | None
    result: dict[str, Any] | None
    origin: DrilldownOrigin | None
    display: DisplayConfiguration | None
    title: str
    views: tuple[View, ...]
    parameters: dict[str, Any]
    view: str = "default"
    execution: Literal["STANDARD", "BULK"] = "STANDARD"
    delivery: Literal["SINGLE", "PACKAGE"] = "SINGLE"


class JobListItem(Contract):
    id: uuid.UUID
    code: str
    status: str
    kind: str
    created_at: dt.datetime


class JobPage(Contract):
    items: list[JobListItem]
    page: PageMeta


class ResultRow(Contract):
    ordinal: int
    data: dict[str, Any]
    drilldowns: tuple[DrilldownLink, ...] = ()
    source_ordinal: int | None = None


class ResultPage(Contract):
    items: list[ResultRow]
    page: PageMeta


class ExportRequest(Contract):
    format: Literal["CSV", "XLSX", "HTML", "PDF"]
    view: str = Field(default="default", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    delivery: Literal["SINGLE", "PACKAGE"] = "SINGLE"
    part_rows: int | None = Field(default=None, ge=1, le=20000)
    trial_balance: TrialPresentation | None = None


class ArtifactDownload(Contract):
    token: str
    expires_in: int = 120
    content_hash: str
    byte_count: int
    filename: str
