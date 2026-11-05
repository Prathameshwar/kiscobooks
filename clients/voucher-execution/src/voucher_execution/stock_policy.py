"""Native Accounting inspection of an exact Catalog policy delivery manifest.

The legacy consumer name remains `billing` at Catalog's adapter boundary. This
read-only owner protocol cannot publish definitions or authorize stock effects.
"""

import datetime as dt
import hashlib
import uuid
from typing import Literal, Self

from billing_platform.idempotency import canonical_json
from pydantic import Field, model_validator

from voucher_execution.stock_policy_manifest import policy_manifest_digest
from voucher_execution.contracts import Contract
from voucher_execution.stock_retirement import ActorProof

PATH = "/internal/v1/stock-policy-inspections"
KEY = "stock-policy.current"
Flag = Literal[
    "allow_sale_issue",
    "allow_purchase_receipt",
    "allow_transfer_in",
    "allow_transfer_out",
    "allow_customer_return_receipt",
    "allow_supplier_return_issue",
    "allow_opening_stock",
    "allow_adjustment",
]
Default = Literal[
    "default_sale_warehouse_id",
    "default_purchase_warehouse_id",
    "default_customer_return_warehouse_id",
    "default_opening_warehouse_id",
]
DEFAULTS: tuple[Default, ...] = (
    "default_sale_warehouse_id",
    "default_purchase_warehouse_id",
    "default_customer_return_warehouse_id",
    "default_opening_warehouse_id",
)


class PolicyLocation(Contract):
    warehouse_id: uuid.UUID
    revision: int = Field(strict=True, ge=1)
    flags: frozenset[Flag]


class PolicyManifest(Contract):
    locations: tuple[PolicyLocation, ...] = Field(max_length=500)
    defaults: dict[Default, uuid.UUID | None] = Field(max_length=4)

    @model_validator(mode="after")
    def unique_locations(self) -> Self:
        keys = {row.warehouse_id for row in self.locations}
        if len(keys) != len(self.locations) or any(not key.int for key in keys):
            raise ValueError("policy manifest needs unique real locations")
        return self

    def digest(self) -> str:
        return policy_manifest_digest(self.locations, self.defaults, DEFAULTS)


class PolicyInspection(Contract):
    check_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    release_id: uuid.UUID
    release_revision: int = Field(strict=True, ge=1)
    effective_date: dt.date
    manifest: PolicyManifest
    authority: ActorProof = Field(repr=False)

    @model_validator(mode="after")
    def contained_defaults(self) -> Self:
        keys = {row.warehouse_id for row in self.manifest.locations}
        if any(
            value not in keys
            for value in self.manifest.defaults.values()
            if value is not None
        ):
            raise ValueError("delivered defaults must name included locations")
        if any(
            not getattr(self, field).int
            for field in (
                "check_id",
                "tenant_id",
                "company_id",
                "actor_user_id",
                "release_id",
            )
        ):
            raise ValueError("policy inspection needs real scoped references")
        return self

    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json(self.model_dump(mode="json", exclude={"authority"}))
        ).hexdigest()


class PolicyInspectionResult(Contract):
    check_id: uuid.UUID
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    issued_at: dt.datetime
    expires_at: dt.datetime
    result: Literal["APPLIED", "REJECTED", "PENDING"]
    reason: Literal["UNSUPPORTED_OPERATION", "SOURCE_UNAVAILABLE"] | None = None

    @model_validator(mode="after")
    def closed_result(self) -> Self:
        if (self.result == "APPLIED") != (self.reason is None):
            raise ValueError("policy inspection needs its exact reason")
        if self.result == "PENDING" and self.reason != "SOURCE_UNAVAILABLE":
            raise ValueError("pending owner enforcement requires an unavailable source")
        if (
            self.issued_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not dt.timedelta(0)
            < self.expires_at - self.issued_at
            <= dt.timedelta(seconds=30)
        ):
            raise ValueError("policy inspection needs a bounded aware lifetime")
        return self
