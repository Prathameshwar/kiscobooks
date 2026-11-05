"""Resumable owner commands. No browser session or cross-service database access.

One step is claimed with a fenced lease. Commands retain stable idempotency keys;
crashes after an owner commit replay that command, never create another company.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from billing_platform.authz import ScopePath, grant_to_wire
from billing_platform.company_context import sign_company_context
from billing_platform.db import create_engine, create_session_factory, tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, PlatformError
from billing_platform.ids import uuid7
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.api.auth import Actor
from identity.api.companies import enable_feature
from identity.api.security import lock_tenant
from identity.config import Settings
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Company, CompanySetupRun, CompanySetupStep, Tenant, User
from identity.services.accounting_context import company_context
from identity.services.audit import record
from identity.services.company_setup import STEPS
from identity.services.login import live_grants

LOG = logging.getLogger(__name__)
LEASE_SECONDS = 120


class SetupWaitError(Exception):
    def __init__(self, code: str, *, actionable: bool = False) -> None:
        self.code, self.actionable = code, actionable


@dataclass(frozen=True)
class Claim:
    tenant: uuid.UUID
    company: uuid.UUID
    run: uuid.UUID
    token: uuid.UUID
    step: str


async def live_actor(db: AsyncSession, run: CompanySetupRun) -> Actor:
    tenant = await db.get(Tenant, run.tenant_id)
    user = await db.get(User, run.created_by)
    company = await db.get(Company, run.company_id)
    if (
        tenant is None
        or tenant.status != "active"
        or user is None
        or user.status != "active"
        or company is None
        or company.status != "active"
    ):
        raise SetupWaitError("ACTOR_OR_COMPANY_UNAVAILABLE", actionable=True)
    if company.requires_step_up:
        raise SetupWaitError("INTERACTIVE_AUTHENTICATION_REQUIRED", actionable=True)
    grants, groups = await live_grants(db, user.id)
    current = Actor(run.tenant_id, user.id, grants, group_ids=groups)
    current.require_scope("company.update", target=ScopePath(company_id=company.id))
    # Changes to approved accounting facts require a new reviewed plan, never an
    # automatic rewrite of already initialized books.
    for key, expected in run.configuration.items():
        actual = getattr(company, key)
        if isinstance(actual, dt.date):
            actual = actual.isoformat()
        if actual != expected:
            raise SetupWaitError("COMPANY_CONFIGURATION_CHANGED", actionable=True)
    return current


class Worker:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        client: httpx.AsyncClient,
    ) -> None:
        self.factory, self.settings, self.client = factory, settings, client

    async def claim(self) -> Claim | None:
        now = utcnow()
        # Identifier-only installation scheduling. Every subsequent read/write is
        # tenant scoped and locks the tenant in the same order as ordinary commands.
        with unfiltered():
            async with self.factory() as db:
                candidates = (
                    await db.execute(
                        select(CompanySetupRun.tenant_id, CompanySetupRun.id)
                        .where(
                            CompanySetupRun.status.in_(("PENDING", "RETRY_WAIT", "RUNNING")),
                            CompanySetupRun.available_at <= now,
                            or_(
                                CompanySetupRun.lease_expires_at.is_(None),
                                CompanySetupRun.lease_expires_at <= now,
                            ),
                        )
                        .order_by(CompanySetupRun.available_at, CompanySetupRun.id)
                        .limit(50)
                    )
                ).all()
        for tenant, identity in candidates:
            with tenant_scope(tenant):
                async with self.factory.begin() as db:
                    await lock_tenant(db, tenant)
                    run = await db.get(CompanySetupRun, identity, with_for_update=True)
                    if (
                        run is None
                        or run.status not in {"PENDING", "RETRY_WAIT", "RUNNING"}
                        or (run.lease_expires_at and run.lease_expires_at > now)
                        or run.available_at > now
                    ):
                        continue
                    steps = {
                        row.key: row
                        for row in await db.scalars(
                            select(CompanySetupStep).where(
                                CompanySetupStep.company_id == run.company_id
                            )
                        )
                    }
                    key = next(
                        (
                            key
                            for key in STEPS
                            if steps[key].status not in {"READY", "AWAITING_OPENING"}
                        ),
                        None,
                    )
                    if key is None:
                        run.status = "COMPLETE"
                        assert run.created_by is not None
                        record(
                            db,
                            Actor(tenant, run.created_by),
                            action="company.setup_progressed",
                            entity="company_setup_run",
                            entity_id=run.id,
                            company_id=run.company_id,
                            changes={"status": {"to": "COMPLETE"}},
                        )
                        continue
                    run.status, run.lease_token = "RUNNING", uuid7()
                    run.lease_expires_at = now + dt.timedelta(seconds=LEASE_SECONDS)
                    run.attempt += 1
                    steps[key].status = "RUNNING"
                    return Claim(tenant, run.company_id, run.id, run.lease_token, key)
        return None

    async def locked_run(self, db: AsyncSession, claim: Claim) -> CompanySetupRun:
        await lock_tenant(db, claim.tenant)
        run = await db.get(CompanySetupRun, claim.run, with_for_update=True)
        if (
            run is None
            or run.lease_token != claim.token
            or (run.lease_expires_at is None or run.lease_expires_at <= utcnow())
        ):
            raise SetupWaitError("LEASE_EXPIRED")
        return run

    async def call(
        self,
        claim: Claim,
        owner: str,
        suffix: str,
        *,
        body: dict[str, Any] | None = None,
        key: str = "",
    ) -> dict[str, Any]:
        origin = self.settings.company_setup_origins.get(owner)
        if origin is None:
            raise SetupWaitError("OWNER_NOT_CONFIGURED", actionable=True)
        secret = self.settings.actor_signing_secret.get_secret_value().encode()
        with tenant_scope(claim.tenant):
            async with self.factory.begin() as db:
                run = await self.locked_run(db, claim)
                current = await live_actor(db, run)
                raw = json.dumps(
                    {
                        "issued_at": int(time.time()),
                        "tenant_id": str(claim.tenant),
                        "user_id": str(current.user_id),
                        "group_ids": sorted(map(str, current.group_ids)),
                        "grants": [
                            grant_to_wire(g)
                            for g in current.grants
                            if g.scope.scope_type == "tenant"
                            or (
                                g.scope.scope_type == "company"
                                and g.scope.scope_id == claim.company
                            )
                        ],
                    },
                    separators=(",", ":"),
                ).encode()
                if len(raw) > 24000:
                    raise SetupWaitError("ACTOR_CONTEXT_TOO_LARGE", actionable=True)
                context = await company_context(
                    db, current, claim.company, entity_prefix=owner + "."
                )
                encoded, signature = sign_company_context(context, secret)
        headers = {
            "X-Actor-Context": base64.urlsafe_b64encode(raw).decode().rstrip("="),
            "X-Actor-Signature": hmac.new(secret, raw, hashlib.sha256).hexdigest(),
            "X-Company-Context": encoded,
            "X-Company-Signature": signature,
        }
        if body is not None:
            headers["Idempotency-Key"] = f"setup-v1-{claim.run}-{key or claim.step}"
            if claim.step == "books":
                # Registration entry follows company creation. A changed authoritative
                # tax/feature selection must not replay the initial empty-books receipt.
                defaults = {
                    "features": sorted(context.features),
                    "registrations": sorted(
                        (
                            {
                                name: row.get(name)
                                for name in (
                                    "id",
                                    "tax_system",
                                    "regime",
                                    "jurisdiction_code",
                                    "valid_from",
                                    "valid_to",
                                )
                            }
                            for row in context.registrations
                        ),
                        key=lambda row: str(row["id"]),
                    ),
                }
                digest = hashlib.sha256(json.dumps(defaults, sort_keys=True).encode()).hexdigest()
                headers["Idempotency-Key"] += "-" + digest
        async with self.client.stream(
            "GET" if body is None else "POST",
            f"{origin}/{'v2' if owner == 'reports' else 'v1'}/companies/{claim.company}/{suffix}",
            headers=headers,
            json=body,
            # Accounting provisioning has a 30-second transaction deadline.
            timeout=45
            if owner == "accounting"
            and body is not None
            and suffix in {"accounting-setup/initialize", "financial-setup/initialize"}
            else 15,
        ) as response:
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > 1048576:
                    raise SetupWaitError("OWNER_RESPONSE_TOO_LARGE", actionable=True)
            if response.status_code >= 400:
                # Never persist/log an owner's raw error, which can include private facts.
                actionable = response.status_code in {401, 403, 409, 422}
                if response.status_code == 409:
                    try:
                        envelope = json.loads(payload)
                    except ValueError:
                        envelope = None
                    error = envelope.get("error") if isinstance(envelope, dict) else None
                    # The shared command executor uses 409 for transient contention too.
                    # Only its exact busy responses are retryable; business conflicts stop.
                    if (
                        isinstance(error, dict)
                        and error.get("code") == "conflict"
                        and error.get("message")
                        in (
                            "request is busy; retry with the same idempotency key",
                            "request is already in progress; retry later",
                        )
                    ):
                        actionable = False
                raise SetupWaitError(
                    "OWNER_ACCESS_DENIED"
                    if response.status_code in {401, 403}
                    else "OWNER_REVIEW_REQUIRED"
                    if actionable
                    else "OWNER_NOT_READY",
                    actionable=actionable,
                )
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise SetupWaitError("INVALID_OWNER_RESPONSE")
        if "company_id" in value and value["company_id"] != str(claim.company):
            raise SetupWaitError("OWNER_SCOPE_MISMATCH", actionable=True)
        return value

    async def execute(self, claim: Claim) -> str:
        with tenant_scope(claim.tenant):
            async with self.factory.begin() as db:
                run = await self.locked_run(db, claim)
                current = await live_actor(db, run)
                config, features = dict(run.configuration), list(run.requested_features)
                choice, reason = run.opening_choice, run.opening_reason
                if claim.step == "features":
                    db.sync_session.info[CAPTURE_KEY] = True
                    for feature in features:
                        await enable_feature(claim.company, feature, current=current, db=db)
                    return "READY"
        if claim.step == "catalog":
            result = await self.call(
                claim,
                "catalog",
                "unit-defaults/bootstrap",
                body={"expected_inventory": "inventory" in features},
                key="units",
            )
            if result.get("status") != "READY":
                raise SetupWaitError("CATALOG_REVIEW_REQUIRED", actionable=True)
            if result.get("inventory_enabled") != ("inventory" in features):
                raise SetupWaitError("CATALOG_CONFIGURATION_CHANGED")
            for suffix in ("warehouse-configuration/bootstrap", "pricing/bootstrap"):
                await self.call(claim, "catalog", suffix, body={}, key=suffix.split("/")[0])
            if config["country_code"] == "IN" and config["default_tax_system"] == "gst_in":
                await self.call(claim, "catalog", "tax-defaults/bootstrap", body={}, key="tax")
            for purpose in ("SALE", "PURCHASE"):
                plans = await self.call(
                    claim,
                    "catalog",
                    f"price-plans?purpose={purpose}&currency={config['base_currency']}&limit=2",
                )
                if not plans.get("items"):
                    raise SetupWaitError("CATALOG_DEFAULTS_PENDING")
            product_type = None
            for resource, kind in (("product-types", "kind"), ("item-groups", "allowed_kind")):
                page = await self.call(claim, "catalog", resource + "?code=DEFAULT&limit=1")
                rows = page.get("items", [])
                if not rows:
                    page = await self.call(claim, "catalog", resource + "?q=Default&limit=50")
                    rows = [
                        r for r in page.get("items", []) if r.get("name", "").lower() == "default"
                    ]
                if not rows:
                    raise SetupWaitError("CATALOG_DEFAULTS_PENDING")
                row = sorted(rows, key=lambda r: r["id"])[0]
                if row.get("is_active") is not True or row.get(kind) != "BOTH":
                    raise SetupWaitError("CATALOG_REVIEW_REQUIRED", actionable=True)
                if resource == "product-types":
                    product_type = row["id"]
            revisions = await self.call(
                claim, "catalog", f"product-types/{product_type}/revisions?published=true&limit=1"
            )
            if not revisions.get("items"):
                raise SetupWaitError("CATALOG_DEFAULTS_PENDING")
            scopes = await self.call(
                claim, "catalog", "product-configuration-scopes?scope_kind=COMPANY&limit=2"
            )
            owners = scopes.get("items", [])
            if not owners:
                raise SetupWaitError("PRODUCT_CONFIGURATION_PENDING")
            if (
                len(owners) != 1
                or owners[0].get("owner_id") != str(claim.company)
                or not owners[0].get("latest_revision")
            ):
                raise SetupWaitError("PRODUCT_CONFIGURATION_REVIEW_REQUIRED", actionable=True)
            as_of = utcnow().astimezone(ZoneInfo(config["timezone"])).date().isoformat()
            for kind in ("GOODS", "SERVICE"):
                effective = await self.call(
                    claim, "catalog", f"product-configuration/effective?kind={kind}&as_of={as_of}"
                )
                if (
                    effective.get("company_id") != str(claim.company)
                    or effective.get("kind") != kind
                    or effective.get("as_of") != as_of
                    or not effective.get("sources")
                ):
                    raise SetupWaitError("PRODUCT_CONFIGURATION_REVIEW_REQUIRED", actionable=True)
            policies = await self.call(
                claim, "catalog", f"company-pricing-policies?as_of={as_of}&limit=2"
            )
            if len(policies.get("items", [])) != 1:
                raise SetupWaitError("PRODUCT_PRICING_POLICY_REVIEW_REQUIRED", actionable=True)
        elif claim.step == "vouchers":
            result = await self.call(
                claim,
                "vouchers",
                "voucher-type-defaults/bootstrap",
                body={
                    "expected_features": [
                        f
                        for f in features
                        if f
                        in {"inventory", "bom_definitions", "approval_workflow", "multi_currency"}
                    ]
                },
            )
            if result.get("status") != "READY":
                raise SetupWaitError("VOUCHERS_REVIEW_REQUIRED", actionable=True)
        elif claim.step in {"chart", "books"}:
            suffix = "accounting-setup" if claim.step == "chart" else "financial-setup"
            await self.call(claim, "accounting", suffix + "/initialize", body={})
        elif claim.step == "calendar":
            begin = dt.date.fromisoformat(config["books_begin_date"])
            anchor = dt.date(
                begin.year, config["fiscal_year_start_month"], config["fiscal_year_start_day"]
            )
            year = await self.call(
                claim,
                "accounting",
                "fiscal-years/generate",
                body={"start_year": begin.year - (begin < anchor)},
                key="year",
            )
            periods = await self.call(
                claim, "accounting", f"fiscal-periods?fiscal_year_id={year['id']}&limit=200"
            )
            items = periods.get("items", [])
            matching = [
                p
                for p in items
                if p.get("start_date", "~") <= begin.isoformat() <= p.get("end_date", "")
            ]
            if len(matching) != 1 or matching[0].get("status") not in {"OPEN", "FUTURE"}:
                raise SetupWaitError("BOOKS_PERIOD_REVIEW_REQUIRED", actionable=True)
            for period in sorted(items, key=lambda p: p.get("start_date", "")):
                if (
                    period.get("status") == "FUTURE"
                    and period.get("end_date", "") >= begin.isoformat()
                ):
                    await self.call(
                        claim,
                        "accounting",
                        f"fiscal-periods/{period['id']}/transition",
                        body={
                            "status": "OPEN",
                            "reason": "Opened during company setup",
                            "expected_version": period["row_version"],
                        },
                        key=f"period-{period['id']}",
                    )
        elif claim.step == "opening":
            if choice != "ZERO_CONFIRMED":
                return "AWAITING_OPENING"
            review = await self.call(claim, "accounting", "financial-setup/zero-opening-review")
            if review.get("blocker") != "OPENING_ALREADY_FINALIZED":
                if not review.get("eligible"):
                    raise SetupWaitError("OPENING_REVIEW_REQUIRED", actionable=True)
                await self.call(
                    claim,
                    "accounting",
                    "financial-setup/confirm-zero-opening",
                    body={
                        "expected_setup_version": review["expected_setup_version"],
                        "reason": reason,
                    },
                )
            if "inventory" in features:
                stock = await self.call(claim, "accounting", "stock/openings/readiness")
                if stock.get("status") != "FINALIZED":
                    await self.call(
                        claim,
                        "accounting",
                        "stock/openings/confirm-zero",
                        body={
                            "expected_generation": stock["expected_generation"],
                            "reason": reason,
                        },
                        key="stock-zero",
                    )
        elif claim.step == "reports":
            result = await self.call(claim, "reports", "source-readiness")
            if result.get("state") == "NEEDS_ACTION":
                raise SetupWaitError("REPORTS_REVIEW_REQUIRED", actionable=True)
            if result.get("generation_id") is None or result.get("state") != "CURRENT":
                raise SetupWaitError("REPORTS_PENDING")
        return "READY"

    async def once(self) -> bool:
        claim = await self.claim()
        if claim is None:
            return False
        status, failure, actionable = "READY", None, False
        try:
            async with asyncio.timeout(90):
                status = await self.execute(claim)
        except SetupWaitError as exc:
            failure, actionable = exc.code, exc.actionable
        except PermissionDeniedError:
            failure, actionable = "ACTOR_ACCESS_REVOKED", True
        except (httpx.HTTPError, TimeoutError):
            failure = "OWNER_UNAVAILABLE"
        except PlatformError:
            failure, actionable = "SETUP_REVIEW_REQUIRED", True
        except Exception as exc:
            LOG.warning("Company setup attempt failed: %s", type(exc).__name__)
            failure = "SETUP_RETRY_REQUIRED"
        with tenant_scope(claim.tenant):
            async with self.factory.begin() as db:
                try:
                    run = await self.locked_run(db, claim)
                except SetupWaitError:
                    return True
                step = await db.scalar(
                    select(CompanySetupStep).where(
                        CompanySetupStep.company_id == claim.company,
                        CompanySetupStep.key == claim.step,
                    )
                )
                assert step is not None
                step.status = (
                    ("NEEDS_ACTION" if actionable else "RETRY_WAIT") if failure else status
                )
                step.failure_code = failure
                run.status = (
                    ("NEEDS_ACTION" if actionable else "RETRY_WAIT") if failure else "PENDING"
                )
                run.failure_code = failure
                if failure is None:
                    # Backoff counts consecutive attempts at the unfinished step;
                    # completing earlier steps must not penalize its first retry.
                    run.attempt = 0
                run.available_at = utcnow() + dt.timedelta(
                    seconds=min(60, 2 ** min(run.attempt, 6)) if failure else 0
                )
                run.lease_token = run.lease_expires_at = None
                assert run.created_by is not None
                record(
                    db,
                    Actor(claim.tenant, run.created_by),
                    action="company.setup_progressed",
                    entity="company_setup_run",
                    entity_id=run.id,
                    company_id=claim.company,
                    changes={"step": {"to": claim.step}, "status": {"to": step.status}},
                )
        return True


async def run_worker(settings: Settings, *, once: bool = False) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            worker = Worker(create_session_factory(engine), settings, client)
            while True:
                try:
                    worked = await worker.once()
                except Exception as exc:
                    if once:
                        raise
                    LOG.warning("Company setup storage retry: %s", type(exc).__name__)
                    worked = False
                if once:
                    return
                if not worked:
                    await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.env_file:
        import dotenv

        dotenv.load_dotenv(args.env_file)
    asyncio.run(run_worker(Settings.model_validate({}), once=args.once))
