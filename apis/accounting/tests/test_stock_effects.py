"""The native compiler quotes the actual ledger and conserves GL/stock value."""

import asyncio
import datetime as dt
import hashlib
import secrets
from decimal import Decimal

import httpx
import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import func, select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock import StockInput
from voucher_execution.stock_facts import StockFenceFacts
from voucher_execution.transport import command_digest

from accounting.api.auth import delegated_access
from accounting.models.ledger import Journal
from accounting.models.masters import Account, AccountGroup, AccountHead
from accounting.models.stock import StockAccountPolicy, StockBalance, StockPosting
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.stock_effects import apply
from accounting.tasks.stock_quote import simulate
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_stock_ledger import item, line, values, warehouse
from tests.test_voucher_execution import command


def authority(*, extra_permissions=frozenset(), features=frozenset({"inventory"})):
    headers = ledger_headers(
        permissions=LEDGER_PERMISSIONS
        | set(extra_permissions)
        | {
            "vouchers.post",
            "vouchers.reverse",
            "accounting.stock.post",
            "accounting.stock.reverse",
            "accounting.stock.read",
            "accounting.stock.configure",
        },
        features=set(features),
    )
    context = verify_company_context(
        headers["X-Company-Context"], headers["X-Company-Signature"], SECRET.encode()
    )
    body, signature = sign_company_context(
        context.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=headers["X-Actor-Context"],
        actor_signature=headers["X-Actor-Signature"],
        company_context=body,
        company_signature=signature,
    )


async def configure(app, *, finalize_zero=True):
    result = {}
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for name, nature in (
                ("inventory_account_id", "ASSET"),
                ("receipt_clearing_account_id", "LIABILITY"),
                ("dispatch_clearing_account_id", "ASSET"),
                ("opening_offset_account_id", "EQUITY"),
                ("variance_account_id", "EXPENSE"),
            ):
                group = await db.scalar(
                    select(AccountGroup)
                    .join(AccountHead, AccountGroup.head_id == AccountHead.id)
                    .where(AccountGroup.company_id == COMPANY, AccountHead.nature == nature)
                    .limit(1)
                )
                account = Account(
                    **values(),
                    code="TEST_" + name[:18],
                    name="Stock test " + name,
                    group_id=group.id,
                    kind="GENERAL",
                    status="ACTIVE",
                )
                db.add(account)
                await db.flush()
                result[name] = account.id
            db.add(
                StockAccountPolicy(
                    **values(),
                    valid_from=dt.date(2026, 4, 1),
                    valid_to=None,
                    reason="Explicit test stock accounts",
                    **result,
                )
            )
            if finalize_zero:
                from accounting.models.stock_opening import StockOpeningControl
                from accounting.schemas.stock_opening import OpeningManifest

                manifest = OpeningManifest(
                    stock_date=dt.date(2026, 4, 1),
                    currency="INR",
                    opening_mode="COMBINED",
                    reason="Explicit test zero-stock declaration",
                )
                payload = manifest.model_dump(mode="json")
                db.add(
                    StockOpeningControl(
                        **values(),
                        currency="INR",
                        books_begin_date=manifest.stock_date,
                        status="FINALIZED",
                        manifest=payload,
                        manifest_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
                        finalized_at=utcnow(),
                    )
                )
    return result


def captured(period, product, location, *, amount="12.50"):
    stock_line = line(
        product,
        location,
        2,
        received_value=amount,
        zero_value_reason="Explicit donated goods" if Decimal(amount) == 0 else None,
    )
    stock = StockInput(
        action="RECEIPT",
        stock_date=dt.date(2026, 4, 2),
        currency="INR",
        lines=(stock_line,),
        reason="Receive test goods",
    )
    payload = {
        "stock": stock.model_dump(mode="json"),
        "mode": "ITEMS",
        "currency": "INR",
        "posting_date": "2026-04-02",
        "stock_date": "2026-04-02",
        "document_date": "2026-04-02",
        "lines": [
            {
                "line_key": str(stock_line.line_id),
                "item": {
                    "item_id": str(product.item_id),
                    "item_version": 1,
                    "unit_id": str(product.base_unit_id),
                    "actual_quantity": "2.0000",
                    "billed_quantity": "0",
                },
            }
        ],
    }
    evidence = {
        "kind": "RECEIPT_NOTE",
        "profile": "STANDARD",
        "company_configuration_hash": "a" * 64,
        "policy": {"stock": {"allow_zero_value_receipts": Decimal(amount) == 0}},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    request = command(
        period,
        protocol_version=2,
        kind="RECEIPT_NOTE",
        stock_date=stock.stock_date,
        source_payload=payload,
        content_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
        configuration_hash=digest,
        configuration_evidence=evidence | {"digest": digest},
        authority=authority(),
    )
    return request.model_copy(update={"request_hash": command_digest(request)})


def source(request, product, location):
    product = type(product).model_validate(
        product.model_dump()
        | {
            "warehouse_permissions": (
                {
                    "warehouse_id": location.warehouse_id,
                    "allowed_operations": location.allowed_operations,
                },
            )
        }
    )
    now = utcnow()
    return StockFenceFacts(
        tenant_id=request.tenant_id,
        company_id=request.company_id,
        execution_id=request.execution_id,
        actor_user_id=request.actor_user_id,
        fence_id=uuid7(),
        stock_date=request.stock_date,
        issued_at=now,
        expires_at=now + dt.timedelta(seconds=60),
        policy_generation=1,
        source_version=1,
        content_hash=request.content_hash,
        items=(product,),
        warehouses=(location,),
        bins=(),
    )


async def intent(db, request):
    row = VoucherMoneyIntent(
        **values(),
        execution_id=request.execution_id,
        voucher_id=request.voucher_id,
        journal_id=None,
        request_hash=request.request_hash,
        kind=request.kind,
        posting_date=request.posting_date,
        status="PREPARED",
        command=request.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.parametrize("quantity_mode", [None, "FIXED", "MEASURED"])
async def test_compiler_quote_rolls_everything_back_then_actual_effects_match(
    app, client, quantity_mode
):
    _, period, _ = await journal_setup(client, app)
    accounts = await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    if quantity_mode:
        from voucher_execution.quantity import QuantityUnitFact

        revision, entered_unit = uuid7(), uuid7()
        entry = {
            "entered_unit_id": str(entered_unit),
            "unit_revision_id": str(revision),
            "entered_quantity": "1",
        }
        if quantity_mode == "MEASURED":
            entry["measured_base_quantity"] = "2"
        payload = request.source_payload | {
            "stock": request.source_payload["stock"]
            | {"lines": [{**request.source_payload["stock"]["lines"][0], "quantity_entry": entry}]}
        }
        request = request.model_copy(
            update={
                "source_payload": payload,
                "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            }
        )
        request = request.model_copy(update={"request_hash": command_digest(request)})
        product = product.model_copy(
            update={
                "quantity_units": (
                    QuantityUnitFact(
                        item_id=product.item_id,
                        unit_id=entered_unit,
                        revision_id=revision,
                        usage_role="PACK" if quantity_mode == "FIXED" else "MEASURED",
                        conversion_mode=quantity_mode,
                        numerator="2" if quantity_mode == "FIXED" else None,
                        denominator="1" if quantity_mode == "FIXED" else None,
                        quantity_increment="1",
                        quantity_decimal_places=0,
                        fractional_entry=False,
                    ),
                )
            }
        )
    current = delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )
    facts = source(request, product, location)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:

            async def quote():
                return await apply(db, current, request, await intent(db, request), facts)

            quoted = await simulate(db, quote)
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
            assert await db.scalar(select(func.count(StockBalance.id))) == 0
            assert await db.scalar(select(func.count(VoucherMoneyIntent.id))) == 0
            posted = await apply(db, current, request, await intent(db, request), facts)
            assert posted.semantic_hash == quoted.semantic_hash
            assert posted.money == quoted.money
            assert [
                (entry.account_id, entry.side, entry.amount) for entry in posted.money.accounts
            ] == sorted(
                [
                    (accounts["inventory_account_id"], "DEBIT", Decimal("12.50")),
                    (accounts["receipt_clearing_account_id"], "CREDIT", Decimal("12.50")),
                ]
            )
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 1
            assert await db.scalar(select(StockBalance.quantity)) == 2


async def test_stock_definition_cannot_change_after_first_physical_effect(app, client):
    _, period, _ = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    current = delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await apply(
                db, current, request, await intent(db, request), source(request, product, location)
            )
        changed = product.model_copy(update={"base_unit_id": uuid7()})
        second = warehouse()
        another = captured(period, changed, second)
        with pytest.raises(ConflictError, match="retained stock definition"):
            async with app.state.session_factory.begin() as db:
                await apply(
                    db,
                    current,
                    another,
                    await intent(db, another),
                    source(another, changed, second),
                )


async def test_stock_source_deadline_survives_savepoint_and_blocks_root_commit(app):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            await db.begin()
            db.info["accounting_stock_source_expires_at"] = utcnow() + dt.timedelta(seconds=2)
            async with db.begin_nested():
                pass
            assert "accounting_stock_source_expires_at" in db.info
            with pytest.raises(ConflictError, match="definition lease"):
                await db.commit()
            await db.rollback()
            assert "accounting_stock_source_expires_at" not in db.info
            async with db.begin():
                pass


class Source:
    def __init__(self, facts):
        self.facts = facts
        self.calls = 0
        self.releases = 0

    async def acquire(self, request):
        self.calls += 1
        assert request.content_hash == self.facts.content_hash
        return self.facts

    async def release(self, facts):
        assert facts.fence_id == self.facts.fence_id
        self.releases += 1


async def test_native_stock_execution_posts_gl_once_and_replays_without_source(app, client):
    from accounting.tasks.stock_execution import _dispatch, dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    remote = Source(source(request, product, location))
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=remote,
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    assert {effect.effect_kind for effect in result.effects} == {
        "STOCK",
        "JOURNAL",
        "SOURCE_RECEIPT",
    }
    replay = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=None,
        enabled=True,
    )
    assert replay == result
    assert owner.calls == remote.calls == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 1
            assert await db.scalar(select(StockBalance.quantity)) == 2
            journal = await db.scalar(select(Journal))
            assert journal.status == "POSTED" and journal.total_debit == Decimal("12.50")
            assert journal.features == ["inventory"]


async def test_zero_value_stock_still_reserves_identity_and_commits_native_first_use(app, client):
    from accounting.models.fiscal import FinancialSetup
    from accounting.tasks.stock_execution import _dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location, amount="0.00")
    remote = Source(source(request, product, location))
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=remote,
        enabled=True,
    )
    assert result.outcome == "COMMITTED" and owner.calls == 1
    assert {effect.effect_kind for effect in result.effects} == {"STOCK", "SOURCE_RECEIPT"}
    assert next(iter(owner.receipts.values())).features == ["inventory"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == 2
            assert await db.scalar(select(func.count(Journal.id))) == 0
            assert (await db.scalar(select(FinancialSetup))).first_posted_at is not None


async def test_signed_delegated_stock_channel_scope_and_retained_outcome(app, client, monkeypatch):
    from voucher_execution.transport import StockExecutionClient

    from accounting.api import stock_execution as api

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    remote = Source(source(request, product, location))
    secret = secrets.token_hex(32)
    from types import SimpleNamespace

    app.state.stock_posting_client = SimpleNamespace(for_command=lambda _: owner)
    app.state.settings.stock_execution_secret = SecretStr(secret)
    app.state.settings.stock_owner_secret = SecretStr(secrets.token_hex(32))
    app.state.settings.stock_owner_url = "http://127.0.0.1:8003"
    app.state.settings.voucher_stock_enabled = True
    monkeypatch.setattr(api, "StockSourceClient", lambda *_: remote)
    transport = StockExecutionClient(client, "http://127.0.0.1", "stock.current", secret.encode())
    with pytest.raises(httpx.HTTPStatusError) as missing:
        await transport.status(request)
    assert missing.value.response.status_code == 404
    wrong_company = request.model_copy(update={"company_id": uuid7()})
    wrong_company = wrong_company.model_copy(update={"request_hash": command_digest(wrong_company)})
    with pytest.raises(httpx.HTTPStatusError) as foreign:
        await transport.send(wrong_company)
    assert foreign.value.response.status_code == 401
    result = await transport.send(request)
    assert result.outcome == "COMMITTED"
    assert remote.calls == remote.releases == owner.calls == 1
    app.state.settings.stock_owner_url = None
    app.state.settings.stock_owner_secret = None
    assert await transport.status(request) == result
    assert await transport.send(request) == result
    assert owner.calls == 1


async def test_cancel_during_stock_identity_reservation_leaves_no_physical_effect(app, client):
    from accounting.tasks.stock_execution import dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    remote = Source(source(request, product, location))
    entered, released = asyncio.Event(), asyncio.Event()
    reserve = owner.reserve

    async def delayed(*args, **kwargs):
        entered.set()
        await released.wait()
        return await reserve(*args, **kwargs)

    owner.reserve = delayed
    pending = asyncio.create_task(
        dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=remote,
            enabled=True,
        )
    )
    await asyncio.wait_for(entered.wait(), 20)
    try:
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                assert await db.scalar(select(func.count(StockPosting.id))) == 0
                assert await db.scalar(select(func.count(StockBalance.id))) == 0
        cancelled = await dispatch(
            app.state.session_factory,
            request.model_copy(update={"purpose": "CANCEL"}),
            secret=SECRET.encode(),
            client=owner,
            source_client=remote,
            enabled=True,
        )
        assert cancelled.outcome == "CANCELLED"
    finally:
        released.set()
    assert (await asyncio.wait_for(pending, 20)).outcome == "CANCELLED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
            assert await db.scalar(select(func.count(StockBalance.id))) == 0
            assert (await db.scalar(select(Journal))).status == "VOID"


@pytest.mark.parametrize("amount", ["12.50", "0.00"])
async def test_stock_reversal_compensates_quantity_value_and_gl_once(app, client, amount):
    from accounting.models.ledger import JournalLine
    from accounting.models.stock import StockCostPool, StockSourceClaim
    from accounting.tasks.stock_execution import dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    location = location.model_copy(
        update={"allowed_operations": (*location.allowed_operations, "ADJUSTMENT")}
    )
    request = captured(period, product, location, amount=amount)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    reverse = request.model_copy(
        update={
            "purpose": "REVERSE",
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "reversal_of_execution_id": request.execution_id,
            "correction_reason": "Correct the physical receipt",
            "authority": authority(),
            "authority_expires_at": utcnow() + dt.timedelta(seconds=60),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    remote = Source(source(reverse, product, location).model_copy(update={"action": "REVERSE"}))
    reversed_result = await dispatch(
        app.state.session_factory,
        reverse,
        secret=SECRET.encode(),
        client=owner,
        source_client=remote,
        enabled=True,
    )
    assert reversed_result.outcome == "COMMITTED", reversed_result
    assert (
        await dispatch(
            app.state.session_factory,
            reverse,
            secret=SECRET.encode(),
            client=None,
            source_client=None,
            enabled=False,
        )
        == reversed_result
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == 0
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == pool.value == 0 and pool.currency == "INR"
            claims = list(
                await db.scalars(
                    select(StockSourceClaim).where(StockSourceClaim.claim_type == "REVERSAL")
                )
            )
            assert (
                len(claims) == 1 and claims[0].quantity == 2 and claims[0].value == Decimal(amount)
            )
            lines = list(await db.scalars(select(JournalLine)))
            assert (
                sum(
                    (
                        line.base_amount if line.side == "DEBIT" else -line.base_amount
                        for line in lines
                    ),
                    Decimal(0),
                )
                == 0
            )
            assert await db.scalar(select(func.count(Journal.id))) == (2 if Decimal(amount) else 0)
    assert owner.calls == 2 and remote.calls == remote.releases == 1


@pytest.mark.parametrize("amount", ["12.50", "0.00"])
async def test_stock_commit_outbox_uses_only_delegated_identity_terminal_channel(
    app, client, amount
):
    from identity_posting import Receipt

    from accounting.tasks.posting_delivery import deliver
    from accounting.tasks.stock_execution import dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location, amount=amount)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    sent = []

    class Terminal:
        async def terminal(self, tenant, company, operation_id, outcome, body):
            assert (tenant, company, outcome) == (TENANT, COMPANY, "confirmed")
            assert body.intent is None and body.posted_at is not None
            expected = "accounting-journal:" if Decimal(amount) else "accounting-stock:"
            assert body.terminal_reference == expected + str(operation_id)
            sent.append(operation_id)
            return Receipt(
                operation_id=operation_id,
                reservation_id=uuid7(),
                status="confirmed",
                configuration_hash="a" * 64,
                features=["inventory"],
                confirmed_at=body.posted_at,
            )

    first = await deliver(app.state.session_factory, None, stock_client=Terminal())
    assert first.confirmed == 1 and len(sent) == 1
    second = await deliver(app.state.session_factory, None, stock_client=Terminal())
    assert second.confirmed == 0 and len(sent) == 1
