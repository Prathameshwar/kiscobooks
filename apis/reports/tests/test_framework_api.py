import uuid

import pytest
from conftest import COMPANY, PERMISSIONS, headers

from reports.tasks.report_catalog import catalog


@pytest.fixture
def v2():
    return f"/v2/companies/{COMPANY}/report-definitions"


async def test_discovery_has_typed_parameters_and_only_ready_capabilities(client, v2):
    response = await client.get(v2, headers=headers())
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    codes = [row["definition"]["code"] for row in items]
    assert len(codes) == len(set(codes))
    # This company context has no GST registrations; return definitions require them.
    assert set(codes) == {code for code, _version in catalog().reports} - {"GSTR1", "GSTR3B"}
    assert all(row["formats"] == [] and not row["run_enabled"] for row in items)
    item = await client.get(v2 + "/TRIAL_BALANCE", headers=headers())
    assert item.status_code == 200
    assert "account_id" not in item.json()["parameter_schema"]["properties"]
    assert (await client.get(v2 + "/UNKNOWN", headers=headers())).status_code == 404
    assert (await client.get(v2 + "/TRIAL_BALANCE?version=0", headers=headers())).status_code == 422


async def test_definition_validation_is_canonical_and_rejects_unused_filters(client, v2):
    body = {"parameters": {"date_to": "2026-04-30", "date_from": "2026-04-01"}}
    response = await client.post(v2 + "/TRIAL_BALANCE/validate", headers=headers(), json=body)
    assert response.status_code == 200, response.text
    repeated = await client.post(v2 + "/TRIAL_BALANCE/validate", headers=headers(), json=body)
    assert repeated.json() == response.json()
    body["parameters"]["account_id"] = str(uuid.uuid4())
    invalid = await client.post(v2 + "/TRIAL_BALANCE/validate", headers=headers(), json=body)
    assert invalid.status_code == 422
    assert "error" in invalid.json()


async def test_corrected_definition_defaults_to_latest_and_rejects_retired_version(client, v2):
    for suffix in ("", "/field-set"):
        response = await client.get(v2 + "/ACCOUNT_SUMMARY" + suffix, headers=headers())
        assert response.status_code == 200, response.text
        value = response.json()
        assert value.get("version", value.get("definition", {}).get("version")) == 6
    body = {"parameters": {"date_from": "2026-06-01", "date_to": "2026-06-30"}}
    accepted = await client.post(v2 + "/ACCOUNT_SUMMARY/validate", headers=headers(), json=body)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["version"] == 6
    retired = await client.post(
        v2 + "/ACCOUNT_SUMMARY/validate", headers=headers(), json=body | {"version": 2}
    )
    assert retired.status_code == 404


async def test_discovery_and_validation_require_current_company_and_source_authority(client, v2):
    for path, method, arguments in [
        (v2, "get", {}),
        (v2 + "/ACCOUNT_LEDGER", "get", {}),
        (v2 + "/ACCOUNT_LEDGER/validate", "post", {"json": {}}),
    ]:
        call = getattr(client, method)
        assert (await call(path, **arguments)).status_code == 401
        assert (
            await call(path, headers=headers(permissions=frozenset({"report.read"})), **arguments)
        ).status_code == 403
        other = uuid.uuid4()
        wrong = path.replace(str(COMPANY), str(other))
        assert (await call(wrong, headers=headers(), **arguments)).status_code == 401
        foreign_scope = headers(company=other)
        actor_headers = headers()
        for key in ("X-Actor-Context", "X-Actor-Signature"):
            foreign_scope[key] = actor_headers[key]
        assert (await call(wrong, headers=foreign_scope, **arguments)).status_code == 403
        denied = headers(
            policies=[
                {"access": "read", "effect": "deny", "entity_type": "account", "field": "name"}
            ]
        )
        assert (await call(path, headers=denied, **arguments)).status_code == 403
    restricted = headers(permissions=PERMISSIONS - {"accounting.statement.read"})
    visible = (await client.get(v2, headers=restricted)).json()["items"]
    assert "BANK_RECONCILIATION_EVIDENCE" not in {row["definition"]["code"] for row in visible}
    assert (
        await client.get(v2 + "/BANK_RECONCILIATION_EVIDENCE", headers=restricted)
    ).status_code == 403
