import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from billing_platform.company_context import CompanyContext, FinancialContext, sign_company_context
from billing_platform.db import create_engine
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from vouchers.config import Settings
from vouchers.main import create_app
from vouchers.metadata import service_metadata

SECRET = secrets.token_hex(32)
TENANT = uuid7()
COMPANY = uuid7()
USER = uuid7()
PERMISSIONS = frozenset(
    "vouchers." + action
    for action in (
        "read",
        "create",
        "edit",
        "submit",
        "approve",
        "reject",
        "issue",
        "share",
        "cancel",
        "accept",
        "decline",
        "expire",
        "post",
        "reverse",
        "export",
        "history.read",
        "operation.read",
        "operation.recover",
        "type.manage",
        "configuration.manage",
        "configuration.publish",
        "series.manage",
        "template.manage",
        "artifact.create",
        "artifact.read",
        "field.adopt",
        "counter.read",
        "counter.operate",
        "counter.close",
        "counter.supervise",
    )
)


def headers(
    *,
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
    user: uuid.UUID = USER,
    permissions: frozenset[str] = PERMISSIONS,
    policies: list[dict[str, Any]] | None = None,
    layouts: list[dict[str, Any]] | None = None,
    features: frozenset[str] = frozenset(),
    allowed_currencies: frozenset[str] = frozenset(),
    policy_namespaces: frozenset[str] = frozenset({"vouchers", "accounting"}),
    key: str | None = None,
) -> dict[str, str]:
    body = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": str(user),
            "grants": [
                {
                    "permissions": sorted(permissions),
                    "scope_type": "company",
                    "scope_id": str(company),
                    "valid_from": "2020-01-01",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    finance = FinancialContext(
        configuration_hash="a" * 64,
        company_active=True,
        books_begin_date=dt.date(2020, 4, 1),
        fiscal_year_start_month=4,
        fiscal_year_start_day=1,
        amount_precision=2,
        rounding_mode="half_up",
        timezone="Asia/Kolkata",
        default_payment_terms_days=30,
    )
    context = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        base_currency="INR",
        features=features,
        allowed_currencies=allowed_currencies,
        policy_namespaces=policy_namespaces,
        finance=finance,
        policies=tuple(policies or []),
        layouts=tuple(layouts or []),
    )
    token, signature = sign_company_context(context, SECRET.encode())
    return {
        "X-Actor-Context": base64.urlsafe_b64encode(body).decode().rstrip("="),
        "X-Actor-Signature": hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
        "X-Company-Context": token,
        "X-Company-Signature": signature,
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    import os
    import re

    from sqlalchemy.engine import make_url

    url = os.environ.get("VOUCHERS_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    native = url != "sqlite+aiosqlite:///:memory:"
    if native:
        parsed = make_url(url)
        if parsed.host not in {"localhost", "127.0.0.1", "::1"} or not re.fullmatch(
            r"vouchers_test_[0-9a-f]{32}", parsed.database or ""
        ):
            raise ValueError("native fixture requires disposable loopback voucher schema")
    database = create_engine(url)

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection: Any, record: Any) -> None:
        if not native:
            connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        if native:
            for table in reversed(service_metadata().sorted_tables):
                await connection.execute(table.delete())
        else:
            await connection.run_sync(service_metadata().create_all)
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
def app(engine: AsyncEngine) -> FastAPI:
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(SECRET),
            artifact_signing_secret=SecretStr(secrets.token_hex(32)),
        ),
        engine=engine,
    )


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://vouchers.test"
        ) as client:
            yield client


@pytest.fixture
def prefix() -> str:
    return f"/v1/companies/{COMPANY}"
