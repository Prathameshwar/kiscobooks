"""Purchase print content, versions and download evidence.

Pure rendering tests: no browser. The real-browser check at the end is selected with
`-k real_chromium` and, on a machine whose sandboxed browser cannot start, needs the explicit
local-only switch (see `test_print_sandbox_switch.py`).
"""

import copy
import io
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, USER, headers
from sqlalchemy import select
from test_purchase_print import queued, snapshot
from voucher_execution.invoice import InvoiceInput
from voucher_execution.printing import PrintLedger, PurchasePrintFacts

from vouchers.domain.purchase_print import (
    LAYOUT_VERSION,
    RENDERER_VERSION,
    assemble_snapshot,
    page_templates,
    render_html,
    snapshot_hash,
    validate_snapshot,
)
from vouchers.events.audit_contract import AUDIT_EVENTS
from vouchers.models.printing import VoucherPrintJob
from vouchers.tasks import print_worker

NUMBER = "PURCHASE/FY2026-2027/000002"
INJECTION = '"><img src=//evil onerror=x></style><script>alert(1)</script>'


def posted(number: str | None = NUMBER):
    value = snapshot()
    value["document"]["status"] = "POSTED"
    value["calculation_source"] = "POSTED"
    value["labels"]["voucher_number"] = number
    return value


def line_key(value) -> str:
    return value["document"]["invoice"]["supplies"][0]["line_key"]


def with_settlement(value, tenders=(), allocations=()):
    value["document"]["invoice"]["tenders"] = list(tenders)
    value["document"]["invoice"]["allocations"] = list(allocations)
    return value


def tender(amount="20000.5000", mode="CASH", reference=None, instrument_date=None):
    return {
        "tender_key": str(uuid7()),
        "mode": mode,
        "amount": amount,
        "currency": "INR",
        "reference": reference,
        "instrument_date": instrument_date,
    }


# --- D7a: renderer and layout versions ---


def test_renderer_and_layout_versions_change_with_the_printed_output():
    # @3 (2026-11-03): a designed layout prints as drawn (canvas_print.py).
    assert RENDERER_VERSION == "purchase-pdf@4"
    assert LAYOUT_VERSION == "purchase-a4@3"
    value = snapshot()
    assert value["renderer_version"] == RENDERER_VERSION
    assert value["layout"]["version"] == LAYOUT_VERSION
    # The version is itself content: changing it changes the integrity hash.
    other = copy.deepcopy(value) | {"renderer_version": "purchase-pdf@1"}
    assert snapshot_hash(other) != snapshot_hash(value)


def test_the_previous_layout_version_is_refused_not_rendered():
    value = snapshot()
    value["layout"]["version"] = "purchase-a4@1"
    with pytest.raises(ValidationFailedError, match="layout"):
        render_html(value)


async def test_a_job_frozen_under_the_previous_renderer_fails_as_source_integrity(
    client, prefix, app, tmp_path, monkeypatch
):
    _, _, value, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    value["renderer_version"] = "purchase-pdf@1"
    result = await client.post(url, json=body, headers=headers())
    assert result.status_code == 202, result.text
    identity = uuid.UUID(result.json()["id"])

    def never(settings, frozen):
        raise AssertionError("an @1 snapshot must not reach the renderer")

    monkeypatch.setattr(print_worker, "render", never)
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.get(VoucherPrintJob, identity)
    assert job.status == "FAILED" and job.failure_code == "SOURCE_INTEGRITY"


# --- D3: Accounting's journal number as the bill's voucher number ---


def test_the_posted_voucher_number_prints_in_the_header_block_and_the_footer():
    value = posted()
    html = render_html(value)
    assert "Voucher no." in html and NUMBER in html and "Not allocated" not in html
    _, footer = page_templates(value)
    assert "Voucher no. " + NUMBER in footer and "Not allocated" not in footer


@pytest.mark.parametrize("status,source", [("DRAFT", "PREVIEW"), ("APPROVED", "PREVIEW")])
def test_an_unposted_bill_still_says_not_allocated(status, source):
    value = snapshot()
    value["document"]["status"] = status
    value["calculation_source"] = source
    assert "Not allocated" in render_html(value)
    assert "Not allocated" in page_templates(value)[1]


def test_a_vouchers_issued_number_wins_over_accounting_s():
    value = posted()
    value["document"]["issue_number"] = "PUR/26-27/00042"
    assert "PUR/26-27/00042" in render_html(value) and NUMBER not in render_html(value)
    assert "PUR/26-27/00042" in page_templates(value)[1]


def test_the_voucher_number_is_escaped_everywhere_it_appears():
    value = posted(INJECTION)
    html = render_html(value)
    footer = page_templates(value)[1]
    for text in (html, footer):
        lowered = text.lower()
        assert "<img" not in lowered and "<script" not in lowered
        assert "&lt;script&gt;" in text
    assert re.findall(r"<\s*([a-zA-Z0-9]+)", footer) and set(
        re.findall(r"<\s*([a-zA-Z0-9]+)", footer)
    ) <= {"div", "span"}


def test_a_number_is_refused_unless_the_source_is_posted():
    value = snapshot()
    value["labels"]["voucher_number"] = NUMBER
    with pytest.raises(ValidationFailedError, match="number"):
        validate_snapshot(value)


def test_the_voucher_number_is_covered_by_the_integrity_hash():
    first = posted(NUMBER)
    second = copy.deepcopy(first)
    second["labels"]["voucher_number"] = NUMBER[:-1] + "3"
    assert snapshot_hash(first) != snapshot_hash(second)


def test_a_custom_layout_binding_prints_the_effective_number():
    value = posted()
    value["layout"] = {
        "source": "CUSTOM",
        "name": "Number only",
        "version": "1",
        "paper_size": "A4",
        "layout_definition": {
            "schema_version": "1.1.0",
            "sections": [
                {
                    "x": 0,
                    "y": 0,
                    "width": 180,
                    "height": 30,
                    "elements": [
                        {
                            "type": "FIELD_BINDING",
                            "binding_path": "voucher.issue_number",
                            "x": 0,
                            "y": 0,
                            "width": 180,
                            "height": 5,
                        },
                        {"type": "ITEM_TABLE", "x": 0, "y": 5, "width": 180, "height": 10},
                        {"type": "TOTALS_BLOCK", "x": 0, "y": 15, "width": 180, "height": 10},
                    ],
                }
            ],
        },
    }
    assert ">" + NUMBER + "</div>" in render_html(value)


# --- D6 (1): the expense ledger per line ---


def test_each_line_shows_its_ledger_name_escaped():
    value = snapshot()
    value["labels"]["ledgers"] = {line_key(value): "Rent & <b>Utilities</b>"}
    html = render_html(value)
    assert '<div class="ledger">Ledger: Rent &amp; &lt;b&gt;Utilities&lt;/b&gt;</div>' in html
    assert "<b>" not in html


def test_a_restricted_ledger_name_prints_a_neutral_label():
    value = snapshot()
    value["labels"]["ledgers"] = {line_key(value): None}
    html = render_html(value)
    assert "Ledger restricted" in html and "Ledger: None" not in html


def test_a_line_without_ledger_evidence_prints_no_ledger_line():
    html = render_html(snapshot())
    assert 'class="ledger"' not in html and "Ledger restricted" not in html


def test_a_long_unbroken_ledger_name_wraps_instead_of_overflowing():
    css = (Path(__file__).parents[1] / "src/vouchers/domain/purchase_print.css").read_text("utf-8")
    rule = re.search(r"\.ledger\s*\{([^}]*)\}", css)
    assert rule and "overflow-wrap: anywhere" in rule.group(1)
    value = snapshot()
    value["labels"]["ledgers"] = {line_key(value): "L" * 200}
    assert "L" * 200 in render_html(value)


def test_ledger_evidence_is_covered_by_the_integrity_hash():
    value = snapshot()
    base = snapshot_hash(value)
    value["labels"]["ledgers"] = {line_key(value): "Rent"}
    renamed = snapshot_hash(value)
    value["labels"]["ledgers"] = {line_key(value): "Utilities"}
    assert len({base, renamed, snapshot_hash(value)}) == 3


# --- D6 (2): the supplier's invoice and the payment terms ---


def test_the_supplier_invoice_date_and_credit_period_are_printed():
    value = snapshot()  # invoice date 31/10/2026, due 30/11/2026
    html = render_html(value)
    assert "Supplier invoice no." in html and "BILL-123" in html
    assert "Supplier invoice date" in html and "31/10/2026" in html
    assert "Credit period" in html and "30 days" in html and "30/11/2026" in html


@pytest.mark.parametrize(
    "due,shown",
    [("2026-11-01", "1 day"), ("2026-10-31", "0 days"), ("2027-10-31", "365 days")],
)
def test_the_credit_period_is_exact_and_singular_when_one(due, shown):
    value = snapshot()
    value["document"]["invoice"]["due_date"] = due
    assert shown in render_html(value)


def test_a_due_date_before_the_invoice_date_prints_no_credit_period():
    value = snapshot()
    value["document"]["invoice"]["due_date"] = "2026-10-01"
    html = render_html(value)
    assert "Credit period" not in html and "01/10/2026" in html


# --- D6 (3): settled at posting versus still payable ---


def test_a_bill_without_settlements_shows_no_settlement_rows():
    html = render_html(snapshot())
    assert "Balance payable" not in html and "Paid at posting" not in html


def test_tenders_and_advances_show_exactly_what_remains_payable():
    value = with_settlement(
        posted(),
        [tender("20000.5000", "NEFT", "UTR&1<2>", "2026-10-31")],
        [{"allocation_key": str(uuid7()), "amount": "3000.2500", "currency": "INR"}],
    )
    value["labels"]["ledgers"] = {value["document"]["invoice"]["tenders"][0]["tender_key"]: "HDFC"}
    html = render_html(value)
    # 123456.7890 - 20000.5000 - 3000.2500 = 100456.0390, shown at the company's 2 decimals.
    assert "1,23,456.79" in html and "20,000.50" in html and "3,000.25" in html
    assert "1,00,456.04" in html
    assert "Paid at posting" in html and "NEFT" in html and "HDFC" in html
    assert "UTR&amp;1&lt;2&gt;" in html and "UTR&1<2>" not in html
    assert "Advances and credits applied" in html and "Balance payable" in html


def test_settlement_arithmetic_is_exact_decimal_never_float():
    value = with_settlement(snapshot(), [tender("0.1000"), tender("0.2000")])
    value["calculation"]["payable"] = "0.3000"
    value["calculation"]["commercial_total"] = "0.3000"
    value["calculation"]["lines"][0] |= {
        "entered": "0.3000",
        "commercial": "0.3000",
        "taxable": "0.3000",
        "payable": "0.3000",
    }
    html = render_html(value)
    assert re.search(r"Balance payable[^<]*</dt><dd>0\.00</dd>", html)
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")  # the property relied on


def test_a_draft_calls_settlements_planned_not_paid():
    value = with_settlement(
        snapshot(),
        [tender("10.0000")],
        [{"allocation_key": str(uuid7()), "amount": "5.0000", "currency": "INR"}],
    )
    html = render_html(value)
    assert "To be paid at posting" in html and "Advances and credits to apply" in html
    assert "Paid at posting" not in html.replace("To be paid at posting", "")


def test_settlements_over_the_payable_or_in_another_currency_are_refused():
    over = with_settlement(snapshot(), [tender("123456.7891")])
    with pytest.raises(ValidationFailedError, match="settlement"):
        validate_snapshot(over)
    split = with_settlement(
        snapshot(),
        [tender("123456.7890")],
        [{"allocation_key": str(uuid7()), "amount": "0.0001", "currency": "INR"}],
    )
    with pytest.raises(ValidationFailedError, match="settlement"):
        validate_snapshot(split)
    foreign = with_settlement(snapshot(), [tender("1.0000") | {"currency": "USD"}])
    with pytest.raises(ValidationFailedError, match="currency"):
        validate_snapshot(foreign)


def test_long_settlement_text_stays_in_the_totals_block():
    value = with_settlement(snapshot(), [tender("1.0000", "NEFT", "R" * 120)])
    value["labels"]["ledgers"] = {
        value["document"]["invoice"]["tenders"][0]["tender_key"]: "B" * 150
    }
    css = (Path(__file__).parents[1] / "src/vouchers/domain/purchase_print.css").read_text("utf-8")
    assert re.search(r"dt\s*\{[^}]*overflow-wrap: anywhere", css)
    # The label beside an amount wraps; the amount itself never wraps or shrinks.
    amount_rule = re.search(r"\.totals dd[^{]*\{([^}]*)\}", css)
    assert amount_rule and "white-space: nowrap" in amount_rule.group(1)
    assert "flex: none" in amount_rule.group(1)
    html = render_html(value)
    assert "R" * 120 in html and "B" * 150 in html
    assert html.count('<section class="totals"') == 1


def test_the_footer_does_not_change_with_settlement_content():
    plain = page_templates(posted())[1]
    settled = page_templates(with_settlement(posted(), [tender("1.0000")], []))[1]
    assert plain == settled


# --- D6 (4): non-base currency ---


def test_a_bill_outside_the_companys_base_currency_is_refused_with_its_reason():
    value = snapshot()
    value["document"]["currency"] = value["calculation"]["currency"] = "USD"
    with pytest.raises(ValidationFailedError, match="base currency"):
        validate_snapshot(value)


# --- display formats are frozen at job creation ---


def test_display_formats_are_part_of_the_frozen_and_hashed_snapshot():
    value = snapshot()
    assert {"date_format", "amount_precision", "rounding_mode", "digit_grouping"} <= set(
        value["display"]
    )
    original = snapshot_hash(value)
    western = copy.deepcopy(value)
    western["display"]["digit_grouping"] = "western"
    western["display"]["date_format"] = "yyyy-MM-dd"
    assert snapshot_hash(western) != original
    assert "123,456.79" in render_html(western) and "2026-10-31" in render_html(western)
    assert "1,23,456.79" in render_html(value) and "31/10/2026" in render_html(value)


# --- the snapshot builder ---


def saved_invoice(value, **extra) -> InvoiceInput:
    from voucher_execution.money import Tender  # noqa: F401  (contract import check)

    supply = value["document"]["invoice"]["supplies"][0]
    return InvoiceInput.model_validate(
        {
            "party_line_key": str(uuid7()),
            "party_account_id": str(uuid7()),
            "party_account_version": 1,
            "bill_reference": "BILL-123",
            "due_date": "2026-11-30",
            "tax": {"profile": "UNTAXED_ACCOUNT"},
            "supplies": [
                {
                    "line_key": supply["line_key"],
                    "account_id": str(uuid7()),
                    "account_version": 1,
                    "supply_kind": "SERVICE",
                    "description": "Consulting & support",
                    "amount": "123456.7890",
                }
            ],
        }
        | extra
    )


def facts_for(value, **changes) -> PurchasePrintFacts:
    from voucher_execution.invoice import InvoiceCalculationDetail

    return PurchasePrintFacts(
        calculation=InvoiceCalculationDetail.model_validate(value["calculation"]),
        supplier_name="Example Supplier",
        source="PREVIEW",
        **changes,
    )


def build(value, invoice, facts):
    return assemble_snapshot(
        document={key: item for key, item in value["document"].items() if key != "invoice"},
        invoice=invoice,
        facts=facts,
        display=value["display"],
        layout=value["layout"],
    )


def test_the_builder_freezes_number_ledgers_tenders_advances_and_formats():
    base = posted()
    cash, bank = uuid7(), uuid7()
    key = uuid.UUID(line_key(base))
    invoice = saved_invoice(
        base,
        tenders=[
            {
                "account_id": str(uuid7()),
                "account_version": 1,
                "tender": {
                    "tender_key": str(cash),
                    "line_key": str(uuid7()),
                    "mode": "CASH",
                    "amount": "300",
                    "currency": "INR",
                },
            }
        ],
    )
    facts = facts_for(
        base,
        voucher_number=NUMBER,
        ledgers=(PrintLedger(key=key, name="Rent"), PrintLedger(key=cash, name="Cash in hand")),
    ).model_copy(update={"source": "POSTED"})
    frozen = build(base, invoice, facts)
    assert frozen["renderer_version"] == RENDERER_VERSION
    assert frozen["labels"]["voucher_number"] == NUMBER
    assert frozen["labels"]["ledgers"] == {str(key): "Rent", str(cash): "Cash in hand"}
    assert frozen["document"]["invoice"]["tenders"] == [
        {
            "tender_key": str(cash),
            "mode": "CASH",
            "amount": "300.0000",
            "currency": "INR",
            "reference": None,
            "instrument_date": None,
        }
    ]
    assert frozen["document"]["invoice"]["allocations"] == []
    assert frozen["display"] == base["display"] and frozen["calculation_source"] == "POSTED"
    assert bank not in frozen["labels"]["ledgers"]
    validate_snapshot(frozen)
    assert snapshot_hash(frozen) == snapshot_hash(copy.deepcopy(frozen))


def test_the_builder_refuses_a_number_on_a_preview_and_a_foreign_currency():
    base = snapshot()
    invoice = saved_invoice(base)
    with pytest.raises(ConflictError, match="number"):
        build(base, invoice, facts_for(base, voucher_number=NUMBER))
    foreign = copy.deepcopy(base)
    foreign["document"]["currency"] = "USD"
    with pytest.raises(ValidationFailedError, match="base currency"):
        validate_snapshot(build(foreign, invoice, facts_for(base)))


# --- D6b: a download is an access event ---


def test_the_download_access_event_is_in_the_audit_contract():
    assert "vouchers.print_job.download" in AUDIT_EVENTS


async def test_each_pdf_download_commits_an_access_audit_event_first(
    client, prefix, app, tmp_path, monkeypatch
):
    saved, _, value, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    identity = (await client.post(url, json=body, headers=headers())).json()["id"]
    data = b"%PDF-1.7\nAudited renderer\n%%EOF"
    monkeypatch.setattr(print_worker, "render", lambda settings, frozen: data)
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(identity)
    )
    status_url = prefix + "/voucher-print-jobs/" + identity
    status = (await client.get(status_url, headers=headers())).json()
    token = status["download_token"]
    assert await download_events(app) == []  # issuing a ticket or polling status discloses nothing

    refused = await client.get(
        status_url + "/download", params={"token": "tampered"}, headers=headers()
    )
    assert refused.status_code == 422 and await download_events(app) == []

    for expected in (1, 2):
        pdf = await client.get(status_url + "/download", params={"token": token}, headers=headers())
        assert pdf.status_code == 200 and pdf.content == data
        events = await download_events(app)
        assert len(events) == expected
    event = events[-1]
    assert event.payload["category"] == "access"
    assert event.payload["entity_type"] == "vouchers.print_job"
    assert event.payload["entity_id"] == identity
    assert event.payload["actor_user_id"] == str(USER)
    assert event.payload["company_id"] == str(COMPANY)
    # References only: the document hash and size, never content, names or amounts.
    assert event.payload["changes"] == {
        "content_hash": status["content_hash"],
        "size_bytes": len(data),
    }
    assert "Example Supplier" not in str(event.payload) and "123456" not in str(event.payload)

    # A download that fails its integrity check discloses nothing and is not recorded.
    from vouchers.domain.supporting_files import location, object_key

    location(
        tmp_path, object_key(TENANT, COMPANY, uuid.UUID(saved["id"]), status["content_hash"])
    ).write_bytes(b"corrupt")
    corrupt = await client.get(status_url + "/download", params={"token": token}, headers=headers())
    assert corrupt.status_code == 409 and len(await download_events(app)) == 2


async def test_the_download_event_reaches_audit_with_its_retention_class(
    client, prefix, app, tmp_path, monkeypatch
):
    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    identity = (await client.post(url, json=body, headers=headers())).json()["id"]
    monkeypatch.setattr(print_worker, "render", lambda settings, frozen: b"%PDF-1.7 audited %%EOF")
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(identity)
    )
    status_url = prefix + "/voucher-print-jobs/" + identity
    token = (await client.get(status_url, headers=headers())).json()["download_token"]
    assert (
        await client.get(status_url + "/download", params={"token": token}, headers=headers())
    ).status_code == 200
    [row] = await download_events(app)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "audit/src"))
    from audit.domain.source_contract import validate_source
    from audit.metadata import service_metadata
    from audit.models import AuditEvent
    from audit.tasks.consume import handle_event
    from billing_platform.db import create_engine, create_session_factory
    from billing_platform.messages import MessageEnvelope

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        envelope = MessageEnvelope(
            message_id=row.message_id,
            tenant_id=row.tenant_id,
            event_type=row.event_type,
            schema_version=row.schema_version,
            occurred_at=row.occurred_at,
            payload=row.payload,
        )
        validate_source(envelope, "vouchers")
        with tenant_scope(TENANT):
            async with factory() as db, db.begin():
                await handle_event(db, envelope, consumer_name="print-download-audit")
            async with factory() as db:
                [event] = list(await db.scalars(select(AuditEvent)))
        assert event.category == "access" and event.entity_type == "vouchers.print_job"
        assert event.company_id == COMPANY
    finally:
        await engine.dispose()


async def download_events(app) -> list[Outbox]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            return list(
                await db.scalars(
                    select(Outbox)
                    .where(Outbox.event_type == "vouchers.print_job.download")
                    .order_by(Outbox.occurred_at)
                )
            )


# --- real browser (not run where the sandboxed browser cannot start) ---


async def test_real_chromium_pdf_shows_the_new_content_on_every_page(tmp_path):
    from pypdf import PdfReader

    from vouchers.config import PrintRuntime
    from vouchers.tasks.print_child import render

    settings = PrintRuntime(database_url="sqlite+aiosqlite:///:memory:")
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    value = with_settlement(
        posted(),
        [tender("20000.5000", "NEFT", "UTR-20261031-0001")],
        [{"allocation_key": str(uuid7()), "amount": "3000.2500", "currency": "INR"}],
    )
    supply = value["document"]["invoice"]["supplies"][0]
    amount = value["calculation"]["lines"][0]
    value["document"]["invoice"]["supplies"], value["calculation"]["lines"] = [], []
    ledgers = {}
    for index in range(60):
        identity = str(uuid7())
        value["document"]["invoice"]["supplies"].append(
            supply | {"line_key": identity, "description": f"Service line {index + 1} " + "x" * 40}
        )
        value["calculation"]["lines"].append(amount | {"key": identity})
        ledgers[identity] = "Professional fees " + "Q" * (150 if index == 0 else 5)
    value["labels"]["ledgers"] = ledgers | {
        value["document"]["invoice"]["tenders"][0]["tender_key"]: "HDFC Current Account"
    }
    # Keep the settlements within the payable of 60 lines.
    value["calculation"]["payable"] = "7407407.3400"
    value["calculation"]["commercial_total"] = "7407407.3400"
    data = await render(
        value,
        executable if executable.is_file() else None,
        sandbox=settings.print_chromium_sandbox,
    )
    (tmp_path / "purchase-content.pdf").write_bytes(data)
    reader = PdfReader(io.BytesIO(data))
    texts = [page.extract_text() for page in reader.pages]
    joined = " ".join(texts)
    assert len(texts) >= 3
    assert "Professional fees" in joined and "Ledger:" in joined
    assert sum("Balance payable" in text for text in texts) == 1
    for page, text in enumerate(texts, 1):
        assert NUMBER in text and "Example Supplier" in text, page


# --- preparation through the real route ---


async def prepared_job(client, prefix, app, tmp_path, monkeypatch, *, currency="INR", features=()):
    """Save a Purchase, then request its print with Accounting's facts replaced by `owner`."""
    import secrets

    from billing_platform.company_context import sign_company_context, verify_company_context
    from billing_platform.display import DisplayConfiguration
    from billing_platform.service_auth import CompanyServiceScope
    from conftest import SECRET
    from pydantic import SecretStr
    from test_foundation import create_type
    from test_invoice_capture import invoice_body, seed_accounts
    from voucher_execution.invoice import InvoiceCalculationDetail
    from voucher_execution.transport import ExecutionClient

    from vouchers.schemas.owners import Owner
    from vouchers.tasks import purchase_print

    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    invoice = invoice_body()
    invoice["components"] = []
    await seed_accounts(app, invoice)
    extra = {"features": frozenset(features), "allowed_currencies": frozenset({currency})}
    saved, _ = await draft_with(client, prefix, kind, invoice, currency, extra)
    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    app.state.settings.print_file_root = tmp_path
    app.state.settings.print_broker_url = SecretStr("amqp://127.0.0.1")
    app.state.settings.print_scopes = [scope]
    app.state.settings.execution_owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="print-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(scope,),
    )
    value = snapshot()
    value["calculation"]["lines"][0]["key"] = invoice["supplies"][0]["line_key"]
    asked = []

    async def owner(self, command):
        asked.append(command)
        return PurchasePrintFacts(
            calculation=InvoiceCalculationDetail.model_validate(value["calculation"]),
            supplier_name="Native supplier",
            source="PREVIEW",
            ledgers=(
                PrintLedger(
                    key=uuid.UUID(invoice["supplies"][0]["line_key"]), name="Professional fees"
                ),
            ),
        )

    async def layout(*args):
        return value["layout"]

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    monkeypatch.setattr(purchase_print, "resolve", layout)

    def auth():
        result = headers(**extra)
        company = verify_company_context(
            result["X-Company-Context"], result["X-Company-Signature"], SECRET.encode()
        )
        result["X-Company-Context"], result["X-Company-Signature"] = sign_company_context(
            company.model_copy(
                update={"report_display": DisplayConfiguration.model_validate(value["display"])}
            ),
            SECRET.encode(),
        )
        return result

    body = {"expected_version": saved["row_version"], "revision_id": saved["revision_id"]}
    url = prefix + "/vouchers/" + saved["id"] + "/print-jobs"
    return await client.post(url, headers=auth(), json=body), asked, invoice


async def draft_with(client, prefix, kind, invoice, currency, extra):
    import datetime as dt

    body = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": currency,
        "invoice": invoice,
        "posting_date": dt.date.today().isoformat(),
    }
    created = await client.post(prefix + "/vouchers", json=body, headers=headers(**extra))
    assert created.status_code == 201, created.text
    return created.json(), body


async def test_the_route_freezes_the_owners_ledger_names_into_the_job(
    client, prefix, app, tmp_path, monkeypatch
):
    result, asked, invoice = await prepared_job(client, prefix, app, tmp_path, monkeypatch)
    assert result.status_code == 202, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            [job] = list(await db.scalars(select(VoucherPrintJob)))
    frozen = job.snapshot
    assert frozen["renderer_version"] == RENDERER_VERSION
    assert frozen["labels"]["ledgers"] == {invoice["supplies"][0]["line_key"]: "Professional fees"}
    assert frozen["labels"]["voucher_number"] is None
    assert frozen["document"]["invoice"]["tenders"] == []
    assert frozen["display"]["date_format"] == "dd/MM/yyyy"
    assert job.request_hash == snapshot_hash(frozen)
    assert len(asked) == 1


async def test_a_foreign_currency_bill_is_refused_before_the_owner_is_asked(
    client, prefix, app, tmp_path, monkeypatch
):
    result, asked, _ = await prepared_job(
        client,
        prefix,
        app,
        tmp_path,
        monkeypatch,
        currency="USD",
        features=("multi_currency",),
    )
    assert result.status_code == 409, result.text
    assert "base currency" in result.text and "USD" in result.text
    assert asked == []  # nothing was asked of Accounting, and no job exists
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert list(await db.scalars(select(VoucherPrintJob))) == []
