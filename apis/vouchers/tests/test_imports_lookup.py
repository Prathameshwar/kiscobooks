"""Signed Accounting code lookup: exact request binding, response verification, scope."""

import json
import secrets
import uuid

import httpx
import pytest
from billing_platform.errors import AuthenticationRequiredError, ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    authorize_snapshot,
    response_headers,
)
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr

from vouchers.schemas.owners import Owner
from vouchers.tasks.master_lookup import lookup, owner_for

TENANT, COMPANY = uuid7(), uuid7()


def credentials(secret: str) -> tuple[Owner, dict[str, SnapshotCredential]]:
    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    owner = Owner(
        owner="accounting", origin="http://127.0.0.1", key_id="lookup",
        secret=SecretStr(secret), scopes=(scope,),
    )
    return owner, {"lookup": SnapshotCredential(secret=SecretStr(secret), scopes=(scope,))}


def server(store: dict[str, SnapshotCredential], result: dict, *, tamper: bool = False):
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        credential, framed, key_id = authorize_snapshot(
            store, owner="accounting", tenant_id=TENANT, company_id=COMPANY,
            headers=request.headers, method=request.method, path=request.url.path,
            query=request.url.query.decode(), body=request.content,
        )
        seen.append(json.loads(request.content))
        body = canonical_json(result)
        signed = response_headers(
            credential, owner="accounting", key_id=key_id, request_bytes=framed, body=body
        )
        return httpx.Response(200, content=body + (b" " if tamper else b""), headers=signed)

    return handle, seen


def payload(party: uuid.UUID, account: uuid.UUID, extra_code: str | None = None) -> dict:
    return {
        "parties": [{"code": "SUP-1", "source_id": str(party), "source_version": 2,
                     "status": "ACTIVE"}],
        "registrations": [{"registration_number": "27ABCDE1234F1Z5", "party_id": str(party),
                           "valid_from": "2020-04-01", "valid_to": None}],
        "party_accounts": [
            {"code": "SUP-1-L", "source_id": str(account), "source_version": 1,
             "status": "ACTIVE", "party_id": str(party), "party_role": "SUPPLIER",
             "currency": None},
            {"code": "CUS-L", "source_id": str(uuid7()), "source_version": 1,
             "status": "ACTIVE", "party_id": str(party), "party_role": "CUSTOMER",
             "currency": None},
        ],
        "accounts": [{"code": extra_code or "EXP", "source_id": str(account),
                      "source_version": 4, "status": "ACTIVE", "kind": "GENERAL",
                      "currency": None}],
    }


@pytest.mark.parametrize("open_start", [False, True])
async def test_lookup_signs_request_and_maps_supplier_ledgers(open_start):
    owner, store = credentials(secrets.token_hex(32))
    party, account = uuid7(), uuid7()
    result = payload(party, account)
    if open_start:
        result["registrations"][0]["valid_from"] = None
    handle, seen = server(store, result)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        found = await lookup(
            client, owner, TENANT, COMPANY, party_codes={"SUP-1"},
            party_gstins={"27ABCDE1234F1Z5"}, account_codes={"EXP"},
        )
    assert seen == [{"account_codes": ["EXP"], "bills": [], "invoices": [],
                     "party_codes": ["SUP-1"], "party_gstins": ["27ABCDE1234F1Z5"]}]
    assert found.party("SUP-1").source_version == 2
    assert found.gstin_parties["27ABCDE1234F1Z5"] == (party,)
    # Every party ledger is kept with its role; each voucher kind picks its own role.
    assert [code for code, _ in found.party_ledgers[party]] == ["SUP-1-L", "CUS-L"]
    assert sorted(str(role) for role in found.ledger_roles.values()) == ["CUSTOMER", "SUPPLIER"]
    assert found.account("EXP").source_version == 4


async def test_lookup_rejects_tampered_unrequested_or_unsigned_responses():
    owner, store = credentials(secrets.token_hex(32))
    party, account = uuid7(), uuid7()
    for result, tamper in ((payload(party, account), True),
                           (payload(party, account, "UNASKED"), False)):
        handle, _ = server(store, result, tamper=tamper)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(AuthenticationRequiredError):
                await lookup(client, owner, TENANT, COMPANY, party_codes={"SUP-1"},
                             party_gstins=set(), account_codes={"EXP"})
    other, _ = credentials(secrets.token_hex(32))
    handle, _ = server(store, payload(party, account))

    def guarded(request: httpx.Request) -> httpx.Response:
        try:
            return handle(request)
        except AuthenticationRequiredError:
            return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(guarded)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await lookup(client, other, TENANT, COMPANY, party_codes={"SUP-1"},
                         party_gstins=set(), account_codes=set())


def test_owner_must_be_accounting_and_scoped_to_the_company():
    owner, _ = credentials(secrets.token_hex(32))
    assert owner_for(owner, TENANT, COMPANY) is owner
    for candidate, company in ((None, COMPANY), (owner, uuid7()),
                               (owner.model_copy(update={"owner": "catalog"}), COMPANY)):
        with pytest.raises(ConflictError, match="lookup owner"):
            owner_for(candidate, TENANT, company)


async def test_lookup_matches_owner_collation_and_batches_large_requests():
    owner, store = credentials(secrets.token_hex(32))
    party, account = uuid7(), uuid7()
    codes = {f"EXP-{n}" for n in range(1200)}
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        credential, framed, key_id = authorize_snapshot(
            store, owner="accounting", tenant_id=TENANT, company_id=COMPANY,
            headers=request.headers, method=request.method, path=request.url.path,
            query=request.url.query.decode(), body=request.content,
        )
        asked = json.loads(request.content)
        calls.append(asked)
        assert len(asked["account_codes"]) <= 500
        result = payload(party, account)
        # A case-insensitive owner collation returns its canonical code.
        result["parties"] = result["parties"] if asked["party_codes"] else []
        result["registrations"] = []
        result["party_accounts"] = result["party_accounts"] if asked["party_codes"] else []
        result["accounts"] = [
            {"code": code.upper(), "source_id": str(uuid7()), "source_version": 1,
             "status": "ACTIVE", "kind": "GENERAL", "currency": None}
            for code in asked["account_codes"]
        ]
        body = canonical_json(result)
        return httpx.Response(200, content=body, headers=response_headers(
            credential, owner="accounting", key_id=key_id, request_bytes=framed, body=body
        ))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        found = await lookup(
            client, owner, TENANT, COMPANY, party_codes={"sup-1"}, party_gstins=set(),
            account_codes={code.lower() for code in codes},
        )
    assert len(calls) == 3
    assert found.party("sup-1") is not None and found.party("SUP-1") is not None
    assert found.account("exp-7") is not None and len(found.accounts) == 1200
