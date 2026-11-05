import base64
import json
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.import_contracts import CONTROLS, FileFormat
from billing_platform.import_files import document
from billing_platform.import_models import ImportChangeSetEffect, ImportJobAttempt
from fastapi import FastAPI
from sqlalchemy import func, select

from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import BASE, new_party, party_accounts, post, prepare


def source(
    file_format: FileFormat = "CSV",
    *,
    code: str = "IMPORT",
    legal_name: str = "Imported Limited",
    resource: str = "customer",
) -> dict[str, str]:
    raw = document(
        file_format,
        [
            (
                "Records",
                [*CONTROLS, "_payload"],
                [
                    [
                        "party",
                        "customer",
                        resource,
                        "CREATE",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        json.dumps(
                            {
                                "code": code,
                                "name": "Imported",
                                "legal_name": legal_name,
                                "country_code": "IN",
                            }
                        ),
                    ]
                ],
            )
        ],
    )
    return {
        "filename": "customers." + file_format.lower(),
        "format": file_format,
        "content_base64": base64.b64encode(raw).decode(),
    }


async def stage(client: httpx.AsyncClient, file: dict[str, str] | None = None) -> dict[str, Any]:
    # A party is only ever created by the ready customer/supplier import, never as a bare row.
    template = await post(
        client,
        "/import-templates",
        {"definition": "parties", "parameters": {"resource": "customer", "role": "CUSTOMER"}},
    )
    return await post(
        client, "/import-jobs", {"template_id": template["id"], "files": [file or source()]}
    )


@pytest.mark.parametrize("file_format", ["CSV", "TSV", "XLSX"])
async def test_file_import_dry_run_commit_history_original_and_replay(
    client: httpx.AsyncClient, app: FastAPI, file_format: FileFormat
) -> None:
    await prepare(client)
    file = source(file_format)
    job = await stage(client, file)
    root = "/import-jobs/" + job["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = await db.scalar(
                select(func.count(Outbox.id)).where(Outbox.event_type == "accounting.party.create")
            )
    validated = await post(
        client, root + "/validate", {"expected_version": job["row_version"]}, status=200
    )
    assert validated["state"] == "READY", validated
    assert not (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            # Validation leaves only its lifecycle event, no native create event.
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "accounting.party.create"
                    )
                )
                == before
            )
    auth = headers()
    body = {
        "expected_version": validated["row_version"],
        "review_digest": validated["review_digest"],
    }
    applied = await post(client, root + "/commit", body, h=auth, status=200)
    assert applied["state"] == "SUCCEEDED", applied
    replay = await post(client, root + "/commit", body, h=auth, status=200)
    assert replay["id"] == applied["id"] and replay["completed_count"] == 1
    assert len((await client.get(BASE + "/parties", headers=headers())).json()["items"]) == 1
    # The import creates the party's account with it; the replay did not add a second one.
    [imported] = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    ledgers = await party_accounts(client, imported["id"])
    assert [(row["code"], row["party_role"], row["status"]) for row in ledgers] == [
        ("IMPORT", "CUSTOMER", "ACTIVE")
    ]
    attempts = await client.get(BASE + root + "/history/attempts", headers=headers())
    assert attempts.status_code == 200, attempts.text
    assert len(attempts.json()["items"]) == 2
    artifacts = (await client.get(BASE + root + "/history/artifacts", headers=headers())).json()[
        "items"
    ]
    options = {"kind": "SOURCE", "artifact_id": artifacts[0]["id"]}
    ticket = await post(client, root + "/download-ticket", options, status=200)
    downloaded = await client.post(
        BASE + root + "/download", json=options | {"token": ticket["token"]}, headers=headers()
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == base64.b64decode(file["content_base64"])
    for fmt in ("CSV", "TSV", "XLSX"):
        options = {"kind": "RESULT", "format": fmt}
        ticket = await post(client, root + "/download-ticket", options, status=200)
        downloaded = await client.post(
            BASE + root + "/download", json=options | {"token": ticket["token"]}, headers=headers()
        )
        assert downloaded.status_code == 200 and downloaded.content
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ImportChangeSetEffect.id))) == 1
            assert await db.scalar(select(func.count(ImportJobAttempt.id))) == 2


async def test_validation_issues_revision_and_drift(client: httpx.AsyncClient) -> None:
    await prepare(client)
    job = await stage(client, source(legal_name=""))
    root = "/import-jobs/" + job["id"]
    invalid = await post(client, root + "/validate", {"expected_version": 1}, status=200)
    assert invalid["state"] == "INVALID" and invalid["review_digest"] is None
    options = {"kind": "RESULT"}
    ticket = await post(client, root + "/download-ticket", options, status=200)
    report = await client.post(
        BASE + root + "/download", json=options | {"token": ticket["token"]}, headers=headers()
    )
    assert (
        report.status_code == 200 and "legal_name" in report.text and "constraints" in report.text
    )
    revised = await post(
        client,
        root + "/revisions",
        {"expected_version": invalid["row_version"], "files": [source()]},
        status=200,
    )
    assert revised["revision"] == 2
    valid = await post(
        client, root + "/validate", {"expected_version": revised["row_version"]}, status=200
    )
    assert valid["state"] == "READY"
    await new_party(client, code="OTHER", role="CUSTOMER", name="Other", legal_name="Other Limited")
    rejected = await client.post(
        BASE + root + "/commit",
        json={"expected_version": valid["row_version"], "review_digest": valid["review_digest"]},
        headers=headers(),
    )
    assert rejected.status_code == 409, rejected.text


async def test_import_scope_permissions_and_download_revocation(client: httpx.AsyncClient) -> None:
    await prepare(client)
    missing = await client.get(BASE + "/import-jobs")
    assert missing.status_code == 401
    denied = await client.get(BASE + "/import-jobs", headers=headers(permissions=set()))
    assert denied.status_code == 403
    job = await stage(client)
    other = await client.get(f"/v1/companies/{uuid7()}/import-jobs/{job['id']}", headers=headers())
    assert other.status_code in {401, 403}
    other_actor = await client.get(
        BASE + "/import-jobs/" + job["id"], headers=headers(user=uuid7())
    )
    assert other_actor.status_code == 403
    root = "/import-jobs/" + job["id"]
    ticket = await post(client, root + "/download-ticket", {"kind": "NORMALIZED"}, status=200)
    policy = {
        "entity_type": "accounting.party",
        "field_key": "legal_name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    revoked = await client.post(
        BASE + root + "/download",
        json={"kind": "NORMALIZED", "token": ticket["token"]},
        headers=headers(policies=[policy]),
    )
    assert revoked.status_code == 403, revoked.text


@pytest.mark.parametrize("parameters", [{"resource": "party"}, {}])
async def test_template_replay_and_saved_snapshot_recheck_current_fields(
    client: httpx.AsyncClient, parameters: dict[str, str]
) -> None:
    await prepare(client)
    body = {"definition": "parties", "parameters": parameters}
    auth = headers()
    template = await post(client, "/import-templates", body, h=auth)
    policy = {
        "entity_type": "accounting.party",
        "field_key": "legal_name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    revoked = headers(policies=[policy], key=auth["Idempotency-Key"])
    replay = await client.post(BASE + "/import-templates", json=body, headers=revoked)
    assert replay.status_code == 403, replay.text
    saved = await client.get(BASE + "/import-templates/" + template["id"], headers=revoked)
    assert saved.status_code == 403, saved.text


async def test_customer_supplier_children_and_activation_share_one_native_aggregate(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    # A bare party row can no longer be created (a party always arrives with a role and its
    # account), so the identity exists first, with its one "other" role and that role's account.
    # The job then adds the two commercial roles and activates them in one native aggregate; each
    # activation creates that role's account.
    owner = await new_party(
        client, code="BOTH", role="OTHER", name="Both", legal_name="Both Limited"
    )
    template = await post(client, "/import-templates", {"definition": "parties"})
    roles = []
    for role in ("CUSTOMER", "SUPPLIER"):
        key = role.lower()
        roles.append(
            [
                key,
                "company",
                "party_role",
                "CREATE",
                "",
                "",
                "",
                "",
                "",
                "",
                json.dumps({"party_id": owner["id"], "role": role}),
            ]
        )
        roles.append(
            [key + "_active", "company", "party_role", "ACTIVATE", "", "", key, "id", "", "", "{}"]
        )
    raw = document("TSV", [("Records", [*CONTROLS, "_payload"], roles)])
    files = [
        {
            "filename": "roles.tsv",
            "format": "TSV",
            "content_base64": base64.b64encode(raw).decode(),
        }
    ]
    job = await post(client, "/import-jobs", {"template_id": template["id"], "files": files})
    path = "/import-jobs/" + job["id"]
    ready = await post(client, path + "/validate", {"expected_version": 1}, status=200)
    assert ready["state"] == "READY", ready
    final = await post(
        client,
        path + "/commit",
        {"expected_version": ready["row_version"], "review_digest": ready["review_digest"]},
        status=200,
    )
    assert final["state"] == "SUCCEEDED" and final["completed_count"] == 4
    parties = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    assert len(parties) == 1 and parties[0]["status"] == "ACTIVE"
    roles = (await client.get(BASE + "/party-roles", headers=headers())).json()["items"]
    assert {role["role"] for role in roles} == {"OTHER", "CUSTOMER", "SUPPLIER"}
    assert all(role["status"] == "ACTIVE" for role in roles)
    # Exactly one active account per account role, the two new ones told apart from the party's
    # first by role.
    ledgers = await party_accounts(client, owner["id"])
    assert [(row["code"], row["party_role"], row["status"]) for row in ledgers] == [
        ("BOTH", "OTHER", "ACTIVE"),
        ("BOTH-CUST", "CUSTOMER", "ACTIVE"),
        ("BOTH-SUPP", "SUPPLIER", "ACTIVE"),
    ]


@pytest.mark.parametrize("resource,role", [("supplier", "SUPPLIER"), ("customer", "CUSTOMER")])
async def test_ready_party_import_activates_identity_and_role_atomically(
    client: httpx.AsyncClient, resource: str, role: str
) -> None:
    await prepare(client)
    template = await post(
        client,
        "/import-templates",
        {"definition": "parties", "parameters": {"resource": resource, "role": role}},
    )
    assert set(template["snapshot"]["schemas"]) == {resource + ":CREATE"}
    file = source(resource=resource)
    staged = await post(client, "/import-jobs", {"template_id": template["id"], "files": [file]})
    root = "/import-jobs/" + staged["id"]
    ready = await post(client, root + "/validate", {"expected_version": 1}, status=200)
    assert ready["state"] == "READY", ready
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    auth = headers()
    body = {"expected_version": ready["row_version"], "review_digest": ready["review_digest"]}
    applied = await post(client, root + "/commit", body, h=auth, status=200)
    assert applied["state"] == "SUCCEEDED" and applied["completed_count"] == 1
    assert (await post(client, root + "/commit", body, h=auth, status=200))["id"] == applied["id"]
    parties = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    roles = (await client.get(BASE + "/party-roles", headers=headers())).json()["items"]
    assert len(parties) == len(roles) == 1
    assert parties[0]["status"] == roles[0]["status"] == "ACTIVE"
    assert roles[0]["party_id"] == parties[0]["id"] and roles[0]["role"] == role
    # The ready import always creates the party's account, here with no opening columns.
    [ledger] = await party_accounts(client, parties[0]["id"])
    assert (ledger["kind"], ledger["party_role"], ledger["status"]) == ("PARTY", role, "ACTIVE")
    assert ledger["code"] == "IMPORT"


async def test_ready_supplier_import_rolls_back_identity_if_role_activation_is_denied(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    policy = {
        "entity_type": "accounting.party_role",
        "field_key": "status",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    auth = headers(policies=[policy])
    template = await post(
        client,
        "/import-templates",
        {"definition": "parties", "parameters": {"resource": "supplier", "role": "SUPPLIER"}},
        h=auth,
    )
    file = source(resource="supplier")
    staged = await post(
        client,
        "/import-jobs",
        {"template_id": template["id"], "files": [file]},
        h=headers(policies=[policy]),
    )
    invalid = await post(
        client,
        "/import-jobs/" + staged["id"] + "/validate",
        {"expected_version": 1},
        h=headers(policies=[policy]),
        status=200,
    )
    assert invalid["state"] == "INVALID"
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    assert (await client.get(BASE + "/party-roles", headers=headers())).json()["items"] == []
    # No party account was left behind either (the chart holds only its business accounts).
    assert not [
        row
        for row in (await client.get(BASE + "/accounts", headers=headers())).json()["items"]
        if row["kind"] == "PARTY"
    ]


async def test_a_plain_party_row_cannot_be_created_by_import(client: httpx.AsyncClient) -> None:
    """A party only ever arrives with its role and ledger account: the ready import does that."""
    await prepare(client)
    template = await post(
        client, "/import-templates", {"definition": "parties", "parameters": {"resource": "party"}}
    )
    # The plain party resource keeps only update, activate and deactivate.
    assert set(template["snapshot"]["schemas"]) == {
        "party:UPDATE",
        "party:ACTIVATE",
        "party:DEACTIVATE",
    }
    # A file asking for a party CREATE is not a file of the configured template, so no job exists
    # that could ever be validated or committed.
    await post(
        client,
        "/import-jobs",
        {"template_id": template["id"], "files": [source(resource="party")]},
        status=422,
    )
    assert (await client.get(BASE + "/import-jobs", headers=headers())).json()["items"] == []
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    assert (await client.get(BASE + "/party-roles", headers=headers())).json()["items"] == []


async def test_supplier_policy_template_limits_the_declared_role(client: httpx.AsyncClient) -> None:
    await prepare(client)
    result = await post(
        client,
        "/import-templates",
        {
            "definition": "parties",
            "parameters": {"resource": "party_credit_policy", "role": "SUPPLIER"},
        },
    )
    assert result["snapshot"]["schemas"]["party_credit_policy:CREATE"]["properties"]["role"][
        "enum"
    ] == ["SUPPLIER"]
