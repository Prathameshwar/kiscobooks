import datetime as dt
import uuid

from conftest import headers
from test_foundation import create_type


async def test_v2_company_default_survives_sparse_type_policy(client, prefix):
    config = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "SPARSE_V2",
            "name": "Sparse v2 inheritance",
            "policy": {"schema_version": 2, "default_narration": "Company narration"},
        },
    )
    assert config.status_code == 201, config.text
    data = config.json()
    published = await client.post(
        prefix + "/voucher-configurations/" + data["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    kind = await create_type(client, prefix, policy={"schema_version": 2})
    created = await client.post(
        prefix + "/vouchers",
        headers=headers(),
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["narration"] == "Company narration"


async def test_sales_workflow_binding_is_visible_only_to_standard_sales(client, prefix):
    wrong_family = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "WRONG_WORKFLOW",
            "name": "Wrong family",
            "family": "PURCHASE",
            "policy": {"schema_version": 2, "sales_workflow": {"max_due_days": 45}},
        },
    )
    assert wrong_family.status_code == 422
    config = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "SALES_WORKFLOW_V2",
            "name": "Sales invoice workflow",
            "policy": {
                "schema_version": 2,
                "sales_workflow": {"max_due_days": 45},
            },
        },
    )
    assert config.status_code == 201, config.text
    data = config.json()
    published = await client.post(
        prefix + "/voucher-configurations/" + data["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    sales = await create_type(
        client, prefix, code="SALES_WORKFLOW", kind="SALES", policy={"schema_version": 2}
    )
    memo = await create_type(client, prefix, code="MEMO_WORKFLOW", policy={"schema_version": 2})
    for kind, visible in ((sales, True), (memo, False)):
        response = await client.get(
            prefix + "/voucher-types/" + kind["id"] + "/effective-configuration",
            headers=headers(),
            params={"date": dt.date.today().isoformat()},
        )
        assert response.status_code == 200, response.text
        assert ("sales_workflow" in response.json()["policy"]) is visible
        if not visible:
            assert data["revision_id"] not in response.json()["policy_revision_ids"]


async def test_common_order_controls_apply_only_to_order_profiles(client, prefix):
    config = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "ORDER_V2",
            "name": "Order limits",
            "policy": {
                "schema_version": 2,
                "order": {"max_validity_days": 10},
                "money": {"max_tenders": 1},
            },
        },
    )
    assert config.status_code == 201, config.text
    data = config.json()
    published = await client.post(
        prefix + "/voucher-configurations/" + data["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    memo = await create_type(client, prefix, code="MEMO2", policy={"schema_version": 2})
    incompatible = await client.post(
        prefix + "/voucher-types/" + memo["id"] + "/configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 1,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert incompatible.status_code == 422, incompatible.text
    quote = await create_type(
        client,
        prefix,
        code="QUOTE2",
        kind="SALES_ORDER",
        profile="QUOTATION",
        policy={"schema_version": 2, "default_mode": "ITEMS"},
    )
    for kind, expected_order in ((memo, False), (quote, True)):
        response = await client.get(
            prefix + "/voucher-types/" + kind["id"] + "/effective-configuration",
            headers=headers(),
            params={"date": dt.date.today().isoformat()},
        )
        assert response.status_code == 200, response.text
        assert ("order" in response.json()["policy"]) is expected_order
        assert "money" not in response.json()["policy"]
        if not expected_order:
            assert data["revision_id"] not in response.json()["policy_revision_ids"]


async def test_common_production_controls_are_profile_scoped_and_non_executable(client, prefix):
    config = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "PRODUCTION_V2",
            "name": "Production preparation",
            "policy": {
                "schema_version": 2,
                "manufacturing": {"max_output_lines": 3},
                "job_process": {"order_required": True},
            },
        },
    )
    assert config.status_code == 201, config.text
    data = config.json()
    published = await client.post(
        prefix + "/voucher-configurations/" + data["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    kinds = (
        await create_type(client, prefix, code="MEMO_PROD", policy={"schema_version": 2}),
        await create_type(
            client,
            prefix,
            code="MFG_PROD",
            kind="STOCK_JOURNAL",
            profile="MANUFACTURING",
            policy={"schema_version": 2},
        ),
        await create_type(
            client,
            prefix,
            code="JOB_PROD",
            kind="JOB_WORK_OUT_ORDER",
            policy={"schema_version": 2, "job_process": {"role": "PRINCIPAL"}},
        ),
    )
    for kind, expected in zip(kinds, (set(), {"manufacturing"}, {"job_process"}), strict=True):
        selected = await client.get(
            prefix + "/voucher-types/" + kind["id"] + "/effective-configuration",
            headers=headers(),
            params={"date": dt.date.today().isoformat()},
        )
        assert selected.status_code == 200, selected.text
        actual = {"manufacturing", "job_process"} & selected.json()["policy"].keys()
        assert actual == expected
        if not expected:
            assert data["revision_id"] not in selected.json()["policy_revision_ids"]
    assert kinds[2]["kind"] == "JOB_WORK_OUT_ORDER"
    unsupported = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "UNREADY_COMBINED",
            "name": "Combined consumption before owner readiness",
            "policy": {
                "schema_version": 2,
                "job_process": {"allowed_consumption_modes": ["SEPARATE", "COMBINED"]},
            },
        },
    )
    assert unsupported.status_code == 422


async def test_v2_money_binding_uses_posting_date_without_moving_document_defaults(client, prefix):
    for code, start, end, narration, allocation in (
        ("APR_V2", "2026-04-01", "2026-05-01", "April", True),
        ("MAY_V2", "2026-05-01", None, "May", False),
    ):
        config = await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={
                "code": code,
                "name": code,
                "policy": {
                    "schema_version": 2,
                    "default_narration": narration,
                    "financial": {"allocations_allowed": allocation},
                },
            },
        )
        assert config.status_code == 201, config.text
        data = config.json()
        published = await client.post(
            prefix + "/voucher-configurations/" + data["id"] + "/publish",
            headers=headers(),
            json={"expected_version": 1},
        )
        assert published.status_code == 200, published.text
        bound = await client.post(
            prefix + "/voucher-configuration-bindings",
            headers=headers(),
            json={
                "expected_version": 2,
                "configuration_revision_id": data["revision_id"],
                "valid_from": start,
                "valid_to": end,
            },
        )
        assert bound.status_code == 201, bound.text
    payment = await create_type(
        client, prefix, code="PAY_V2", kind="PAYMENT", policy={"schema_version": 2}
    )
    path = prefix + "/voucher-types/" + payment["id"] + "/effective-configuration"
    missing_date = await client.get(path, headers=headers(), params={"date": "2026-04-20"})
    assert missing_date.status_code == 409, missing_date.text
    selected = await client.get(
        path,
        headers=headers(),
        params={"date": "2026-04-20", "posting_date": "2026-05-02"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["policy"]["default_narration"] == "April"
    assert selected.json()["policy"]["financial"]["allocations_allowed"] is False


async def test_v1_configuration_digest_keeps_document_date_selection(client, prefix):
    config = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={
            "code": "LEGACY_DATE",
            "name": "Legacy date",
            "policy": {"default_narration": "Legacy"},
        },
    )
    assert config.status_code == 201, config.text
    data = config.json()
    published = await client.post(
        prefix + "/voucher-configurations/" + data["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": data["revision_id"],
            "valid_from": "2026-04-01",
            "valid_to": "2026-05-01",
        },
    )
    assert bound.status_code == 201, bound.text
    payment = await create_type(client, prefix, code="LEGACY_PAY", kind="PAYMENT")
    path = prefix + "/voucher-types/" + payment["id"] + "/effective-configuration"
    without_posting = await client.get(path, headers=headers(), params={"date": "2026-04-20"})
    with_posting = await client.get(
        path,
        headers=headers(),
        params={"date": "2026-04-20", "posting_date": "2026-05-20"},
    )
    assert without_posting.status_code == with_posting.status_code == 200
    assert without_posting.json()["digest"] == with_posting.json()["digest"]


async def test_configured_defaults_and_cancel_incomplete(client, prefix):
    kind = await create_type(
        client,
        prefix,
        policy={"default_narration": "Configured narration", "narration_required": True},
    )
    result = await client.post(
        prefix + "/vouchers",
        headers=headers(),
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["narration"] == "Configured narration"
    cancel = await client.post(
        prefix + "/vouchers/" + result.json()["id"] + "/cancel",
        headers=headers(),
        json={"expected_version": 1, "reason": "Abandoned"},
    )
    assert cancel.status_code == 200, cancel.text


async def test_history_uses_scoped_signed_cursor(client, prefix):
    kind = await create_type(client, prefix)
    created = await client.post(
        prefix + "/vouchers",
        headers=headers(),
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
        },
    )
    voucher = created.json()
    await client.post(
        prefix + "/vouchers/" + voucher["id"] + "/submit",
        headers=headers(),
        json={"expected_version": 1},
    )
    await client.post(
        prefix + "/vouchers/" + voucher["id"] + "/reject",
        headers=headers(user=uuid.uuid4()),
        json={"expected_version": 2, "reason": "Fix"},
    )
    url = prefix + "/vouchers/" + voucher["id"] + "/history"
    first = await client.get(url, headers=headers(), params={"limit": 1})
    assert first.status_code == 200, first.text
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(url, headers=headers(), params={"limit": 1, "cursor": cursor})
    assert len(second.json()["items"]) == 1
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    assert (
        await client.get(
            url, headers=headers(user=uuid.uuid4()), params={"limit": 1, "cursor": cursor}
        )
    ).status_code == 422


async def test_item_field_metadata_obeys_denies(client, prefix):
    from conftest import COMPANY

    kind = await create_type(client, prefix)
    rule = {
        "entity_type": "vouchers.voucher_item",
        "field_key": "actual_quantity",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    response = await client.get(
        prefix + "/voucher-types/" + kind["id"] + "/field-set",
        params={"date": "2026-10-10"},
        headers=headers(policies=[rule]),
    )
    item = response.json()["native"]["properties"]["lines"]["items"]["properties"]["item"]
    assert "actual_quantity" not in item["properties"]


async def test_cancel_remains_available_after_type_retirement(client, prefix):
    from test_foundation import draft

    kind = await create_type(client, prefix)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/retire",
        headers=headers(),
        json={"expected_version": 1},
    )
    cancelled = await client.post(
        prefix + "/vouchers/" + voucher["id"] + "/cancel",
        headers=headers(),
        json={"expected_version": 1, "reason": "Abandoned"},
    )
    assert cancelled.status_code == 200, cancelled.text


async def test_invalid_calendar_binding_is_validation_error(client, prefix):
    response = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 1,
            "configuration_revision_id": str(uuid.uuid4()),
            "valid_from": "2026-99-99",
        },
    )
    assert response.status_code == 422, response.text


async def test_company_type_clone_pins_origin_and_cannot_weaken_source(client, prefix):
    source = await create_type(client, prefix, policy={"max_lines": 3, "narration_required": True})
    clone = await create_type(
        client,
        prefix,
        code="CLONE",
        derived_from_revision_id=source["revision_id"],
        policy={"max_lines": 200, "narration_required": False},
    )
    assert clone["derived_from_revision_id"] == source["revision_id"]
    assert clone["policy"]["max_lines"] == 3 and clone["policy"]["narration_required"]
    incompatible = await client.post(
        prefix + "/voucher-types",
        headers=headers(),
        json={
            "code": "WRONG",
            "name": "Wrong",
            "kind": "SALES",
            "derived_from_revision_id": source["revision_id"],
        },
    )
    assert incompatible.status_code == 409
    changed = await client.post(
        prefix + "/voucher-types/" + source["id"] + "/revisions",
        headers=headers(),
        json={"expected_version": 1, "policy": {"max_lines": 1}},
    )
    assert changed.status_code == 200
    reread = await client.get(prefix + "/voucher-types/" + clone["id"], headers=headers())
    assert reread.json()["policy"]["max_lines"] == 3


async def test_number_and_artifact_defaults_inherit_and_remain_pinned(client, prefix):
    from test_foundation import draft

    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={"code": "CONFIGURED", "prefix": "CONF-"},
        )
    ).json()
    template = (
        await client.post(
            prefix + "/voucher-templates",
            headers=headers(),
            json={"code": "CONFIGURED", "title": "Configured document"},
        )
    ).json()
    policy = {
        "allowed_series_ids": [series["id"]],
        "default_series_id": series["id"],
        "allowed_template_revision_ids": [template["revision_id"]],
        "default_template_revision_id": template["revision_id"],
        "approval_required": False,
    }
    config = (
        await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={"code": "DEFAULTS", "name": "Company defaults", "policy": policy},
        )
    ).json()
    published = await client.post(
        prefix + "/voucher-configurations/" + config["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": config["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    kind = await create_type(client, prefix, policy={"approval_required": False})
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    path = prefix + "/vouchers/" + voucher["id"]
    denied = await client.post(
        path + "/issue",
        headers=headers(),
        json={"expected_version": 1, "series_id": str(uuid.uuid4())},
    )
    assert denied.status_code == 422, denied.text
    denied_print = await client.post(
        path + "/artifacts",
        headers=headers(),
        json={"expected_version": 1, "template_revision_id": str(uuid.uuid4())},
    )
    assert denied_print.status_code == 422
    issued = await client.post(path + "/issue", headers=headers(), json={"expected_version": 1})
    assert issued.status_code == 200, issued.text
    assert issued.json()["issue_number"].startswith("CONF-")
    artifact = await client.post(
        path + "/artifacts", headers=headers(), json={"expected_version": 2}
    )
    assert artifact.status_code == 202, artifact.text
    # A later type revision cannot substitute a historical document's print defaults.
    revised = await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/revisions",
        headers=headers(),
        json={"expected_version": 1, "policy": {"allowed_template_revision_ids": []}},
    )
    assert revised.status_code == 200, revised.text
    again = await client.post(path + "/artifacts", headers=headers(), json={"expected_version": 2})
    assert again.status_code == 202 and again.json()["id"] == artifact.json()["id"]


async def test_configuration_references_cannot_cross_company(client, prefix):
    from conftest import COMPANY

    other = uuid.uuid4()
    other_prefix = prefix.replace(str(COMPANY), str(other))
    series = (
        await client.post(
            other_prefix + "/voucher-series",
            headers=headers(company=other),
            json={"code": "FOREIGN"},
        )
    ).json()
    template = (
        await client.post(
            other_prefix + "/voucher-templates",
            headers=headers(company=other),
            json={"code": "FOREIGN", "title": "Other company"},
        )
    ).json()
    for policy in (
        {"default_series_id": series["id"]},
        {"default_template_revision_id": template["revision_id"]},
    ):
        result = await client.post(
            prefix + "/voucher-types",
            headers=headers(),
            json={"code": "FOREIGN", "name": "Invalid", "kind": "MEMORANDUM", "policy": policy},
        )
        assert result.status_code == 422, result.text
