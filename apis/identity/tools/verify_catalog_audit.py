"""Catalog adapter for the shared disposable gateway/broker/browser audit proof."""

import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


async def prepare(database_url, tenant, company, user, request):
    import asyncio

    from verify_accounting_audit import execute

    version = 1

    async def refresh():
        nonlocal version
        version += 1
        result = await asyncio.to_thread(
            execute,
            [str(ROOT / "apis/catalog/.venv/Scripts/python.exe"), "tools/seed_audit_proof.py"],
            cwd=ROOT / "apis/catalog",
            env=dict(
                os.environ,
                PYTHONPATH=".",
                CATALOG_DATABASE_URL=database_url,
                CATALOG_PROOF_TENANT=str(tenant),
                CATALOG_PROOF_COMPANY=str(company),
                CATALOG_PROOF_USER=str(user),
                CATALOG_PROOF_VERSION=str(version),
            ),
        )
        assert result.returncode == 0, "Catalog fixture failed: " + result.stderr[-1500:]

    await refresh()
    base = f"/catalog/v1/companies/{company}"
    idem = {"Idempotency-Key": str(uuid.uuid4())}
    body = {
        "code": "PROOF",
        "name": "Private person",
        "symbol": "ea",
        "dimension": "COUNT",
        "decimal_places": 0,
        "quantity_increment": "1",
    }
    row = (await request("POST", base + "/units", body, 201, idem)).json()
    await request("POST", base + "/units", body, 201, idem)
    updated = await request(
        "PATCH",
        base + "/units/" + row["id"],
        {"quantity_increment": "2", "expected_version": row["row_version"]},
        extra={"Idempotency-Key": str(uuid.uuid4()), "X-Trace-Id": "a" * 32},
    )
    assert updated.json()["quantity_increment"] == "2.0000"
    job = (
        await request(
            "POST",
            base + "/bulk-jobs",
            {
                "format": "JSON",
                "records": [
                    {
                        "key": "row1",
                        "change_set": "row1",
                        "resource": "unit_of_measure",
                        "data": body | {"code": "SECOND"},
                    }
                ],
            },
            202,
            {"Idempotency-Key": str(uuid.uuid4())},
        )
    ).json()

    async def download():
        await refresh()
        ticket = (await request("GET", base + "/bulk-jobs/" + job["id"] + "/report-ticket")).json()
        await request("GET", "/catalog" + ticket["download_path"])

    await download()
    return download


if __name__ == "__main__":
    os.environ["AUDIT_PROOF_SERVICE"] = "catalog"
    from verify_accounting_audit import main

    main()
