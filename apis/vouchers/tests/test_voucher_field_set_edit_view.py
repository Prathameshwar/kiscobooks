"""A saved voucher's field-set carries what a client needs to edit it.

The Console reopens a saved Purchase to edit it. To do that it needs the same native schema and
effective configuration the type's field-set gives for a new one, resolved for the voucher's type
and dates. The route used to return only the pinned custom-field definitions, so every reopen of a
saved bill failed.
"""

import datetime as dt

from billing_platform.ids import uuid7
from conftest import COMPANY, headers
from test_foundation import create_type, draft


async def saved(client, prefix, **type_changes):
    kind = await create_type(client, prefix, **type_changes)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    return kind, voucher


def view(client, prefix, voucher, **kwargs):
    return client.get(prefix + f'/vouchers/{voucher["id"]}/field-set', headers=headers(**kwargs))


async def test_saved_voucher_field_set_carries_the_native_schema_and_configuration(client, prefix):
    kind, voucher = await saved(client, prefix)
    result = await view(client, prefix, voucher)
    assert result.status_code == 200, result.text
    body = result.json()
    # What the route always returned stays.
    assert {"voucher_id", "revision_id", "header", "items"} <= body.keys()
    assert body["voucher_id"] == voucher["id"]
    # What an editor needs.
    assert {"native", "custom", "configuration", "layouts"} <= body.keys()
    assert body["configuration"]["type_revision_id"] == kind["revision_id"]
    assert body["configuration"]["kind"] == "MEMORANDUM"
    assert "document_date" in body["native"]["properties"]
    # It is the very answer the type gives for a new voucher on those dates.
    fresh = await client.get(
        prefix + f'/voucher-types/{kind["id"]}/field-set',
        params={"date": dt.date.today().isoformat()},
        headers=headers(),
    )
    assert fresh.status_code == 200, fresh.text
    for key in ("native", "custom", "configuration", "layouts"):
        assert body[key] == fresh.json()[key], key


async def test_the_edit_view_names_the_current_type_revision_after_the_type_is_revised(
    client, prefix
):
    kind, voucher = await saved(client, prefix)
    revised = await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/revisions",
        headers=headers(),
        json={"expected_version": 1, "policy": {"allowed_template_revision_ids": []}},
    )
    assert revised.status_code == 200, revised.text
    current = revised.json()["revision_id"]
    assert current != kind["revision_id"]
    body = (await view(client, prefix, voucher)).json()
    # A write is validated against the type's current revision, so that is what the editor is told.
    assert body["configuration"]["type_revision_id"] == current
    assert (await client.get(prefix + f'/vouchers/{voucher["id"]}', headers=headers())).json()[
        "type_revision_id"
    ] == kind["revision_id"]


async def test_the_edit_view_follows_current_field_policy(client, prefix):
    _, voucher = await saved(client, prefix)
    policy = lambda access: [  # noqa: E731
        {
            "entity_type": "vouchers.voucher",
            "field_key": "narration",
            "access": access,
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    plain = (await view(client, prefix, voucher)).json()["native"]["properties"]
    assert "narration" in plain and plain["narration"]["readOnly"] is False
    write_denied = (await view(client, prefix, voucher, policies=policy("write"))).json()
    assert write_denied["native"]["properties"]["narration"]["readOnly"] is True
    read_denied = (await view(client, prefix, voucher, policies=policy("read"))).json()
    assert "narration" not in read_denied["native"]["properties"]
    # The pinned custom-field metadata is filtered by the same policy, as before.
    assert read_denied["header"] == []


async def test_a_voucher_whose_type_is_retired_can_still_be_read_but_says_it_cannot_be_edited(
    client, prefix
):
    kind, voucher = await saved(client, prefix)
    retired = await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/retire",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert retired.status_code == 200, retired.text
    result = await view(client, prefix, voucher)
    assert result.status_code == 200, result.text
    body = result.json()
    assert {"voucher_id", "revision_id", "header", "items"} <= body.keys()
    assert "native" not in body and "configuration" not in body
    assert (
        "retired" in body["configuration_unavailable"]
        or "superseded" in body["configuration_unavailable"]
    )


async def test_the_edit_view_needs_authentication_and_the_read_permission(client, prefix):
    _, voucher = await saved(client, prefix)
    path = prefix + f'/vouchers/{voucher["id"]}/field-set'
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=headers(permissions=frozenset()))).status_code == 403


async def test_the_edit_view_is_scoped_to_the_requested_company_and_tenant(client, prefix):
    _, voucher = await saved(client, prefix)
    path = prefix + f'/vouchers/{voucher["id"]}/field-set'
    # A company context signed for another company is not a context for this route.
    stale = await client.get(path, headers=headers(company=uuid7()))
    assert stale.status_code == 401, stale.text
    # A user whose grants are for another company holds no read permission here.
    other_grants = headers(company=uuid7())
    here = {key: value for key, value in headers().items() if key.startswith("X-Company")}
    wrong_company = await client.get(path, headers=other_grants | here)
    assert wrong_company.status_code == 403, wrong_company.text
    # Another tenant cannot see that the voucher exists.
    wrong_tenant = await client.get(path, headers=headers(tenant=uuid7()))
    assert wrong_tenant.status_code == 404, wrong_tenant.text
    # Nor can this company's route be used to reach a voucher that belongs to another company.
    other = uuid7()
    foreign = f"/v1/companies/{other}"
    made = await client.post(
        foreign + "/voucher-types",
        json={"code": "OTHER", "name": "Other", "kind": "MEMORANDUM"},
        headers=headers(company=other),
    )
    assert made.status_code == 201, made.text
    theirs = await client.post(
        foreign + "/vouchers",
        json={
            "type_revision_id": made.json()["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "narration": "Another company's bill",
        },
        headers=headers(company=other),
    )
    assert theirs.status_code == 201, theirs.text
    reach = await client.get(
        prefix + f'/vouchers/{theirs.json()["id"]}/field-set', headers=headers()
    )
    assert reach.status_code == 403, reach.text
    assert reach.json()["error"]["message"] == "resource is outside the requested company"


async def test_a_voucher_with_a_class_of_a_superseded_type_revision_is_still_readable(
    client, prefix
):
    """Revising the type leaves the class on the old revision; the saved capture must still read."""
    kind = await create_type(client, prefix)
    created = await client.post(
        prefix + f'/voucher-types/{kind["id"]}/classes',
        headers=headers(),
        json={"expected_version": 1, "code": "CLS", "name": "Class", "policy": {}},
    )
    assert created.status_code == 201, created.text
    voucher, _ = await draft(client, prefix, kind["revision_id"], class_id=created.json()["id"])
    current = await client.get(prefix + f'/voucher-types/{kind["id"]}', headers=headers())
    revised = await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/revisions",
        headers=headers(),
        json={
            "expected_version": current.json()["row_version"],
            "policy": {"allowed_template_revision_ids": []},
        },
    )
    assert revised.status_code == 200, revised.text
    result = await view(client, prefix, voucher)
    assert result.status_code == 200, result.text
    body = result.json()
    # The pinned capture is still returned; only the edit view is withheld, with the reason.
    assert {"voucher_id", "revision_id", "header", "items"} <= body.keys()
    assert body["voucher_id"] == voucher["id"]
    assert "native" not in body and "configuration" not in body
    assert "class belongs to another type revision" in body["configuration_unavailable"]
