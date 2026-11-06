"""Stock first use shares durable reservations without widening ordinary service scope."""

import datetime as dt
import secrets
import time

import httpx
import pytest
from billing_platform.company_context import CompanyContext, FinancialContext, sign_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from identity_posting import PostingClient, ReservationRejectedError
from identity_posting.stock import (
    StockAuthority,
    StockPostingClient,
    StockReservationIntent,
    StockReservationSource,
    StockTerminalRequest,
)
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select

from identity.config import CatalogSourceCredential, CatalogSourceScope
from identity.models import Company, PostingReservation
from identity.services.posting import configuration, digest
from tests.api_support import ACTOR_SECRET, actor_headers, grant
from tests.factories import (
    build_catalog_source_enrollment,
    build_company_feature,
    build_user,
    seed_two_companies,
)


def test_stock_reservation_accepts_its_financial_journal_features_only():
    values = {
        "operation_id": uuid7(),
        "actor_user_id": uuid7(),
        "configuration_hash": "a" * 64,
        "features": ("inventory", "credit_limits", "multi_currency"),
        "source": StockReservationSource(
            execution_id=uuid7(), command_hash="b" * 64, action="POST"
        ),
        "authority": StockAuthority(
            actor_context="actor",
            actor_signature="c" * 64,
            company_context="company",
            company_signature="d" * 64,
        ),
    }
    assert StockReservationIntent.model_validate(values).features == values["features"]
    with pytest.raises(ValidationError):
        StockReservationIntent.model_validate(values | {"features": ("inventory", "banking")})


async def fixture(app, session, tenant_a, tenant_b):
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add_all(
            [
                user,
                build_company_feature(tenant_id=tenant_a, company_id=company_id),
                build_catalog_source_enrollment(tenant_id=tenant_a, company_id=company_id),
            ]
        )
        await session.commit()
        company = await session.get(Company, company_id)
        state = await configuration(session, company)
        config_hash = digest(state)
        finance = FinancialContext.model_validate(
            {
                "configuration_hash": config_hash,
                "company_active": True,
                **{
                    key: getattr(company, key)
                    for key in FinancialContext.model_fields
                    if key not in {"version", "configuration_hash", "company_active"}
                },
            }
        )
    request_secret, response_secret = secrets.token_hex(32), secrets.token_hex(32)
    app.state.settings.stock_reservation_request_secret = SecretStr(request_secret)
    app.state.settings.stock_reservation_response_secret = SecretStr(response_secret)

    def intent(*, issued_at=None, permissions=None, operation_id=None, source=None):
        stamp = issued_at if issued_at is not None else int(time.time())
        permissions = (
            permissions
            if permissions is not None
            else ["ledger.post_journal", "accounting.stock.post", "vouchers.post"]
        )
        headers = actor_headers(
            tenant_id=tenant_a,
            user_id=user.id,
            grants=[grant(permissions, scope_type="company", scope_id=company_id)],
            issued_at=stamp,
        )
        context = CompanyContext(
            issued_at=stamp,
            tenant_id=tenant_a,
            user_id=user.id,
            company_id=company_id,
            base_currency=company.base_currency,
            finance=finance,
            features=frozenset({"inventory"}),
            policy_namespaces=frozenset({"accounting", "vouchers"}),
        )
        token, signature = sign_company_context(context, ACTOR_SECRET.encode())
        return StockReservationIntent(
            operation_id=operation_id or uuid7(),
            actor_user_id=user.id,
            configuration_hash=config_hash,
            features=("inventory",),
            source=source
            or StockReservationSource(execution_id=uuid7(), command_hash="a" * 64, action="POST"),
            authority=StockAuthority(
                actor_context=headers["X-Actor-Context"],
                actor_signature=headers["X-Actor-Signature"],
                company_context=token,
                company_signature=signature,
            ),
        )

    return company_id, user.id, request_secret, response_secret, intent


async def test_stock_delegated_first_use_replay_terminal_and_authority_immutability(
    app, session, tenant_a, tenant_b
):
    company, user, request_secret, response_secret, intent = await fixture(
        app, session, tenant_a, tenant_b
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as http:
        client = StockPostingClient(
            http, request_secret=request_secret.encode(), response_secret=response_secret.encode()
        )
        body = intent()
        result = await client.reserve(tenant_a, company, body)
        assert result.status == "pending" and result.features == ["inventory"]
        assert await client.reserve(tenant_a, company, body) == result
        with pytest.raises(ReservationRejectedError) as duplicate:
            await client.reserve(tenant_a, company, intent(source=body.source))
        assert duplicate.value.status_code == 409
        with pytest.raises(ReservationRejectedError) as foreign:
            await client.reserve(tenant_b, company, body)
        assert foreign.value.status_code == 403
        posted = utcnow()
        terminal = StockTerminalRequest(
            terminal_reference="accounting-stock:" + str(body.operation_id), posted_at=posted
        )
        confirmed = await client.terminal(
            tenant_a, company, body.operation_id, "confirmed", terminal
        )
        assert confirmed.status == "confirmed" and confirmed.confirmed_at == posted
        assert (
            await client.terminal(tenant_a, company, body.operation_id, "confirmed", terminal)
            == confirmed
        )
    with tenant_scope(tenant_a):
        row = await session.scalar(
            select(PostingReservation).where(PostingReservation.operation_id == body.operation_id)
        )
        assert row.authority_kind == "STOCK" and row.source_execution_id == body.source.execution_id
        stored_company = await session.get(Company, company)
        await session.refresh(stored_company)
        assert stored_company.first_posted_at == posted
        row.source_command_hash = "b" * 64
        with pytest.raises(ConflictError, match="immutable"):
            await session.flush()


async def test_expired_proof_only_retains_abort_and_cannot_grant_new_stock_authority(
    app, session, tenant_a, tenant_b
):
    company, _, request_secret, response_secret, intent = await fixture(
        app, session, tenant_a, tenant_b
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as http:
        client = StockPostingClient(
            http, request_secret=request_secret.encode(), response_secret=response_secret.encode()
        )
        old = intent(issued_at=int(time.time()) - 86400)
        with pytest.raises(ReservationRejectedError) as stale:
            await client.reserve(tenant_a, company, old)
        assert stale.value.status_code == 401
        denied = intent(permissions=["ledger.post_journal", "vouchers.post"])
        with pytest.raises(ReservationRejectedError) as missing:
            await client.reserve(tenant_a, company, denied)
        assert missing.value.status_code == 403
        canceled = await client.terminal(
            tenant_a,
            company,
            old.operation_id,
            "aborted",
            StockTerminalRequest(
                terminal_reference="accounting-stock:" + str(old.operation_id), intent=old
            ),
        )
        assert canceled.status == "aborted"
        fresh = intent(operation_id=old.operation_id, source=old.source)
        assert (await client.reserve(tenant_a, company, fresh)).status == "aborted"
    with tenant_scope(tenant_a):
        assert (
            await session.scalar(
                select(func.count(PostingReservation.id)).where(
                    PostingReservation.status == "pending"
                )
            )
            == 0
        )
        assert (await session.get(Company, company)).first_posted_at is None


async def test_ordinary_and_stock_credentials_cannot_terminate_each_others_reservations(
    app, session, tenant_a, tenant_b
):
    company, user, request_secret, response_secret, intent = await fixture(
        app, session, tenant_a, tenant_b
    )
    ordinary_secret, ordinary_response = secrets.token_hex(32), secrets.token_hex(32)
    app.state.settings.accounting_reservation_credentials = {
        "general.current": CatalogSourceCredential(
            secret=SecretStr(ordinary_secret),
            scopes=(CatalogSourceScope(tenant_id=tenant_a, company_id=company),),
        )
    }
    app.state.settings.accounting_reservation_response_secret = SecretStr(ordinary_response)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://identity.test"
    ) as http:
        stock = StockPostingClient(
            http, request_secret=request_secret.encode(), response_secret=response_secret.encode()
        )
        ordinary = PostingClient(
            http,
            key_id="general.current",
            request_secret=ordinary_secret.encode(),
            response_keys={"current": ordinary_response.encode()},
            issuer="accounting",
        )
        body = intent()
        await stock.reserve(tenant_a, company, body)
        with pytest.raises(ReservationRejectedError) as denied:
            await ordinary.terminal(
                tenant_a,
                company,
                operation_id=body.operation_id,
                outcome="confirmed",
                reference="accounting-journal:" + str(body.operation_id),
                posted_at=utcnow(),
            )
        assert denied.value.status_code == 403
        operation = uuid7()
        await ordinary.reserve(
            tenant_a,
            company,
            operation_id=operation,
            actor_user_id=user,
            configuration_hash=body.configuration_hash,
            features=[],
        )
        with pytest.raises(ReservationRejectedError) as denied:
            await stock.terminal(
                tenant_a,
                company,
                operation,
                "confirmed",
                StockTerminalRequest(
                    terminal_reference="accounting-journal:" + str(operation), posted_at=utcnow()
                ),
            )
        assert denied.value.status_code == 403
