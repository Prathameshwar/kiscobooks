"""Fresh, signed Identity authority for report workers; persisted job grants are not authority."""

import datetime as dt
import uuid

import httpx
from billing_platform.actor_authorization import ActorAuthorizationProof, ActorAuthorizationRequest
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential, request_headers, verify_response
from billing_platform.service_auth import service_request_bytes
from pydantic import Field, field_validator

from reporting_contract.transport import Owner

REPORT_PERMISSIONS = frozenset(
    {
        "item.read",
        "warehouse.read",
        "item_warehouse_policy.read",
        "report.read",
        "report.export",
        "ledger.read",
        "accounting.finance.read",
        "accounting.head.read",
        "accounting.group.read",
        "accounting.account.read",
        "accounting.party.read",
        "accounting.setup.read",
        "period.read",
        "accounting.bank.read",
        "accounting.statement.read",
    }
)


class ReportAuthority(ActorAuthorizationProof):
    read_allowed: bool = Field(strict=True)


class AuthoritySource(SnapshotCredential):
    origin: str
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")

    @field_validator("origin")
    @classmethod
    def safe_origin(cls, value: str) -> str:
        return Owner.safe_origin(value)


def require_authority(
    proof: ReportAuthority,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    actor: uuid.UUID,
    permissions: frozenset[str],
) -> None:
    now = utcnow()
    if (
        (proof.tenant_id, proof.company_id, proof.user_id) != (tenant, company, actor)
        or proof.expires_at <= now
        or proof.generated_at > now + dt.timedelta(seconds=5)
        or not permissions <= proof.permissions
        or not proof.read_allowed
    ):
        raise PermissionDeniedError("current complete-source report authority is unavailable")


async def fetch_authority(
    client: httpx.AsyncClient,
    source: AuthoritySource,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    actor: uuid.UUID,
    permissions: frozenset[str],
) -> ReportAuthority:
    if not permissions <= REPORT_PERMISSIONS or not (source.allow_enrolled_companies or any(
        scope.tenant_id == tenant and scope.company_id == company for scope in source.scopes
    )):
        raise PermissionDeniedError("worker has no authority source for this scope")
    request = ActorAuthorizationRequest(request_id=uuid7(), user_id=actor, permissions=permissions)
    path = f"/internal/v1/report-authority/{tenant}/{company}"
    body = canonical_json(request.model_dump(mode="json"))
    framed = service_request_bytes(method="POST", path=path, query="", body=body)
    secret = source.secret.get_secret_value().encode()
    headers = request_headers(
        requester="reports", owner="identity", key_id=source.key_id, secret=secret, framed=framed
    )
    headers.update({"Content-Type": "application/json", "Accept-Encoding": "identity"})
    async with client.stream(
        "POST",
        source.origin + path,
        content=body,
        headers=headers,
        follow_redirects=False,
        timeout=10,
    ) as response:
        response.raise_for_status()
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > 32768:
                raise ValueError("authority proof exceeds its bound")
        verify_response(
            requester="reports",
            owner="identity",
            key_id=source.key_id,
            secret=secret,
            framed=framed,
            body=bytes(raw),
            headers=response.headers,
        )
    proof = ReportAuthority.model_validate_json(raw)
    if proof.request_id != request.request_id:
        raise PermissionDeniedError("authority proof request binding differs")
    require_authority(proof, tenant=tenant, company=company, actor=actor, permissions=permissions)
    return proof
