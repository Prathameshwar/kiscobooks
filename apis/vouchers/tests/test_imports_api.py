"""Purchase import: template, stage, native dry-run validation, commit and result report."""

import base64
import csv
import datetime as dt
import io
import secrets
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, PERMISSIONS, TENANT, USER, headers
from pydantic import SecretStr
from sqlalchemy import func, select
from test_foundation import create_type
from voucher_execution.invoice import InvoiceCalculationDetail

from vouchers.domain.imports import MARKER, Master, Resolution
from vouchers.models import core as m
from vouchers.models import imports as im
from vouchers.schemas.owners import Owner
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks import imports as tasks
from vouchers.tasks.sources import apply_bundle

TODAY = dt.date.today().isoformat()
IMPORT = frozenset({"vouchers.import.read", "vouchers.import.manage", "vouchers.import.commit"})


class Masters:
    """Accounting masters known to the fake owner lookup and to local evidence."""

    def __init__(self) -> None:
        self.parties = {"SUP-1": uuid7(), "SUP-2": uuid7()}
        self.ledgers = {code: uuid7() for code in self.parties}
        self.accounts = {"EXP-RENT": uuid7(), "EXP-FEES": uuid7()}
        self.versions: dict[uuid.UUID, int] = {}
        self.lookups = 0

    def resolution(self) -> Resolution:
        def master(source: uuid.UUID) -> Master:
            return Master(source, self.versions.get(source, 1), "ACTIVE")

        return Resolution(
            parties={code: master(pid) for code, pid in self.parties.items()},
            gstin_parties={"27ABCDE1234F1Z5": (self.parties["SUP-2"],)},
            party_ids={pid: master(pid) for pid in self.parties.values()},
            party_ledgers={
                pid: ((code + "-LEDGER", master(self.ledgers[code])),)
                for code, pid in self.parties.items()
            },
            accounts={code: master(aid) for code, aid in self.accounts.items()},
        )

    async def evidence(self, app, *, version: int = 1, only: uuid.UUID | None = None) -> None:
        rows = [("party", pid) for pid in self.parties.values()] + [
            ("account", aid) for aid in [*self.ledgers.values(), *self.accounts.values()]
        ]
        # Accounting links each party ledger to its party; the document check relies on it.
        owners = {self.ledgers[code]: pid for code, pid in self.parties.items()}
        bundle = SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "entity_type": entity,
                        "source_id": str(source),
                        "source_version": version,
                        "status": "ACTIVE",
                        "facts": (
                            {"kind": "GENERAL"}
                            | ({"party_id": str(owners[source])} if source in owners else {})
                            if entity == "account"
                            else {}
                        ),
                    }
                    for entity, source in rows
                    if only is None or source == only
                ],
            }
        )
        await apply_bundle(app.state.session_factory, bundle, "accounting")


@pytest.fixture
def masters(app, monkeypatch) -> Masters:
    known = Masters()
    owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="import-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    app.state.settings.master_lookup_owner = owner
    app.state.settings.execution_owner = owner

    async def resolve(owner, tenant, company, **codes):
        known.lookups += 1
        assert tenant == TENANT and company == COMPANY
        return known.resolution()

    async def preview(owner, command):
        payable = sum(
            (Decimal(row.amount) for row in command.invoice.supplies), start=Decimal(0)
        )
        return InvoiceCalculationDetail.model_validate(
            {
                "calculation_hash": "c" * 64,
                "currency": command.currency,
                "commercial_total": str(payable),
                "tax_total": "0",
                "charged_tax_total": "0",
                "rounding": "0",
                "payable": str(payable),
                "lines": [],
                "components": [],
                "allocations": [],
                "tax_evidence": [],
            }
        )

    monkeypatch.setattr(tasks, "default_lookup", resolve)
    monkeypatch.setattr(tasks, "preview_owner", preview)
    return known


def auth(**changes):
    return headers(permissions=changes.pop("permissions", None) or PERMISSIONS | IMPORT, **changes)


async def purchase_type(client, prefix, code="PURCH"):
    return await create_type(
        client, prefix, code=code, name="Purchase", kind="PURCHASE",
        policy={"invoice": {"supplier_difference_limit": "1", "manual_discounts_allowed": True}},
    )


async def template_header(client, prefix, type_id):
    result = await client.get(
        prefix + "/voucher-import-templates",
        params={"voucher_type_id": type_id, "format": "CSV"},
        headers=auth(),
    )
    assert result.status_code == 200, result.text
    rows = list(csv.reader(io.StringIO(result.text)))
    assert rows[0] == [MARKER, "1"]
    return rows[1]


def csv_file(header, vouchers):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([MARKER, "1"])
    writer.writerow(header)
    for voucher in vouchers:
        for line in voucher["lines"]:
            cells = {k: v for k, v in voucher.items() if k != "lines"} | line
            writer.writerow([cells.get(name, "") for name in header])
    return base64.b64encode(output.getvalue().encode()).decode()


def bill(key, supplier="SUP-1", number=None, total="1500.00", **extra):
    return {
        "import_key": key,
        "document_date": TODAY,
        "supplier_code": supplier,
        "supplier_invoice_number": number or "INV-" + key,
        "supplier_invoice_date": TODAY,
        "currency": "INR",
        "tax_profile": "UNTAXED_ACCOUNT",
        "supplier_declared_total": total,
        "lines": [
            {"line_no": "1", "supply_kind": "SERVICE", "account_code": "EXP-RENT",
             "description": "Rent", "amount": "1000.00"},
            {"line_no": "2", "supply_kind": "ACCOUNT", "account_code": "EXP-FEES",
             "description": "Fees", "amount": "500"},
        ],
    } | extra


async def upload(client, prefix, type_id, vouchers, header=None, key=None, rule=None,
                 **auth_changes):
    header = header or await template_header(client, prefix, type_id)
    return await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": type_id, "format": "CSV",
              "content_base64": csv_file(header, vouchers)}
        | ({"duplicate_rule": rule} if rule else {}),
        headers=auth(key=key, **auth_changes),
    )


async def validated(client, prefix, job):
    result = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]},
        headers=auth(),
    )
    assert result.status_code == 200, result.text
    body = result.json()
    for _ in range(30):
        if body["state"] != "VALIDATING":
            break
        body = (await client.post(prefix + f"/voucher-imports/{job['id']}/run",
                                  headers=auth())).json()
    return body


async def rows(client, prefix, job_id):
    result = await client.get(prefix + f"/voucher-imports/{job_id}/vouchers", headers=auth())
    assert result.status_code == 200, result.text
    return {row["import_key"]: row for row in result.json()["items"]}


async def detail(client, prefix, job_id, key):
    result = await client.get(
        prefix + f"/voucher-imports/{job_id}/vouchers/{key}", headers=auth()
    )
    assert result.status_code == 200, result.text
    return result.json()


async def voucher_count(app) -> int:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            return int(await db.scalar(select(func.count(m.Voucher.id))) or 0)


async def test_template_formats_permissions_and_field_policy(client, prefix, masters):
    kind = await purchase_type(client, prefix)
    path = prefix + "/voucher-import-templates"
    params = {"voucher_type_id": kind["id"], "format": "CSV"}
    assert (await client.get(path, params=params)).status_code == 401
    assert (await client.get(path, params=params, headers=headers())).status_code == 403
    header = await template_header(client, prefix, kind["id"])
    assert {"import_key", "supplier_code", "narration", "account_code", "amount"} <= set(header)
    deny = {
        "entity_type": "vouchers.voucher", "access": "write", "effect": "deny",
        "scope_type": "company", "scope_id": str(COMPANY),
    }
    hidden = await client.get(
        path, params=params, headers=auth(policies=[deny | {"field_key": "narration"}])
    )
    assert hidden.status_code == 200 and "narration" not in hidden.text.splitlines()[1]
    refused = await client.get(
        path, params=params, headers=auth(policies=[deny | {"field_key": "invoice"}])
    )
    assert refused.status_code == 403
    for file_format, media in (("XLSX", "spreadsheetml"), ("JSON", "json")):
        result = await client.get(
            path, params={"voucher_type_id": kind["id"], "format": file_format}, headers=auth()
        )
        assert result.status_code == 200 and media in result.headers["content-type"]
        assert "attachment" in result.headers["content-disposition"]
    other = uuid7()
    other_company = await client.get(
        f"/v1/companies/{other}/voucher-import-templates", params=params,
        headers=auth(company=other),
    )
    assert other_company.status_code in {403, 404}
    memo = await create_type(client, prefix, code="MEMO")
    wrong = await client.get(
        path, params={"voucher_type_id": memo["id"], "format": "CSV"}, headers=auth()
    )
    assert wrong.status_code == 409


async def test_json_template_round_trips_and_xlsx_formulas_are_rejected(
    client, prefix, masters
):
    from billing_platform.bulk_files import xlsx_workbook

    kind = await purchase_type(client, prefix)
    template = await client.get(
        prefix + "/voucher-import-templates",
        params={"voucher_type_id": kind["id"], "format": "JSON"}, headers=auth(),
    )
    staged = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "JSON", "document": template.json()},
        headers=auth(),
    )
    assert staged.status_code == 202, staged.text
    assert staged.json()["voucher_count"] == 1 and staged.json()["invalid_count"] == 0
    workbook = xlsx_workbook([("vouchers", ["import_key"], [["A"]])], marker=MARKER)
    formula = workbook.replace(b"<is><t>A</t></is>", b"<f>1+1</f>")
    for raw in (formula, b"not a workbook"):
        result = await client.post(
            prefix + "/voucher-imports",
            json={"voucher_type_id": kind["id"], "format": "XLSX",
                  "content_base64": base64.b64encode(raw).decode()},
            headers=auth(),
        )
        assert result.status_code == 422, result.text
    unknown = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "CSV", "content_base64": csv_file(
            ["import_key", "unexpected"], [{"import_key": "A", "lines": [{}]}]
        )},
        headers=auth(),
    )
    assert unknown.status_code == 422
    assert "unknown_column" in unknown.json()["error"]["fields"].values()


async def test_full_flow_validates_without_effects_then_commits_drafts(
    client, prefix, app, masters
):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    key = str(uuid.uuid4())
    staged = await upload(
        client, prefix, kind["id"],
        [
            bill("A"),
            bill("B", supplier="", supplier_gstin="27ABCDE1234F1Z5", total="1500.50",
                 supplier_difference_reason="Supplier rounding"),
            bill("C", total="1,500.00"),
            bill("D", supplier="SUP-404"),
            bill("E", total="1600"),
            bill("F", number="INV-A"),
        ],
        key=key,
    )
    assert staged.status_code == 202, staged.text
    job = staged.json()
    assert job["state"] == "STAGED" and job["voucher_count"] == 6
    assert job["invalid_count"] == 2  # C lexical, F duplicates A within the file
    replay = await upload(
        client, prefix, kind["id"],
        [bill("A"), bill("B", supplier="", supplier_gstin="27ABCDE1234F1Z5", total="1500.50",
                          supplier_difference_reason="Supplier rounding"),
         bill("C", total="1,500.00"), bill("D", supplier="SUP-404"), bill("E", total="1600"),
         bill("F", number="INV-A")],
        key=key,
    )
    assert replay.json()["id"] == job["id"] and replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = int(await db.scalar(select(func.count(Outbox.id))) or 0)
    ready = await validated(client, prefix, job)
    assert ready["state"] == "READY", ready
    assert (ready["valid_count"], ready["warning_count"], ready["invalid_count"]) == (1, 1, 4)
    assert await voucher_count(app) == 0
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            outbox = list(await db.scalars(select(Outbox).order_by(Outbox.occurred_at)))
            assert not [r for r in outbox if r.event_type.startswith("vouchers.voucher.")]
            assert len(outbox) == before + 2  # validate + validated job events only
            stored = await db.scalar(
                select(im.VoucherImportRow).where(im.VoucherImportRow.import_key == "A")
            )
            assert type(stored.computed_payable) is Decimal
            assert stored.computed_payable == Decimal("1500")
    results = await rows(client, prefix, job["id"])
    assert {key: row["state"] for key, row in results.items()} == {
        "A": "VALID", "B": "WARNING", "C": "INVALID", "D": "INVALID", "E": "INVALID",
        "F": "INVALID",
    }
    assert results["B"]["supplier_difference"] == "0.5000"
    codes = {
        key: {error["code"] for error in (await detail(client, prefix, job["id"], key))["errors"]}
        for key in ("C", "D", "E", "F")
    }
    assert codes == {
        "C": {"invalid_decimal"},
        "D": {"unknown_master"},
        "E": {"supplier_total_mismatch"},
        "F": {"duplicate_supplier_invoice"},
    }
    stale = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit",
        json={"expected_version": ready["row_version"], "selection_digest": "0" * 64},
        headers=auth(),
    )
    assert stale.status_code == 409
    commit_key = str(uuid.uuid4())
    body = {"expected_version": ready["row_version"], "selection_digest": ready["selection_digest"]}
    done = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit", json=body, headers=auth(key=commit_key)
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "SUCCEEDED" and done.json()["created_count"] == 2
    again = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit", json=body, headers=auth(key=commit_key)
    )
    assert again.headers["Idempotency-Replayed"] == "true"
    assert (await client.post(prefix + f"/voucher-imports/{job['id']}/run",
                              headers=auth())).status_code == 200
    assert await voucher_count(app) == 2
    created = await rows(client, prefix, job["id"])
    voucher = await client.get(
        prefix + "/vouchers/" + created["A"]["voucher_id"], headers=auth()
    )
    assert voucher.status_code == 200
    document = voucher.json()
    assert document["status"] == "DRAFT" and document["kind"] == "PURCHASE"
    assert document["invoice"]["tax"]["supplier_invoice_number"] == "INV-A"
    assert document["invoice"]["supplier_declared_total"] == "1500.0000"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            effects = list(await db.scalars(select(im.VoucherImportEffect)))
            assert {row.import_key for row in effects} == {"A", "B"}
    ticket = await client.get(
        prefix + f"/voucher-imports/{job['id']}/report-ticket", headers=auth()
    )
    assert ticket.status_code == 200
    path = ticket.json()["download_path"]
    report = await client.get(path, headers=auth())
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/csv")
    lines = list(csv.reader(io.StringIO(report.text)))
    assert lines[0] == tasks.REPORT_COLUMNS
    assert {line[0] for line in lines[1:]} == set("ABCDEF")
    assert (await client.get(path.replace("token=", "token=x"), headers=auth())).status_code == 422
    xlsx = await client.get(
        (await client.get(prefix + f"/voucher-imports/{job['id']}/report-ticket",
                          params={"format": "XLSX"}, headers=auth())).json()["download_path"],
        headers=auth(),
    )
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    stranger = await client.get(path, headers=auth(user=uuid7()))
    assert stranger.status_code == 403
    duplicate = await upload(client, prefix, kind["id"], [bill("A2", number="INV-A")])
    again_job = await validated(client, prefix, duplicate.json())
    assert again_job["invalid_count"] == 1
    assert {e["code"] for e in (await detail(client, prefix, duplicate.json()["id"], "A2"))[
        "errors"]} == {"duplicate_supplier_invoice"}


async def test_access_isolation_and_revoked_permission(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    path = prefix + f"/voucher-imports/{job['id']}"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=headers())).status_code == 403
    other_tenant = uuid7()
    foreign = await client.get(
        f"/v1/companies/{COMPANY}/voucher-imports/{job['id']}",
        headers=auth(tenant=other_tenant),
    )
    assert foreign.status_code == 404
    other_company = uuid7()
    wrong = await client.get(
        f"/v1/companies/{other_company}/voucher-imports/{job['id']}",
        headers=auth(company=other_company),
    )
    assert wrong.status_code in {403, 404}
    peer = uuid7()
    assert (await client.get(path, headers=auth(user=peer))).json()["own"] is False
    peer_detail = await client.get(path + "/vouchers/A", headers=auth(user=peer))
    assert peer_detail.status_code == 200 and "source_input" not in peer_detail.json()
    assert (
        await client.post(path + "/validate", json={"expected_version": 1}, headers=auth(user=peer))
    ).status_code == 403
    listed = await client.get(prefix + "/voucher-imports", headers=auth())
    assert [item["id"] for item in listed.json()["items"]] == [job["id"]]
    assert (await client.get(prefix + "/voucher-imports", headers=auth(user=peer))).json()[
        "items"] == []
    ready = await validated(client, prefix, job)
    no_commit = auth(permissions=PERMISSIONS | {"vouchers.import.read", "vouchers.import.manage"})
    refused = await client.post(
        path + "/commit",
        json={"expected_version": ready["row_version"],
              "selection_digest": ready["selection_digest"]},
        headers=no_commit,
    )
    assert refused.status_code == 403
    invalid = await client.post(path + "/commit", json={"expected_version": 1}, headers=auth())
    assert invalid.status_code == 422
    assert await voucher_count(app) == 0


async def test_stop_blocks_rest_and_continue_reports_partial(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    for on_error, expected in (("STOP", ("PARTIAL", "BLOCKED")),
                               ("CONTINUE_INDEPENDENT", ("PARTIAL", "CREATED"))):
        suffix = on_error[:4]
        job = (await upload(client, prefix, kind["id"], [
            bill(f"{suffix}1"), bill(f"{suffix}2", supplier="SUP-2"), bill(f"{suffix}3"),
        ])).json()
        ready = await validated(client, prefix, job)
        assert ready["valid_count"] == 3
        # Supplier 2 changes at the owner after review: its draft is refused natively.
        changed = masters.versions.get(masters.parties["SUP-2"], 1) + 1
        await masters.evidence(app, version=changed, only=masters.parties["SUP-2"])
        done = await client.post(
            prefix + f"/voucher-imports/{job['id']}/commit",
            json={"expected_version": ready["row_version"],
                  "selection_digest": ready["selection_digest"], "on_error": on_error},
            headers=auth(),
        )
        assert done.status_code == 200, done.text
        assert done.json()["state"] == expected[0]
        states = {k: r["state"] for k, r in (await rows(client, prefix, job["id"])).items()}
        assert states == {f"{suffix}1": "CREATED", f"{suffix}2": "FAILED",
                          f"{suffix}3": expected[1]}
        failed = await detail(client, prefix, job["id"], f"{suffix}2")
        assert failed["errors"][-1]["code"] == "master_unavailable"
        masters.versions[masters.parties["SUP-2"]] = changed  # owner and evidence agree again


async def test_exclusion_cancel_and_revalidation(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A"), bill("B")])).json()
    ready = await validated(client, prefix, job)
    again = await validated(client, prefix, ready)
    assert again["selection_digest"] == ready["selection_digest"]
    assert again["row_version"] > ready["row_version"]
    outside = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit",
        json={"expected_version": again["row_version"],
              "selection_digest": again["selection_digest"], "exclude_keys": ["Z"]},
        headers=auth(),
    )
    assert outside.status_code == 422
    done = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit",
        json={"expected_version": again["row_version"],
              "selection_digest": again["selection_digest"], "exclude_keys": ["B"]},
        headers=auth(),
    )
    assert done.json()["state"] == "SUCCEEDED" and done.json()["created_count"] == 1
    assert (await rows(client, prefix, job["id"]))["B"]["state"] == "NOT_SELECTED"
    finished = await client.post(
        prefix + f"/voucher-imports/{job['id']}/cancel",
        json={"expected_version": done.json()["row_version"]}, headers=auth(),
    )
    assert finished.status_code == 409
    second = (await upload(client, prefix, kind["id"], [bill("C")])).json()
    cancelled = await client.post(
        prefix + f"/voucher-imports/{second['id']}/cancel",
        json={"expected_version": second["row_version"]}, headers=auth(),
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "CANCELLED"
    assert (await rows(client, prefix, second["id"]))["C"]["state"] == "NOT_SELECTED"
    stale = await client.post(
        prefix + f"/voucher-imports/{second['id']}/validate",
        json={"expected_version": second["row_version"]}, headers=auth(),
    )
    assert stale.status_code == 409
    assert await voucher_count(app) == 1


async def test_validation_requires_configured_owners(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    app.state.settings.master_lookup_owner = None
    result = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]}, headers=auth(),
    )
    assert result.status_code == 409
    assert "lookup owner" in result.json()["error"]["message"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(select(im.VoucherImportJob))
            assert row.state == "STAGED"
            assert row.actor_user_id == USER


async def test_owner_refusal_outage_paging_and_expiry(client, prefix, app, masters, monkeypatch):
    import httpx

    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A"), bill("B")])).json()

    async def unavailable(owner, command):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(tasks, "preview_owner", unavailable)
    down = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]}, headers=auth(),
    )
    assert down.status_code == 409 and "unavailable" in down.json()["error"]["message"]
    assert {r["state"] for r in (await rows(client, prefix, job["id"])).values()} == {"STAGED"}

    async def refused(owner, command):
        request = httpx.Request("POST", "http://127.0.0.1")
        raise httpx.HTTPStatusError(
            "refused", request=request, response=httpx.Response(422, request=request)
        )

    monkeypatch.setattr(tasks, "preview_owner", refused)
    ready = (await client.post(prefix + f"/voucher-imports/{job['id']}/run",
                               headers=auth())).json()
    assert ready["state"] == "READY" and ready["invalid_count"] == 2
    assert (await detail(client, prefix, job["id"], "A"))["errors"][0]["code"] == (
        "calculation_refused"
    )
    page = await client.get(
        prefix + f"/voucher-imports/{job['id']}/vouchers", params={"limit": 1}, headers=auth()
    )
    assert [row["import_key"] for row in page.json()["items"]] == ["A"]
    following = await client.get(
        prefix + f"/voucher-imports/{job['id']}/vouchers",
        params={"limit": 1, "cursor": page.json()["next_cursor"]}, headers=auth(),
    )
    assert [row["import_key"] for row in following.json()["items"]] == ["B"]
    assert following.json()["next_cursor"] is None
    foreign_cursor = await client.get(
        prefix + "/voucher-imports", params={"cursor": page.json()["next_cursor"]},
        headers=auth(),
    )
    assert foreign_cursor.status_code == 422
    filtered = await client.get(
        prefix + "/voucher-imports", params={"state": "STAGED"}, headers=auth()
    )
    assert filtered.json()["items"] == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.scalar(select(im.VoucherImportJob))
            stored.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
            artifact = await db.scalar(select(im.VoucherImportArtifact))
            artifact.expires_at = stored.expires_at
    expired = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": ready["row_version"]}, headers=auth(),
    )
    assert expired.status_code == 409 and "expired" in expired.json()["error"]["message"]
    await upload(client, prefix, kind["id"], [bill("C")])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            purged = await db.get(im.VoucherImportArtifact, artifact.id)
            assert purged.byte_count == 0


async def test_review_regressions_lookup_failure_privacy_and_masking(
    client, prefix, app, masters, monkeypatch
):
    import httpx

    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()

    async def offline(owner, tenant, company, **codes):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(tasks, "default_lookup", offline)
    down = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]}, headers=auth(),
    )
    assert down.status_code == 409 and "lookup" in down.json()["error"]["message"]

    async def resolve(owner, tenant, company, **codes):
        return masters.resolution()

    monkeypatch.setattr(tasks, "default_lookup", resolve)
    ready = (await client.post(prefix + f"/voucher-imports/{job['id']}/run",
                               headers=auth())).json()
    assert ready["state"] == "READY"
    path = prefix + f"/voucher-imports/{job['id']}"
    peer = uuid7()
    clerk = (PERMISSIONS - {"vouchers.operation.read"}) | IMPORT
    for suffix in ("", "/vouchers", "/vouchers/A"):
        result = await client.get(path + suffix, headers=auth(user=peer, permissions=clerk))
        assert result.status_code == 403
    auditor = auth(user=peer, permissions=frozenset({"vouchers.import.read",
                                                     "vouchers.operation.read"}))
    assert (await client.get(path + "/vouchers", headers=auditor)).status_code == 200
    peers = await client.get(prefix + "/voucher-imports", params={"mine": "false"},
                             headers=auth(user=peer, permissions=clerk))
    assert peers.status_code == 403
    deny = [{"entity_type": "vouchers.voucher", "field_key": "invoice", "access": "read",
             "effect": "deny", "scope_type": "company", "scope_id": str(COMPANY)}]
    masked = (await client.get(path + "/vouchers/A", headers=auth(policies=deny))).json()
    assert masked.get("computed_payable") is None and masked.get("declared_total") is None
    assert "source_input" not in masked
    visible = (await client.get(path + "/vouchers/A", headers=auth())).json()
    assert visible["computed_payable"] == "1500.0000"


async def test_review_regressions_inputs_policy_drift_cancel_and_busy(
    client, prefix, app, masters, monkeypatch
):
    from billing_platform.errors import ConflictError

    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    number = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "JSON",
              "document": {"schema_version": 1, "vouchers": [{"amount": 1000.5}]}},
        headers=auth(),
    )
    assert number.status_code == 422
    job = (await upload(client, prefix, kind["id"], [bill("A", narration="Note")])).json()
    deny = [{"entity_type": "vouchers.voucher", "field_key": "narration", "access": "write",
             "effect": "deny", "scope_type": "company", "scope_id": str(COMPANY)}]
    drifted = await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]}, headers=auth(policies=deny),
    )
    assert drifted.json()["invalid_count"] == 1
    assert ("narration", "unknown_column") in {
        (e["column"], e["code"]) for e in (await detail(client, prefix, job["id"], "A"))["errors"]
    }
    second = (await upload(client, prefix, kind["id"], [bill("B"), bill("C")])).json()
    ready = await validated(client, prefix, second)
    original, attempts = tasks.create_draft, []

    async def busy(*args, **kwargs):
        attempts.append(args[4])
        if len(attempts) == 1:
            raise ConflictError("request is busy; retry with the same idempotency key")
        return await original(*args, **kwargs)

    monkeypatch.setattr(tasks, "create_draft", busy)
    paused = await client.post(
        prefix + f"/voucher-imports/{second['id']}/commit",
        json={"expected_version": ready["row_version"],
              "selection_digest": ready["selection_digest"]},
        headers=auth(),
    )
    assert paused.json()["state"] == "COMMITTING"
    assert {r["state"] for r in (await rows(client, prefix, second["id"])).values()} == {"VALID"}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.scalar(
                select(im.VoucherImportRow).where(im.VoucherImportRow.import_key == "B")
            )
            row.state = "CREATED"
    cancelled = await client.post(
        prefix + f"/voucher-imports/{second['id']}/cancel",
        json={"expected_version": paused.json()["row_version"]}, headers=auth(),
    )
    assert cancelled.json()["state"] == "CANCELLED" and cancelled.json()["created_count"] == 1


async def test_run_checks_permission_before_reading_the_job(client, prefix, masters):
    missing = await client.post(prefix + f"/voucher-imports/{uuid7()}/run", headers=headers())
    assert missing.status_code == 403
    allowed = await client.post(prefix + f"/voucher-imports/{uuid7()}/run", headers=auth())
    assert allowed.status_code == 404


async def test_duplicate_rule_is_chosen_per_job(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    first = (await upload(client, prefix, kind["id"], [bill("A", number="INV-9")])).json()
    assert first["duplicate_rule"] == "DATE_NUMBER_PARTY"
    ready = await validated(client, prefix, first)
    done = await client.post(
        prefix + f"/voucher-imports/{first['id']}/commit",
        json={"expected_version": ready["row_version"],
              "selection_digest": ready["selection_digest"]},
        headers=auth(),
    )
    assert done.json()["state"] == "SUCCEEDED"
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    candidates = [
        bill("SAME", number="INV-9"),
        bill("OTHER-SUPPLIER", supplier="SUP-2", number="INV-9"),
        bill("OTHER-DAY", number="INV-9", supplier_invoice_date=yesterday),
    ]
    expected = {
        # Same supplier and number in the financial year on another date: a warning only.
        "DATE_NUMBER_PARTY": {"SAME": "INVALID", "OTHER-SUPPLIER": "VALID",
                              "OTHER-DAY": "WARNING"},
        "DATE_NUMBER_ACCOUNT": {"SAME": "INVALID", "OTHER-SUPPLIER": "VALID",
                                "OTHER-DAY": "WARNING"},
        "DATE_NUMBER": {"SAME": "INVALID", "OTHER-SUPPLIER": "INVALID", "OTHER-DAY": "WARNING"},
    }
    for rule, states in expected.items():
        # Within one file the three bills only collide under DATE_NUMBER, at staging.
        job = (await upload(client, prefix, kind["id"], candidates, rule=rule)).json()
        assert job["duplicate_rule"] == rule
        result = await validated(client, prefix, job)
        assert result["state"] == "READY"
        found = {key: row["state"] for key, row in (await rows(client, prefix, job["id"])).items()}
        assert found == states, (rule, found)
        codes = {e["code"] for e in (await detail(client, prefix, job["id"], "SAME"))["errors"]}
        assert codes == {"duplicate_supplier_invoice"}
    invalid = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "CSV", "content_base64": "YWJjZA==",
              "duplicate_rule": "FISCAL_YEAR"},
        headers=auth(),
    )
    assert invalid.status_code == 422


async def test_validate_checks_permission_before_owner_configuration(
    client, prefix, app, masters
):
    kind = await purchase_type(client, prefix)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    # Unconfigured owners must not be revealed to a caller who may not validate at all.
    app.state.settings.master_lookup_owner = None
    from conftest import headers as plain

    refused = await client.post(prefix + f"/voucher-imports/{job['id']}/validate",
                                json={"expected_version": 1}, headers=plain())
    assert refused.status_code == 403
