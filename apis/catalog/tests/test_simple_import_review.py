"""Simple-mode history keeps the original file and diagnostics after correction."""

import csv
import io

import pytest

from tests.test_master_imports import command
from tests.test_simple_product_creation import starter
from tests.test_simple_product_import import simple_source, stage_rows, template, validate

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_simple_historical_result_download_after_replacing_source(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a)
    configured = await template(client, root, auth)
    staged = await stage_rows(
        client, root, auth, configured, [{"name": "Original product", "base_unit": "UNKNOWN"}]
    )
    invalid = await validate(client, root, auth, staged)
    assert invalid["state"] == "INVALID"
    path = root + "/import-jobs/" + staged["id"]
    history = await client.get(path + "/history/attempts", headers=auth)
    attempt = history.json()["items"][0]["id"]
    replacement = simple_source([{"name": "Replacement product", "base_unit": "UNKNOWN"}])
    replacement["filename"] = "replacement.csv"
    await command(
        client,
        root,
        auth,
        "/import-jobs/" + staged["id"] + "/revisions",
        {"expected_version": invalid["row_version"], "files": [replacement]},
    )
    options = {"kind": "RESULT", "format": "CSV", "attempt_id": attempt}
    ticket = await client.post(path + "/download-ticket", headers=auth, json=options)
    assert ticket.status_code == 200, ticket.text
    result = await client.post(
        path + "/download",
        headers=auth,
        json=options | {"token": ticket.json()["token"]},
    )
    assert result.status_code == 200, result.text
    rows = list(csv.DictReader(io.StringIO(result.text).readlines()[1:]))
    assert rows[0]["product_name"] == "Original product"
    assert rows[0]["file"] == "products.csv"
    assert rows[0]["field"] == "base_unit" and rows[0]["status"] == "INVALID"
