"""Signed owner projection synchronization outside every voucher write transaction."""

import asyncio
import logging
import uuid

import httpx
from billing_platform.db import create_engine, create_session_factory
from billing_platform.diagnostics import log_failure
from billing_platform.errors import AuthenticationRequiredError, ConflictError, PlatformError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import request_headers, verify_response
from billing_platform.service_auth import (
    CompanyServiceScope,
    service_request_bytes,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.schemas.owners import Owner as Owner
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOUCHERS_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    snapshot_owners: tuple[Owner, ...] = Field(default=(), max_length=12)


def check_configuration(settings: Settings) -> None:
    if not settings.snapshot_owners:
        raise ValueError("source delivery requires at least one configured owner")
    if any(owner.allow_enrolled_companies for owner in settings.snapshot_owners) and not any(
        owner.owner == "identity" and owner.allow_enrolled_companies
        for owner in settings.snapshot_owners
    ):
        raise ValueError("automatic company discovery requires its configured Identity owner")


class EnrollmentPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scopes: tuple[CompanyServiceScope, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=4096)


async def discover(client: httpx.AsyncClient, identity: Owner) -> tuple[CompanyServiceScope, ...]:
    if identity.owner != "identity" or not identity.allow_enrolled_companies:
        raise AuthenticationRequiredError("Identity enrollment discovery is not configured")
    scopes: list[CompanyServiceScope] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    cursors: set[str] = set()
    cursor = None
    async with asyncio.timeout(30):
        for _ in range(100):
            path = "/internal/v1/voucher-enrollments"
            raw = canonical_json({"limit": 200, "cursor": cursor})
            framed = service_request_bytes(method="POST", path=path, query="", body=raw)
            response = await client.post(
                identity.origin + path,
                content=raw,
                headers=request_headers(
                    requester="vouchers",
                    owner="identity",
                    key_id=identity.key_id,
                    secret=identity.secret.get_secret_value().encode(),
                    framed=framed,
                ),
            )
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ConflictError("enrollment response exceeds its bound")
            verify_response(
                requester="vouchers",
                owner="identity",
                key_id=identity.key_id,
                secret=identity.secret.get_secret_value().encode(),
                framed=framed,
                body=response.content,
                headers=response.headers,
            )
            page = EnrollmentPage.model_validate_json(response.content)
            for scope in page.scopes:
                key = scope.tenant_id, scope.company_id
                if key in seen or len(scopes) >= 10000:
                    raise ConflictError("duplicate or excessive source enrollment")
                seen.add(key)
                scopes.append(scope)
            if page.next_cursor is None:
                return tuple(scopes)
            if not page.scopes or page.next_cursor in cursors:
                raise ConflictError("source enrollment cursor did not advance")
            cursors.add(page.next_cursor)
            cursor = page.next_cursor
    raise ConflictError("source enrollment exceeded its page bound")


async def synchronize(
    factory: async_sessionmaker[AsyncSession], client: httpx.AsyncClient, owner: Owner
) -> int:
    total = 0
    for scope in owner.scopes:
        entities = {
            "identity": ("company", "vouchers.voucher", "vouchers.voucher_item", "salesperson"),
            "catalog": (
                "item",
                "item_transaction_policy",
                "item_unit_revision",
                "unit",
                "item_regulatory_classification",
            ),
            "accounting": (
                "party",
                "broker_party",
                "party_drug_licence",
                "account",
                "fiscal_period",
            ),
        }[owner.owner]
        for entity in entities:
            after = None
            for _ in range(100):
                path = f"/internal/v1/voucher-sources/{scope.tenant_id}/{scope.company_id}/{entity}"
                params = {"limit": "128"} | ({"after": after} if after else {})
                url = httpx.URL(owner.origin + path, params=params)
                framed = service_request_bytes(
                    method="GET", path=url.path, query=url.query.decode(), body=b""
                )
                response = await client.get(
                    url,
                    headers=request_headers(
                        requester="vouchers",
                        owner=owner.owner,
                        key_id=owner.key_id,
                        secret=owner.secret.get_secret_value().encode(),
                        framed=framed,
                    ),
                )
                response.raise_for_status()
                verify_response(
                    requester="vouchers",
                    owner=owner.owner,
                    key_id=owner.key_id,
                    secret=owner.secret.get_secret_value().encode(),
                    framed=framed,
                    body=response.content,
                    headers=response.headers,
                )
                data = response.json()
                bundle = SourceBundle.model_validate(data["bundle"])
                if bundle.tenant_id != scope.tenant_id or bundle.company_id != scope.company_id:
                    raise AuthenticationRequiredError("owner returned another company")
                await apply_bundle(factory, bundle, owner.owner)
                total += 1
                after = data["next_after"]
                if after is None:
                    break
                uuid.UUID(after)
            else:
                raise ConflictError("owner snapshot exceeds supported page bound")
    return total


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            while True:
                dynamic = None
                if any(owner.allow_enrolled_companies for owner in settings.snapshot_owners):
                    identity = next(
                        (
                            owner
                            for owner in settings.snapshot_owners
                            if owner.owner == "identity" and owner.allow_enrolled_companies
                        ),
                        None,
                    )
                    if identity is None:
                        raise ValueError("automatic source owners require Identity discovery")
                    try:
                        dynamic = await discover(client, identity)
                    except (httpx.HTTPError, PlatformError, TimeoutError, ValueError) as error:
                        log_failure(
                            logging.getLogger("vouchers.sources"),
                            service="vouchers",
                            event="source.enrollment.deferred",
                            error=error,
                        )
                for owner in settings.snapshot_owners:
                    scopes = owner.scopes
                    if owner.allow_enrolled_companies:
                        if dynamic is None:
                            continue
                        scopes = tuple(
                            {
                                (scope.tenant_id, scope.company_id): scope
                                for scope in (*owner.scopes, *dynamic)
                            }.values()
                        )
                    for scope in scopes:
                        try:
                            await synchronize(
                                factory, client, owner.model_copy(update={"scopes": (scope,)})
                            )
                        except (httpx.HTTPError, PlatformError, TimeoutError, ValueError) as error:
                            log_failure(
                                logging.getLogger("vouchers.sources"),
                                service="vouchers",
                                event="source.snapshot.deferred",
                                error=error,
                            )
                await asyncio.sleep(30)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    configuration = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # settings accepts env-file at runtime
    check_configuration(configuration)
    if not args.check_config:
        asyncio.run(run(configuration))
