"""Company onboarding creates usable, isolated native definitions without replacing work."""

import hashlib
import itertools
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type
from test_sources_custom_artifacts import source

from vouchers.domain.company_defaults import (
    FEATURES,
    PREVIOUS_VERSION,
    RELEASED_VERSIONS,
    SECOND_VERSION,
    THIRD_VERSION,
    VERSION,
    catalogue,
)
from vouchers.domain.configuration import digest, policy_wire
from vouchers.domain.registry import KINDS
from vouchers.models import core as m


@pytest.mark.parametrize(
    "features,count",
    [
        (frozenset(), 20),
        (frozenset({"inventory"}), 38),
        (frozenset({"inventory", "bom_definitions", "approval_workflow", "multi_currency"}), 39),
    ],
)
def test_catalogue_covers_applicable_kinds_and_conservative_native_rules(features, count):
    rows = catalogue(features)
    assert len(rows) == count and len({row.code for row in rows}) == count
    if "bom_definitions" in features:
        assert {row.kind for row in rows} == {kind.code for kind in KINDS}
    for row in rows:
        assert row.policy.approval_required == ("approval_workflow" in features)
        assert not row.policy.self_approval_allowed
        assert row.policy.default_series_id is None
        assert row.policy.default_template_revision_id is None
        if row.policy.invoice:
            assert not row.policy.invoice.manual_free_allowed
            assert not row.policy.invoice.same_item_deals_allowed
            assert row.policy.invoice.supplier_difference_limit == 0
        if row.policy.job_process:
            assert row.policy.job_process.allowed_consumption_modes == {"SEPARATE"}
        if row.policy.financial:
            assert row.policy.financial.foreign_currency_allowed == ("multi_currency" in features)
        # v4: nothing in the starter catalogue demands narration or a line description.
        assert not row.policy.narration_required, row.code
        assert not row.policy.line_description_required, row.code
    by_code = {row.code: row for row in rows}
    for prefix in ("PUR", "SAL"):
        # GST is recorded on service lines, so both account documents take both.
        assert by_code[prefix + "_ACC"].policy.invoice.allowed_supply_kinds == {
            "ACCOUNT",
            "SERVICE",
        }
        assert by_code[prefix + "_PRD"].policy.invoice.allowed_supply_kinds == {"GOODS", "SERVICE"}
        assert by_code[prefix + "_MIX"].policy.allowed_modes == {"MIXED"}
    for code in ("PUR_ACC", "PUR_PRD", "PUR_MIX", "SAL_ACC", "SAL_PRD", "SAL_MIX", "CRN", "DBN"):
        invoice = by_code[code].policy.invoice
        assert invoice.manual_discounts_allowed and invoice.charges_allowed, code
    for code in ("PAY", "REC", "PAY_ADV", "REC_ADV"):
        assert by_code[code].policy.financial.settlement_adjustments_allowed, code
    for code in ("CTR", "JRN"):
        assert not by_code[code].policy.financial.settlement_adjustments_allowed, code
    assert by_code["CTR"].policy.money.allowed_purposes == {"TRANSFER"}
    assert by_code["PAY_ADV"].profile == "ADVANCE"
    assert by_code["PAY_ADV"].policy.allowed_party_roles == {"SUPPLIER"}
    assert by_code["REC_ADV"].policy.allowed_party_roles == {"CUSTOMER"}
    assert by_code["QUOTE"].policy.order.allowed_purposes == {"QUOTE"}


def test_earlier_catalogues_keep_their_recipes_so_untouched_companies_are_recognised():
    assert RELEASED_VERSIONS == (PREVIOUS_VERSION, SECOND_VERSION, THIRD_VERSION, VERSION)
    assert VERSION.endswith("-v4") and len(set(RELEASED_VERSIONS)) == 4
    for version in (PREVIOUS_VERSION, SECOND_VERSION):
        by_code = {row.code: row for row in catalogue(frozenset(), version=version)}
        assert by_code["PUR_ACC"].policy.invoice.allowed_supply_kinds == {"ACCOUNT"}
    for version in (PREVIOUS_VERSION, SECOND_VERSION, THIRD_VERSION):
        by_code = {row.code: row for row in catalogue(frozenset({"inventory"}), version=version)}
        assert by_code["SAL_ACC"].policy.invoice.allowed_supply_kinds == {"ACCOUNT"}
        assert by_code["JRN"].policy.narration_required
        assert by_code["GRN"].policy.narration_required
        assert by_code["PUR_ACC"].policy.line_description_required
        assert not by_code["PUR_ACC"].policy.invoice.manual_discounts_allowed
        assert not by_code["PAY"].policy.financial.settlement_adjustments_allowed
    # Released recipes are recognised by their hashes, so they must never drift: this is the
    # digest of every v1-v3 recipe in every feature combination as released.
    combined = hashlib.sha256()
    for size in range(len(FEATURES) + 1):
        for combo in itertools.combinations(sorted(FEATURES), size):
            for version in (PREVIOUS_VERSION, SECOND_VERSION, THIRD_VERSION):
                for row in catalogue(frozenset(combo), version=version):
                    combined.update(
                        (version + row.code + digest(policy_wire(row.policy))).encode()
                    )
    assert combined.hexdigest() == (
        "f587344d8593461dbf331c8c0be6896380a4ae371e51dd9b0f600491656fd968"
    )
    third = {row.code: row for row in catalogue(frozenset(), version=THIRD_VERSION)}
    assert third["PUR_ACC"].policy.invoice.allowed_supply_kinds == {"ACCOUNT", "SERVICE"}
    with pytest.raises(ValueError, match="unsupported"):
        catalogue(frozenset(), version="company-voucher-defaults-v5")


async def test_a_new_companys_account_documents_take_service_lines(client, prefix):
    result = await client.post(
        prefix + "/voucher-type-defaults/bootstrap",
        headers=headers(),
        json={"expected_features": []},
    )
    assert result.status_code == 200 and result.json()["catalogue_version"] == VERSION
    types = [
        row
        for kind in ("PURCHASE", "SALES")
        for row in (
            await client.get(prefix + f"/voucher-types?kind={kind}&limit=50", headers=headers())
        ).json()["items"]
    ]
    by_code = {row["code"]: row for row in types}
    for code, kinds in (
        ("SAL_ACC", {"ACCOUNT", "SERVICE"}),
        ("PUR_ACC", {"ACCOUNT", "SERVICE"}),
        ("PUR_PRD", {"GOODS", "SERVICE"}),
        ("PUR_MIX", {"ACCOUNT", "GOODS", "SERVICE"}),
    ):
        detail = (
            await client.get(prefix + "/voucher-types/" + by_code[code]["id"], headers=headers())
        ).json()
        assert set(detail["policy"]["invoice"]["allowed_supply_kinds"]) == kinds, code


async def test_bootstrap_provisions_account_product_and_mixed_purchase(client, prefix, app):
    result = await client.post(
        prefix + "/voucher-type-defaults/bootstrap",
        headers=headers(),
        json={"expected_features": []},
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "READY"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(
                await db.scalars(
                    select(m.VoucherType).where(
                        m.VoucherType.company_id == COMPANY, m.VoucherType.kind == "PURCHASE"
                    )
                )
            )
            assert {row.code for row in rows} == {"PUR_ACC", "PUR_PRD", "PUR_MIX"}


async def test_replay_and_new_keys_do_not_duplicate_types_revisions_or_audits(client, prefix, app):
    url, body, auth = (
        prefix + "/voucher-type-defaults/bootstrap",
        {"expected_features": []},
        headers(),
    )
    first = await client.post(url, headers=auth, json=body)
    replay = await client.post(url, headers=auth, json=body)
    again = await client.post(url, headers=headers(), json=body)
    assert first.status_code == replay.status_code == again.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true" and replay.json() == first.json()
    assert first.json()["created_count"] == 20
    assert again.json()["created_count"] == 0 and again.json()["preserved_count"] == 20
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherType.id))) == 20
            assert await db.scalar(select(func.count(m.VoucherTypeRevision.id))) == 20
            audits = list(
                await db.scalars(select(Outbox).where(Outbox.event_type == "vouchers.type.create"))
            )
            assert len(audits) == 20
            assert all(
                row.payload["actor_type"] == "system"
                and row.payload["reason"] == VERSION
                for row in audits
            )


async def test_authored_and_retired_types_are_preserved_and_conflicts_are_reported(
    client, prefix, app
):
    authored = await create_type(
        client,
        prefix,
        code="PUR_ACC",
        kind="PURCHASE",
        name="Our expense bills",
        policy={"narration_required": True},
    )
    retired = await create_type(client, prefix, code="SAL_ACC", kind="SALES")
    stopped = await client.post(
        prefix + "/voucher-types/" + retired["id"] + "/retire",
        headers=headers(),
        json={"expected_version": retired["row_version"], "reason": "User retired this type"},
    )
    assert stopped.status_code == 200, stopped.text
    incompatible = await create_type(client, prefix, code="JRN", kind="MEMORANDUM")
    result = await client.post(
        prefix + "/voucher-type-defaults/bootstrap",
        headers=headers(),
        json={"expected_features": []},
    )
    assert result.status_code == 409 and "need review" in result.json()["error"]["message"]
    current = await client.get(prefix + "/voucher-types/" + authored["id"], headers=headers())
    assert current.json()["revision_id"] == authored["revision_id"]
    assert (
        current.json()["name"] == "Our expense bills"
        and current.json()["policy"]["narration_required"]
    )
    current = await client.get(prefix + "/voucher-types/" + incompatible["id"], headers=headers())
    assert current.json()["kind"] == "MEMORANDUM"


async def test_review_conflict_rolls_back_and_same_key_can_retry(client, prefix, app, monkeypatch):
    from vouchers.api import company_defaults as api

    original = api.ensure_defaults

    async def needs_review(*args, **kwargs):
        result = await original(*args, **kwargs)
        # Inject review after actual definitions/revisions/outbox writes, so rollback
        # and command-key release are exercised without mutating immutable identities.
        return result.model_copy(update={"status": "NEEDS_REVIEW", "review_count": 1})

    monkeypatch.setattr(api, "ensure_defaults", needs_review)
    auth = headers()
    url = prefix + "/voucher-type-defaults/bootstrap"
    assert (await client.post(url, headers=auth, json={"expected_features": []})).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            assert await db.scalar(select(func.count(m.VoucherType.id))) == 0
            assert await db.scalar(select(func.count(m.VoucherTypeRevision.id))) == 0
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(Outbox.event_type == "vouchers.type.create")
                )
                == 0
            )
    monkeypatch.setattr(api, "ensure_defaults", original)
    retry = await client.post(url, headers=auth, json={"expected_features": []})
    assert retry.status_code == 200 and retry.json()["created_count"] == 20, retry.text
    assert retry.headers.get("Idempotency-Replayed") != "true"


async def test_feature_progression_adds_types_and_disabling_preserves_history(client, prefix, app):
    for features, count, total in (
        (frozenset(), 20, 20),
        (frozenset({"inventory"}), 18, 38),
        (frozenset({"inventory", "bom_definitions"}), 1, 39),
        (frozenset(), 0, 39),
    ):
        result = await client.post(
            prefix + "/voucher-type-defaults/bootstrap",
            headers=headers(features=features),
            json={"expected_features": sorted(features)},
        )
        assert result.status_code == 200, result.text
        assert result.json()["created_count"] == count
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                assert await db.scalar(select(func.count(m.VoucherType.id))) == total


async def test_bootstrap_requires_current_company_authority_and_exact_features(client, prefix):
    url, body = prefix + "/voucher-type-defaults/bootstrap", {"expected_features": []}
    assert (await client.post(url, json=body)).status_code == 401
    assert (
        await client.post(url, json=body, headers=headers(permissions=frozenset({"vouchers.read"})))
    ).status_code == 403
    other = uuid7()
    assert (
        await client.post(
            f"/v1/companies/{other}/voucher-type-defaults/bootstrap", json=body, headers=headers()
        )
    ).status_code == 401
    assert (
        await client.post(url, json=body, headers=headers(features=frozenset({"inventory"})))
    ).status_code == 409
    assert (
        await client.post(url, json=body | {"policy": {}}, headers=headers())
    ).status_code == 422
    assert (
        await client.post(url, json={"expected_features": ["invented"]}, headers=headers())
    ).status_code == 422


def company_fact(version=1, **features):
    return {
        "entity_type": "company",
        "source_id": str(COMPANY),
        "source_version": version,
        "status": "ACTIVE",
        "facts": {
            "inventory": False,
            "bom_definitions": False,
            "approval_workflow": False,
            "multi_currency": False,
            **features,
        },
    }


async def test_setup_features_reconcile_only_untouched_system_rules(client, prefix, app):
    # Discovery can run between company creation and the wizard enabling selected features.
    assert (await source(client, app, masters=[company_fact()])).status_code == 200
    authored = await create_type(
        client, prefix, kind="JOURNAL", code="CUSTOM_JRN", policy={"narration_required": True}
    )
    result = await client.post(
        prefix + "/voucher-type-defaults/bootstrap",
        headers=headers(features=frozenset({"approval_workflow", "multi_currency"})),
        json={"expected_features": ["approval_workflow", "multi_currency"]},
    )
    assert result.status_code == 200, result.text
    rows = (
        await client.get(prefix + "/voucher-types?kind=PURCHASE&limit=50", headers=headers())
    ).json()["items"]
    account = next(row for row in rows if row["code"] == "PUR_ACC")
    saved = (await client.get(prefix + "/voucher-types/" + account["id"], headers=headers())).json()
    assert saved["policy"]["approval_required"] is True
    assert saved["current_revision"] == 2
    assert result.json()["updated_count"] == 20
    # A late signed worker snapshot may add definitions, but cannot undo setup rules.
    assert (await source(client, app, masters=[company_fact(2)])).status_code == 200
    late = (await client.get(prefix + "/voucher-types/" + account["id"], headers=headers())).json()
    assert late["revision_id"] == saved["revision_id"]
    custom = (
        await client.get(prefix + "/voucher-types/" + authored["id"], headers=headers())
    ).json()
    assert custom["revision_id"] == authored["revision_id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            history = list(
                await db.scalars(
                    select(m.VoucherTypeRevision)
                    .where(m.VoucherTypeRevision.type_id == uuid.UUID(account["id"]))
                    .order_by(m.VoucherTypeRevision.revision_number)
                )
            )
            assert len(history) == 2
            assert (
                not history[0].policy["approval_required"]
                and history[1].policy["approval_required"]
            )


async def test_default_codes_are_independent_in_two_companies(client, prefix, app):
    other = uuid7()
    for company in (COMPANY, other):
        response = await client.post(
            f"/v1/companies/{company}/voucher-type-defaults/bootstrap",
            headers=headers(company=company),
            json={"expected_features": []},
        )
        assert response.status_code == 200 and response.json()["created_count"] == 20
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(
                await db.scalars(select(m.VoucherType).where(m.VoucherType.code == "PUR_ACC"))
            )
            assert {row.company_id for row in rows} == {COMPANY, other}
            assert len({row.id for row in rows}) == 2
    foreign = await client.get(
        prefix + "/voucher-types/" + str(next(row.id for row in rows if row.company_id == other)),
        headers=headers(),
    )
    assert foreign.status_code == 403


async def test_provisioned_purchase_account_bill_accepts_native_capture(client, prefix, app):
    from test_foundation import draft
    from test_invoice_capture import invoice_body, seed_accounts

    result = await client.post(
        prefix + "/voucher-type-defaults/bootstrap",
        headers=headers(),
        json={"expected_features": []},
    )
    assert result.status_code == 200
    rows = (
        await client.get(prefix + "/voucher-types?kind=PURCHASE&limit=50", headers=headers())
    ).json()["items"]
    account = next(row for row in rows if row["code"] == "PUR_ACC")
    detail = (
        await client.get(prefix + "/voucher-types/" + account["id"], headers=headers())
    ).json()
    body = invoice_body()
    body["components"] = []
    body["supplies"][0]["supply_kind"] = "ACCOUNT"
    await seed_accounts(app, body)
    voucher, _ = await draft(
        client,
        prefix,
        detail["revision_id"],
        mode="ACCOUNTS",
        invoice=body,
        references=[{"purpose": "SUPPLIER_INVOICE", "reference": "SUP-42"}],
    )
    assert voucher["status"] == "DRAFT"


async def test_concurrent_native_company_bootstrap_serializes(client, prefix, engine):
    import asyncio

    if engine.dialect.name != "mysql":
        pytest.skip("MySQL company fence regression")
    results = await asyncio.gather(
        *(
            client.post(
                prefix + "/voucher-type-defaults/bootstrap",
                headers=headers(),
                json={"expected_features": []},
            )
            for _ in range(2)
        )
    )
    assert all(result.status_code == 200 for result in results), [r.text for r in results]
    assert sorted(result.json()["created_count"] for result in results) == [0, 20]


async def test_only_signed_identity_company_facts_provision_and_stale_sources_never_enable(
    client, app
):
    fact = company_fact()
    assert (await source(client, app, issuer="catalog", masters=[fact])).status_code == 422
    assert (
        await source(client, app, masters=[company_fact(bom_definitions=True)])
    ).status_code == 422
    assert (await source(client, app, masters=[company_fact(inventory="true")])).status_code == 422
    assert (await source(client, app, masters=[fact, fact])).status_code == 422
    assert (
        await source(client, app, masters=[fact | {"source_id": str(uuid7())}])
    ).status_code == 422
    accepted = await source(client, app, masters=[company_fact(2, inventory=True)])
    assert accepted.status_code == 200, accepted.text
    accepted = await source(client, app, masters=[company_fact(3)])
    assert accepted.status_code == 200
    # The stale snapshot asks for manufacturing; the accepted current snapshot disables it.
    accepted = await source(
        client, app, masters=[company_fact(1, inventory=True, bom_definitions=True)]
    )
    assert accepted.status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(m.VoucherType)))
            assert len(rows) == 38 and "MFG" not in {row.code for row in rows}
            company = await db.scalar(
                select(m.VoucherMasterEvidence).where(
                    m.VoucherMasterEvidence.entity_type == "company"
                )
            )
            assert company.source_version == 3 and not company.facts["inventory"]
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherType.id))) == 0


async def test_native_account_section_rules_match_the_configured_policy(client, prefix, app):
    saved = await create_type(
        client,
        prefix,
        kind="JOURNAL",
        policy={
            "allowed_modes": ["ACCOUNTS"],
            "default_mode": "ACCOUNTS",
            "required_sections": ["ACCOUNTS"],
        },
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rules = list(
                await db.scalars(
                    select(m.VoucherTypeSection).where(
                        m.VoucherTypeSection.company_id == COMPANY,
                        m.VoucherTypeSection.type_revision_id == uuid.UUID(saved["revision_id"]),
                        m.VoucherTypeSection.section == "ACCOUNTS",
                    )
                )
            )
            assert len(rules) == 1 and rules[0].requirement == "REQUIRED"
