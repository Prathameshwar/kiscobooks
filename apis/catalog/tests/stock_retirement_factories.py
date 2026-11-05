"""Explicit native-owner doubles; ordinary Catalog tests remain unconfigured."""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from voucher_execution.retirement_transport import RetirementUnavailableError
from voucher_execution.stock_retirement import (
    RetirementEvidence,
    RetirementRelease,
    RetirementRequest,
)

from tests.conftest import ACTOR_SECRET


@dataclass
class NativeOwners:
    unavailable: bool = False
    unavailable_owner: str | None = None
    wrong_hash_owner: str | None = None
    unavailable_warehouses: set[uuid.UUID] = field(default_factory=set)
    blocked: dict[uuid.UUID, str] = field(default_factory=dict)
    checks: list[tuple[str, RetirementRequest]] = field(default_factory=list)
    releases: list[RetirementRelease] = field(default_factory=list)

    async def check(self, owner: str, request: RetirementRequest) -> RetirementEvidence:
        actor = request.verified_actor(ACTOR_SECRET.encode())
        actor.require_scope(
            "warehouse_bin.manage" if request.bin_id else "warehouse.deactivate",
            target=ScopePath(company_id=request.company_id),
        )
        self.checks.append((owner, request))
        if (
            self.unavailable
            or request.warehouse_id in self.unavailable_warehouses
            or owner == self.unavailable_owner
        ):
            raise RetirementUnavailableError("current stock owner evidence is unavailable")
        reason = self.blocked.get(request.warehouse_id) if owner == "accounting" else None
        now = utcnow()
        return RetirementEvidence.model_validate(
            {
                "owner": owner,
                "check_id": request.check_id,
                "request_hash": "b" * 64 if owner == self.wrong_hash_owner else request.digest(),
                "issued_at": now,
                "expires_at": now + dt.timedelta(seconds=30),
                "fence_id": uuid7() if owner == "vouchers" and reason is None else None,
                "result": "CLEARED" if reason is None else "BLOCKED",
                "reason": reason,
            }
        )
