"""The mandatory per-endpoint matrix applied to every registered resource.

The router generates up to seven endpoints per resource from two facts: whether the resource is
maintained by Accounting setup, and whether it carries a status lifecycle. Deriving the matrix
from those same two facts means a newly registered resource is covered without editing this
file, and a resource that gains a lifecycle is immediately held to the activation contract.

Each test walks every resource inside one database, collecting failures rather than stopping at
the first: parametrizing over 28 resources would rebuild the schema 28 times per behaviour and
cost minutes, and a matrix nobody runs locally protects nothing.
"""

from typing import Any

import httpx
from billing_platform.ids import uuid7

from accounting.resources import BY_NAME, RESOURCES, Resource
from accounting.tasks.commands import READ_ONLY
from tests.conftest import headers
from tests.test_masters import BASE

OTHER_COMPANY = uuid7()
MISSING = uuid7()


# A party is created only with its role and ledger account (`parties/create-with-details`,
# docs/party-ledger-mandatory-plan.md PL-D01), so it has no plain create route to sweep; that its
# plain `POST` is gone is asserted in test_party_ledger_mandatory.py.
NO_PLAIN_CREATE = frozenset({"party"})


def endpoints(spec: Resource) -> list[tuple[str, str]]:
    rows = [("GET", ""), ("GET", "/field-set"), ("GET", f"/{MISSING}")]
    if spec.name not in READ_ONLY:
        rows += [("POST", "")] if spec.name not in NO_PLAIN_CREATE else []
        rows += [("PATCH", f"/{MISSING}")]
        if spec.lifecycle == "status":
            rows += [("POST", f"/{MISSING}/activate"), ("POST", f"/{MISSING}/deactivate")]
    return rows


def body_for(method: str, suffix: str) -> dict[str, Any] | None:
    """Every mutation but create accepts the bare optimistic-concurrency body, which is what
    lets one matrix reach handlers whose create payload is resource-specific."""
    if method == "GET":
        return None
    return {} if suffix == "" else {"expected_version": 1}


async def sweep(
    client: httpx.AsyncClient,
    expected: int,
    *,
    base: str = BASE,
    query: str = "",
    skip_create: bool = False,
    **kwargs: Any,
) -> list[str]:
    """Call every endpoint of every resource and report each status that is not `expected`."""
    problems = []
    for spec in RESOURCES:
        for method, suffix in endpoints(spec):
            if skip_create and (method, suffix) == ("POST", ""):
                continue
            url = f"{base}/{spec.path}{suffix}{query}"
            result = await client.request(method, url, json=body_for(method, suffix), **kwargs)
            if result.status_code != expected:
                problems.append(f"{method} {url} -> {result.status_code}: {result.text[:120]}")
    return problems


async def test_every_endpoint_requires_verified_context(client: httpx.AsyncClient) -> None:
    assert await sweep(client, 401) == []


async def test_every_endpoint_denies_a_missing_permission(client: httpx.AsyncClient) -> None:
    # Create is excluded: FastAPI validates its resource-specific body before the handler runs,
    # so an empty body answers 422 first. Per-resource tests cover create denial with a real body.
    problems = await sweep(client, 403, skip_create=True, headers=headers(permissions=set()))
    assert problems == []


async def test_every_endpoint_rejects_a_foreign_company_path(client: httpx.AsyncClient) -> None:
    """A company context is bound to one company, so a path naming another is refused before any
    permission check or object lookup — the permission key alone never reaches company B."""
    problems = await sweep(client, 401, base=f"/v1/companies/{OTHER_COMPANY}", headers=headers())
    assert problems == []


async def test_unknown_object_is_not_found_on_every_object_endpoint(
    client: httpx.AsyncClient,
) -> None:
    problems = []
    for spec in RESOURCES:
        for method, suffix in endpoints(spec):
            if suffix in {"", "/field-set"}:
                continue
            url = f"{BASE}/{spec.path}{suffix}"
            result = await client.request(
                method, url, json=body_for(method, suffix), headers=headers()
            )
            if result.status_code != 404:
                problems.append(f"{method} {url} -> {result.status_code}: {result.text[:120]}")
    assert problems == []


async def test_every_endpoint_rejects_query_parameters_it_does_not_define(
    client: httpx.AsyncClient,
) -> None:
    problems = await sweep(client, 422, query="?unexpected=1", headers=headers())
    assert problems == []


async def test_list_rejects_a_repeated_query_parameter(client: httpx.AsyncClient) -> None:
    problems = []
    for spec in RESOURCES:
        result = await client.get(f"{BASE}/{spec.path}?code=A&code=B", headers=headers())
        if result.status_code != 422:
            problems.append(f"{spec.path} -> {result.status_code}")
    assert problems == []


async def test_every_resource_lists_leanly_and_describes_its_field_set(
    client: httpx.AsyncClient,
) -> None:
    problems = []
    for spec in RESOURCES:
        page = await client.get(f"{BASE}/{spec.path}", headers=headers())
        if page.status_code != 200:
            problems.append(f"{spec.path} list -> {page.status_code}: {page.text[:120]}")
            continue
        envelope = page.json()
        if envelope["items"] or envelope["page"] != {
            "limit": 50,
            "has_more": False,
            "next_cursor": None,
        }:
            problems.append(f"{spec.path} list envelope -> {envelope}")

        described = await client.get(f"{BASE}/{spec.path}/field-set", headers=headers())
        if described.status_code != 200:
            problems.append(f"{spec.path} field-set -> {described.status_code}")
            continue
        body = described.json()
        if body["resource"] != spec.path:
            problems.append(f"{spec.path} field-set names {body['resource']}")
        if {row["key"] for row in body["fields"]} != set(spec.create.model_fields):
            problems.append(f"{spec.path} field-set keys diverge from its create schema")
        for row in body["fields"]:
            # A field accepted on create but absent from the detail schema is write-only by
            # design; the raw bank account number is the only one, and it must never read back.
            if row["readable"] is not (row["key"] in spec.detail.model_fields):
                problems.append(f"{spec.path}.{row['key']} readable={row['readable']}")
            if row["writable"] is not (spec.name not in READ_ONLY) or not row["visible"]:
                problems.append(f"{spec.path}.{row['key']} has incorrect editability or visibility")
            reference = spec.references.get(row["key"])
            expected = BY_NAME[reference].path if reference else None
            if row["reference"] != expected:
                problems.append(f"{spec.path}.{row['key']} references {row['reference']}")
    assert problems == []


def test_only_the_raw_bank_account_number_is_write_only() -> None:
    """§5.10: the number is tokenized into ciphertext plus last four, so no read path may
    return it. Any other create-only field would be an unintended one-way write."""
    write_only = {
        (spec.path, field)
        for spec in RESOURCES
        for field in set(spec.create.model_fields) - set(spec.detail.model_fields)
    }
    assert write_only == {("party-bank-accounts", "account_number")}
