"""Purchase output is exact, escaped, scoped, immutable and safe to retry."""

import copy
import hashlib
import uuid
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr
from sqlalchemy import func, select
from test_foundation import create_type, draft

from vouchers.domain.purchase_print import (
    LAYOUT_VERSION,
    RENDERER_VERSION,
    render_html,
    snapshot_hash,
)
from vouchers.models.printing import VoucherPrintJob
from vouchers.tasks import print_worker, purchase_print


def snapshot():
    line = str(uuid7())
    return {
        "renderer_version": RENDERER_VERSION,
        "document": {
            "id": str(uuid7()),
            "kind": "PURCHASE",
            "currency": "INR",
            "status": "DRAFT",
            "row_version": 1,
            "revision_number": 1,
            "document_date": "2026-10-31",
            "posting_date": "2026-10-31",
            "narration": '<script>alert("x")</script>',
            "invoice": {
                "bill_reference": "BILL-123",
                "due_date": "2026-11-30",
                "supplies": [{"line_key": line, "description": "Consulting & support"}],
                "components": [],
            },
        },
        "calculation": {
            "currency": "INR",
            "calculation_hash": "a" * 64,
            "commercial_total": "123456.7890",
            "tax_total": "0.0000",
            "charged_tax_total": "0.0000",
            "rounding": "0.0000",
            "payable": "123456.7890",
            "lines": [
                {
                    "key": line,
                    "entered": "123456.7890",
                    "commercial": "123456.7890",
                    "taxable": "123456.7890",
                    "taxes": [],
                    "price_rounding": "0.0000",
                    "payable": "123456.7890",
                }
            ],
            "components": [],
            "allocations": [],
            "tax_evidence": [],
        },
        "display": {
            "company_label": "QA & Company",
            "base_currency": "INR",
            "amount_precision": 2,
            "quantity_precision": 3,
            "rounding_mode": "half_up",
            "date_format": "dd/MM/yyyy",
            "datetime_format": "dd/MM/yyyy HH:mm",
            "digit_grouping": "indian",
            "decimal_separator": ".",
            "thousands_separator": ",",
            "negative_format": "minus",
            "currency_display": "code",
            "currency_symbol_position": "prefix",
            "timezone": "Asia/Kolkata",
            "locale": "en-IN",
        },
        "layout": {
            "source": "BUILTIN",
            "name": "Standard Purchase · A4",
            "version": LAYOUT_VERSION,
            "paper_size": "A4",
            "page_orientation": "PORTRAIT",
            "layout_digest": hashlib.sha256(LAYOUT_VERSION.encode()).hexdigest(),
        },
        "labels": {"supplier": "Example Supplier"},
        "calculation_source": "PREVIEW",
    }


def test_exact_formats_escaped_text_and_draft_identity():
    value = snapshot()
    original = copy.deepcopy(value)
    html = render_html(value)
    assert "1,23,456.79" in html and "31/10/2026" in html
    assert "Consulting &amp; support" in html and "QA &amp; Company" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Draft — not posted" in html and "Not allocated" in html
    assert "Not a supplier tax invoice" in html
    assert value == original
    assert snapshot_hash(value) == snapshot_hash(copy.deepcopy(value))


@pytest.mark.parametrize(
    "status,word",
    [
        ("CANCELLED", "Cancelled"),
        ("REVERSED", "Reversed"),
        ("POSTED", "Posted purchase"),
        ("APPROVED", "Approval"),
    ],
)
def test_lifecycle_is_not_misrepresented(status, word):
    value = snapshot()
    value["document"]["status"] = status
    assert word in render_html(value)


def test_mismatched_calculation_is_refused():
    value = snapshot()
    value["calculation"]["lines"][0]["key"] = str(uuid7())
    with pytest.raises(ValidationFailedError, match="lines"):
        render_html(value)


def test_custom_paper_is_honoured_and_an_unsupported_option_is_never_silently_discarded():
    value = snapshot()
    value["layout"] = {
        "source": "CUSTOM",
        "name": "Compact custom",
        "version": "1",
        "paper_size": "A5",
        "layout_definition": {
            "schema_version": "1.1.0",
            "sections": [
                {
                    "x": 0,
                    "y": 0,
                    "width": 180,
                    "height": 20,
                    "elements": [
                        {"type": "ITEM_TABLE", "x": 0, "y": 0, "width": 180, "height": 10},
                        {"type": "TOTALS_BLOCK", "x": 0, "y": 10, "width": 180, "height": 10},
                    ],
                }
            ],
        },
    }
    # A5 is printable now (2026-11-03): the page is A5, not an A4 page with A5 content.
    assert "size: 148mm 210mm" in render_html(value)
    # Rolls print since 2026-11-04 (designer plan R3); a size outside the manifest never does.
    value["layout"]["paper_size"] = "A3"
    with pytest.raises(ValidationFailedError, match="custom layout cannot be printed"):
        render_html(value)
    value["layout"]["paper_size"] = "A5"
    value["layout"]["layout_definition"]["sections"][0]["elements"].append(
        {"type": "IMAGE", "x": 0, "y": 12, "width": 20, "height": 8}
    )
    with pytest.raises(ValidationFailedError, match="no picture chosen"):
        render_html(value)


async def queued(client, prefix, app, tmp_path, monkeypatch):
    kind = await create_type(client, prefix, kind="PURCHASE", name="Purchase")
    saved, content = await draft(client, prefix, kind["revision_id"])
    value = snapshot()
    value["document"].update(
        {key: saved[key] for key in ("id", "row_version", "revision_number", "status")}
    )

    async def prepare(request, current, identity, body):
        from vouchers.tasks.access import authorize

        for action in ("read", "artifact.create", "artifact.read"):
            authorize(current, action)
        return copy.deepcopy(value)

    monkeypatch.setattr(purchase_print, "prepare", prepare)

    async def reauthorize(*args):
        pass  # Signed owner HTTP and its native permissions are verified independently.

    monkeypatch.setattr(purchase_print, "reauthorize", reauthorize)
    app.state.settings.print_file_root = tmp_path
    app.state.settings.print_broker_url = SecretStr("amqp://127.0.0.1")
    app.state.settings.print_scopes = [CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)]
    body = {"expected_version": saved["row_version"], "revision_id": saved["revision_id"]}
    url = prefix + "/vouchers/" + saved["id"] + "/print-jobs"
    return saved, content, value, url, body


async def test_create_replay_worker_duplicate_status_and_protected_download(
    client, prefix, app, tmp_path, monkeypatch
):
    saved, _, value, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    auth = headers()
    result = await client.post(url, json=body, headers=auth)
    assert result.status_code == 202, result.text
    identity = result.json()["id"]
    replay = await client.post(url, json=body, headers=auth)
    assert replay.json()["id"] == identity and replay.headers["Idempotency-Replayed"] == "true"
    status_url = prefix + "/voucher-print-jobs/" + identity
    assert (await client.get(status_url, headers=headers())).json()["status"] == "PENDING"
    data = b"%PDF-1.7\nVerified test renderer\n%%EOF"
    calls = []

    def render(settings, frozen):
        calls.append(frozen)
        return data

    monkeypatch.setattr(print_worker, "render", render)
    for _ in range(2):
        await print_worker.execute(
            app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(identity)
        )
    assert len(calls) == 1 and calls[0] == value
    status = (await client.get(status_url, headers=headers())).json()
    assert (
        status["status"] == "READY" and status["content_hash"] == hashlib.sha256(data).hexdigest()
    )
    download = status_url + "/download"
    pdf = await client.get(download, params={"token": status["download_token"]}, headers=headers())
    assert pdf.status_code == 200 and pdf.content == data
    assert pdf.headers["content-type"] == "application/pdf"
    assert "no-store" in pdf.headers["cache-control"]
    assert (
        await client.get(download, params={"token": "tampered"}, headers=headers())
    ).status_code == 422
    other = uuid7()
    cross = await client.get(
        f"/v1/companies/{other}/voucher-print-jobs/{identity}", headers=headers(company=other)
    )
    assert cross.status_code == 403
    assert (await client.get(status_url, headers=headers(tenant=other))).status_code == 404
    assert (await client.get(status_url, headers=headers(user=other))).status_code == 403
    assert (
        await client.get(status_url, headers=headers(permissions=frozenset()))
    ).status_code == 403
    assert (await client.get(status_url)).status_code == 401
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherPrintJob.id))) == 1
    with tenant_scope(other):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherPrintJob.id))) == 0
    # Integrity is checked before delivery, including a previously issued valid ticket.
    from vouchers.domain.supporting_files import location, object_key

    location(
        tmp_path, object_key(TENANT, COMPANY, uuid.UUID(saved["id"]), status["content_hash"])
    ).write_bytes(b"corrupt")
    assert (
        await client.get(download, params={"token": status["download_token"]}, headers=headers())
    ).status_code == 409


async def test_failed_worker_is_terminal_and_stale_input_never_prints(
    client, prefix, app, tmp_path, monkeypatch
):
    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    stale = await client.post(url, json=body | {"expected_version": 999}, headers=headers())
    assert stale.status_code == 409
    result = await client.post(url, json=body, headers=headers())
    identity = uuid.UUID(result.json()["id"])

    def unavailable(settings, frozen):
        raise TimeoutError("sensitive renderer details must not be exposed")

    monkeypatch.setattr(print_worker, "render", unavailable)
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
    )
    status = (
        await client.get(prefix + "/voucher-print-jobs/" + str(identity), headers=headers())
    ).json()
    assert status["status"] == "FAILED" and status["failure_code"] == "RENDER_TIMEOUT"
    assert "sensitive" not in str(status) and status["download_token"] is None


async def test_owner_permission_revocation_invalidates_print_scope(
    client, prefix, app, tmp_path, monkeypatch
):
    from conftest import PERMISSIONS

    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    result = await client.post(
        url,
        json=body,
        headers=headers(
            permissions=PERMISSIONS | {"accounting.account.read"},
        ),
    )
    status = prefix + "/voucher-print-jobs/" + result.json()["id"]
    assert (await client.get(status, headers=headers())).status_code == 403


async def test_print_source_is_immutable_and_worker_needs_no_actor_keys(
    client, prefix, app, tmp_path, monkeypatch
):
    from billing_platform.errors import ConflictError

    from vouchers.config import PrintRuntime

    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    identity = uuid.UUID((await client.post(url, json=body, headers=headers())).json()["id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(VoucherPrintJob, identity)
            row.snapshot = row.snapshot | {"changed": True}
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
    worker = PrintRuntime(database_url="sqlite+aiosqlite:///:memory:")
    assert "actor_signing_secret" not in type(worker).model_fields
    assert "artifact_signing_secret" not in type(worker).model_fields


async def test_actual_worker_produces_and_delivers_private_pdf(
    client, prefix, app, tmp_path, monkeypatch
):
    saved, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if executable.is_file():
        app.state.settings.print_browser_executable = executable
    result = await client.post(url, json=body, headers=headers())
    identity = uuid.UUID(result.json()["id"])
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
    )
    status_url = prefix + "/voucher-print-jobs/" + str(identity)
    status = (await client.get(status_url, headers=headers())).json()
    assert status["status"] == "READY", status
    pdf = await client.get(
        status_url + "/download", params={"token": status["download_token"]}, headers=headers()
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert status["size_bytes"] == len(pdf.content)
    assert hashlib.sha256(pdf.content).hexdigest() == status["content_hash"]
    # Repeated worker delivery preserves precisely the completed artifact.
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity
    )
    assert (await client.get(status_url, headers=headers())).json()["content_hash"] == status[
        "content_hash"
    ]
    assert str(saved["id"]) in pdf.headers["content-disposition"]


async def test_dispatch_repair_and_worker_scope_are_bounded(
    client, prefix, app, tmp_path, monkeypatch
):
    import datetime as dt

    from billing_platform.db.platform_models import Outbox
    from billing_platform.db.types import utcnow

    from vouchers.tasks.print_dispatcher import application, repair

    _, _, _, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    identity = uuid.UUID((await client.post(url, json=body, headers=headers())).json()["id"])
    assert await repair(app.state.session_factory, app.state.settings) == 0
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(VoucherPrintJob, identity)
            row.status, row.attempt = "RUNNING", 1
            row.lease_until = utcnow() - dt.timedelta(seconds=1)
            dispatch = await db.scalar(
                select(Outbox).where(Outbox.event_type == print_worker.DISPATCH_EVENT)
            )
            dispatch.published_at = utcnow() - dt.timedelta(seconds=60)
            dispatch.occurred_at = utcnow() - dt.timedelta(seconds=60)
    assert await repair(app.state.session_factory, app.state.settings) == 1
    assert await repair(app.state.session_factory, app.state.settings) == 0
    with pytest.raises(PermissionError):
        await print_worker.execute(
            app.state.session_factory, app.state.settings, uuid7(), COMPANY, identity
        )
    broker = application(app.state.settings, executor=lambda *args: None)
    try:
        assert broker.conf.accept_content == ["json"]
        assert broker.conf.task_acks_late and not broker.conf.worker_enable_remote_control
        assert broker.conf.worker_prefetch_multiplier == 1
    finally:
        broker.close()


@pytest.mark.parametrize("line_kind", ["ACCOUNT", "GOODS"])
async def test_real_chromium_pdf_pagination(tmp_path, line_kind):
    import io

    from pypdf import PdfReader

    from vouchers.config import PrintRuntime
    from vouchers.tasks.print_child import render

    # The sandbox is on unless this developer machine explicitly (and only in development)
    # turned it off with VOUCHERS_ENVIRONMENT / VOUCHERS_PRINT_CHROMIUM_SANDBOX.
    settings = PrintRuntime(database_url="sqlite+aiosqlite:///:memory:")
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not executable.is_file():
        executable = None
    value = snapshot()
    if line_kind == "GOODS":
        from test_purchase_goods_print import with_goods

        value = with_goods(value)
        value["labels"]["units"] = {}
    value["document"]["issue_number"] = "PUR/26-27/00042"
    source = 1 if line_kind == "GOODS" else 0
    supply = value["document"]["invoice"]["supplies"][source]
    amount = value["calculation"]["lines"][source]
    value["document"]["invoice"]["supplies"] = []
    value["calculation"]["lines"] = []
    for index in range(100):
        identity = str(uuid7())
        value["document"]["invoice"]["supplies"].append(
            supply
            | {
                "line_key": identity,
                "description": f"{line_kind} line {index + 1} / " + "Long detail " * 5,
            }
        )
        value["calculation"]["lines"].append(amount | {"key": identity})
        if line_kind == "GOODS":
            value["labels"]["units"][identity] = "kg"
    data = await render(value, executable, sandbox=settings.print_chromium_sandbox)
    (tmp_path / f"purchase-{line_kind.lower()}-100-lines.pdf").write_bytes(data)
    reader = PdfReader(io.BytesIO(data))
    texts = [page.extract_text() for page in reader.pages]
    assert len(texts) >= 3
    assert sum("bill summary" in text.lower() for text in texts) == 1
    assert all("Purchase voucher" in text and "Page" in text for text in texts)
    # A loose continuation page (and the last page, with only totals) still names its bill.
    for page, text in enumerate(texts, 1):
        for fact in ("PUR/26-27/00042", "Example Supplier", "BILL-123", "31/10/2026"):
            assert fact in text, f"page {page} is missing {fact!r}"
        assert f"Page {page} of {len(texts)}" in text
    for index in range(1, 101):
        marker = f"{line_kind} line {index} /"
        assert sum(text.count(marker) for text in texts) == 1, marker
    assert all("Particulars" in text for text in texts if f"{line_kind} line" in text)


async def test_preparation_reads_the_saved_invoice_and_live_owner_facts(
    client, prefix, app, tmp_path, monkeypatch
):
    import datetime as dt
    import secrets

    from billing_platform.company_context import sign_company_context, verify_company_context
    from billing_platform.display import DisplayConfiguration
    from conftest import SECRET
    from test_invoice_capture import invoice_body, seed_accounts
    from voucher_execution.invoice import InvoiceCalculationDetail
    from voucher_execution.printing import PurchasePrintFacts
    from voucher_execution.transport import ExecutionClient

    from vouchers.schemas.owners import Owner

    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    invoice = invoice_body()
    invoice["components"] = []
    await seed_accounts(app, invoice)
    saved, _ = await draft(
        client,
        prefix,
        kind["revision_id"],
        invoice=invoice,
        posting_date=dt.date.today().isoformat(),
    )
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
    observed = []

    async def owner(self, command):
        observed.append(command)
        return PurchasePrintFacts(
            calculation=InvoiceCalculationDetail.model_validate(value["calculation"]),
            supplier_name="Native supplier",
            source="PREVIEW",
        )

    async def layout(*args):
        return value["layout"]

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    monkeypatch.setattr(purchase_print, "resolve", layout)

    def auth(**kwargs):
        result = headers(**kwargs)
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
    result = await client.post(url, headers=auth(), json=body)
    assert result.status_code == 202, result.text
    assert observed[0].preview.invoice.bill_reference == invoice["bill_reference"]
    assert not observed[0].require_posted
    # Native field denies stop the request before contacting either owner.
    denied = await client.post(
        url,
        headers=auth(
            policies=[
                {
                    "entity_type": "vouchers.voucher",
                    "field_key": "invoice",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
        json=body,
    )
    assert denied.status_code == 403 and len(observed) == 1
    assert (
        await client.post(url, headers=auth(), json=body | {"revision_id": str(uuid7())})
    ).status_code == 409
    assert (
        await client.post(url, headers=auth(), json=body | {"html": "unsafe"})
    ).status_code == 422
