import base64
import hashlib
import hmac
import json
import os
import re
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
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry

from accounting.config import Settings
from accounting.main import create_app
from accounting.metadata import service_metadata

SECRET = secrets.token_hex(32)
ENCRYPTION = secrets.token_hex(32)
TENANT = uuid7()
COMPANY = uuid7()
USER = uuid7()
PERMISSIONS = frozenset(
    f"accounting.{family}.{action}"
    for family in (
        "head",
        "group",
        "account",
        "party",
        "tax",
        "bank",
        "policy",
        "setup",
        "mapping",
        "withholding",
    )
    for action in ("read", "manage")
) | {
    "accounting.mapping.publish",
    "accounting.import.manage",
    "accounting.export.read",
    "accounting.history.read",
}


def headers(
    *,
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
    user: uuid.UUID = USER,
    permissions: set[str] | frozenset[str] = PERMISSIONS,
    policies: list[dict[str, Any]] | None = None,
    layouts: list[dict[str, Any]] | None = None,
    registrations: list[dict[str, Any]] | None = None,
    bank_ids: set[uuid.UUID] | None = None,
    features: set[str] | None = None,
    allowed_currencies: set[str] | None = None,
    base_currency: str = "INR",
    finance: FinancialContext | None = None,
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
    context = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        base_currency=base_currency,
        finance=finance,
        features=frozenset(features or ()),
        allowed_currencies=frozenset(
            allowed_currencies
            if allowed_currencies is not None
            else {"USD"} if features and "multi_currency" in features else set()
        ),
        policies=tuple(policies or []),
        layouts=tuple(layouts or []),
        registrations=tuple(registrations or []),
        bank_ids=frozenset(bank_ids or ()),
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
    url = os.environ.get("ACCOUNTING_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    native = url != "sqlite+aiosqlite:///:memory:"
    if native:
        parsed = make_url(url)
        if parsed.host not in {"localhost", "127.0.0.1", "::1"} or not re.fullmatch(
            r"accounting_test_[0-9a-f]{32}", parsed.database or ""
        ):
            raise ValueError("native tests require a disposable loopback Accounting schema")
    database = create_engine(url)

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection: Any, record: ConnectionPoolEntry) -> None:
        if not native:
            connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        if native:
            assert await connection.scalar(text("SELECT DATABASE()")) == make_url(url).database
            # Only the validated disposable schema is cleared. Keep real FK enforcement on.
            for table in reversed(service_metadata().sorted_tables):
                if table.name == "account_group":
                    await connection.execute(table.update().values(parent_id=None))
                if table.name == "withholding_rate":
                    await connection.execute(table.update().values(supersedes_id=None))
                if table.name == "opening_batch":
                    await connection.execute(table.update().values(replacement_of_id=None))
                if table.name == "journal":
                    await connection.execute(
                        table.update().values(reversal_of_id=None, authorization_journal_id=None)
                    )
                if table.name == "invoice_record":
                    await connection.execute(
                        table.delete().where(table.c.kind.in_(["CREDIT_NOTE", "DEBIT_NOTE"]))
                    )
                if table.name == "gst_outward_record":
                    await connection.execute(table.update().values(original_record_id=None))
                if table.name == "stock_movement":
                    await connection.execute(table.update().values(source_movement_id=None))
                if table.name == "stock_posting":
                    await connection.execute(table.update().values(reverses_id=None))
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
            encryption_key=SecretStr(ENCRYPTION),
        ),
        engine=engine,
    )


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://accounting.test",
        ) as client:
            yield client
