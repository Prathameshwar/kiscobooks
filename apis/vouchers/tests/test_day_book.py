import datetime as dt
import uuid

import pytest
from conftest import COMPANY, PERMISSIONS, headers
from test_foundation import create_type, draft


def filters(**changes):
    today = dt.date.today().isoformat()
    return {"date_from": today, "date_to": today, "include_summary": True, **changes}


def authority(**changes):
    return headers(permissions=PERMISSIONS | {"report.read"}, **changes)


async def test_live_activity_counts_current_revisions_and_cursor_without_duplicate_documents(
    client, prefix
):
    kind = await create_type(client, prefix)
    documents = [
        await draft(client, prefix, kind["revision_id"], narration="Day book " + str(index))
        for index in range(3)
    ]
    first = await client.post(
        prefix + "/day-book/query", json=filters(limit=2), headers=authority()
    )
    assert first.status_code == 200, first.text
    value = first.json()
    assert value["scope"] == "LIVE_DOCUMENTS"
    assert len(value["items"]) == 2
    assert value["summary"] == {
        "voucher_count": 3,
        "by_status": {"DRAFT": 3},
        "by_kind": {"MEMORANDUM": 3},
    }
    second = await client.post(
        prefix + "/day-book/query",
        json=filters(limit=2, cursor=value["page"]["next_cursor"]),
        headers=authority(),
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 1
    ids = {item["id"] for item in value["items"] + second.json()["items"]}
    assert ids == {document[0]["id"] for document in documents}
    mismatched = await client.post(
        prefix + "/day-book/query",
        json=filters(limit=2, cursor=value["page"]["next_cursor"], q="different"),
        headers=authority(),
    )
    assert mismatched.status_code == 422, mismatched.text


@pytest.mark.parametrize(
    "changes,count",
    [
        ({"q": "Day book 1"}, 1),
        ({"q": "%"}, 0),
        ({"status": "POSTED"}, 0),
        ({"kinds": ["MEMORANDUM"]}, 2),
        ({"kinds": ["PURCHASE"]}, 0),
        ({"conditions": [{"field": "narration", "value": "Day book 1", "operator": "equals"}]}, 1),
        (
            {
                "match": "ANY",
                "conditions": [
                    {"field": "kind", "value": "MEMORANDUM", "operator": "equals"},
                    {"field": "narration", "value": "missing"},
                ],
            },
            2,
        ),
    ],
)
async def test_filters_apply_to_rows_and_complete_summary(client, prefix, changes, count):
    kind = await create_type(client, prefix)
    for index in range(2):
        await draft(client, prefix, kind["revision_id"], narration="Day book " + str(index))
    response = await client.post(
        prefix + "/day-book/query", json=filters(**changes), headers=authority()
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["voucher_count"] == count
    assert len(response.json()["items"]) == count


async def test_summary_is_opt_in_and_no_financial_amounts_are_invented(client, prefix):
    kind = await create_type(client, prefix)
    await draft(client, prefix, kind["revision_id"])
    response = await client.post(
        prefix + "/day-book/query", json=filters(include_summary=False), headers=authority()
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"] is None
    assert not {"debit", "credit", "amount"} & response.json()["items"][0].keys()


async def test_type_revision_lookup_is_company_scoped(client, prefix):
    kind = await create_type(client, prefix)
    response = await client.get(
        prefix + "/day-book/types/" + kind["id"] + "/revisions", headers=authority()
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"type_id": kind["id"], "revision_ids": [kind["revision_id"]]}
    wrong = await client.get(
        f"/v1/companies/{(other := uuid.uuid4())}/day-book/types/" + kind["id"] + "/revisions",
        headers=authority(company=other),
    )
    assert wrong.status_code == 403, wrong.text


async def test_read_authority_and_field_denies_apply_before_any_summary(client, prefix):
    path = prefix + "/day-book/query"
    assert (await client.post(path, json=filters())).status_code == 401
    assert (await client.post(path, json=filters(), headers=headers())).status_code == 403
    assert (
        await client.post(
            f"/v1/companies/{uuid.uuid4()}/day-book/query", json=filters(), headers=authority()
        )
    ).status_code == 401
    policy = {
        "entity_type": "vouchers.voucher",
        "field_key": "narration",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.post(path, json=filters(), headers=authority(policies=[policy]))
    ).status_code == 403


@pytest.mark.parametrize(
    "field", ["id", "type_id", "revision_id", "type_revision_id", "revision_ids", "revision_number"]
)
async def test_type_revision_read_denies_apply_to_lookup(client, prefix, field):
    kind = await create_type(client, prefix)
    policy = {
        "entity_type": "vouchers.configuration",
        "field_key": field,
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    response = await client.get(
        prefix + "/day-book/types/" + kind["id"] + "/revisions",
        headers=authority(policies=[policy]),
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "changes",
    [
        {"date_to": "2020-01-01"},
        {"amount_min": "1"},
        {"limit": 201},
        {"conditions": [{"field": "custom_secret", "value": "x"}]},
        {"type_id": "wrong"},
    ],
)
async def test_invalid_and_unsupported_filters_rejected(client, prefix, changes):
    result = await client.post(
        prefix + "/day-book/query", json=filters(**changes), headers=authority()
    )
    assert result.status_code == 422, result.text


async def test_live_documents_never_cross_company_or_tenant(client, prefix):
    kind = await create_type(client, prefix)
    await draft(client, prefix, kind["revision_id"])
    for scope in ({"company": uuid.uuid4()}, {"tenant": uuid.uuid4()}):
        company = scope.get("company", COMPANY)
        response = await client.post(
            f"/v1/companies/{company}/day-book/query", json=filters(), headers=authority(**scope)
        )
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
        assert response.json()["summary"]["voucher_count"] == 0
