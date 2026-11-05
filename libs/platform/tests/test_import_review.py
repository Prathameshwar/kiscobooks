"""Regression coverage for retained attempt exports and editable workbook templates."""

import csv
import io
import uuid
import zipfile

import pytest
from sqlalchemy import select

from billing_platform.bulk_files import xml
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.import_contracts import (
    CommitImport,
    DownloadOptions,
    ImportAction,
    ReviseImport,
)
from billing_platform.import_files import template_document
from billing_platform.import_models import ImportJobAttempt
from billing_platform.import_reads import download
from tests.test_import_framework import Adapter, file, invoke, row, stage
from tests.test_import_tabular import snapshot


async def test_older_attempt_download_uses_its_own_revision_and_authority(factory, tenant_a):
    adapter = Adapter(tenant_a)
    with tenant_scope(tenant_a):
        original = await stage(factory, adapter, [row("original", data={"name": ""})])
        checked = await invoke(
            factory, adapter, "validate", ImportAction(expected_version=1), original["id"]
        )
        async with factory() as db:
            attempt = (await db.scalars(select(ImportJobAttempt))).one()
            attempt_id = attempt.id
        await invoke(
            factory,
            adapter,
            "revise",
            ReviseImport(
                expected_version=checked["row_version"], files=[file([row("replacement")])]
            ),
            original["id"],
        )
        unrelated = await stage(factory, adapter, [row("unrelated")])
        async with factory() as db:
            raw, _ = await download(
                db, adapter, uuid.UUID(original["id"]), DownloadOptions(attempt_id=attempt_id)
            )
            report = list(csv.DictReader(io.StringIO(raw.decode()).readlines()[1:]))
            assert report[0]["key"] == "original" and report[0]["status"] == "INVALID"
            with pytest.raises(ValidationFailedError):
                await download(
                    db,
                    adapter,
                    uuid.UUID(original["id"]),
                    DownloadOptions(attempt_id=attempt_id, revision=2),
                )
            with pytest.raises(PermissionDeniedError):
                await download(
                    db, adapter, uuid.UUID(unrelated["id"]), DownloadOptions(attempt_id=attempt_id)
                )

            async def current_read_authority(db, batch):
                if any(record.key == "original" for record in batch.records):
                    raise PermissionDeniedError("Original fields are now protected")

            adapter.readable = current_read_authority
            with pytest.raises(PermissionDeniedError, match="now protected"):
                await download(
                    db, adapter, uuid.UUID(original["id"]), DownloadOptions(attempt_id=attempt_id)
                )


def test_excel_template_formats_new_input_cells_as_text():
    raw = template_document(snapshot(), "ready_thing", "CREATE", "XLSX")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        worksheet = xml(archive.read("xl/worksheets/sheet1.xml"))
        columns = worksheet.findall("s:cols/s:col", ns)
        assert columns, "Blank template columns need Text formatting to preserve codes and decimals"
        styles = xml(archive.read("xl/styles.xml")).findall("s:cellXfs/s:xf", ns)
        for column in columns:
            assert styles[int(column.attrib["style"])].attrib["numFmtId"] == "49"
        assert int(columns[0].attrib["min"]) == 1
        assert int(columns[-1].attrib["max"]) == 2


async def test_old_failed_results_do_not_borrow_a_later_corrected_product(factory, tenant_a):
    class ReportingAdapter(Adapter):
        async def snapshot(self, db, definition, parameters):
            return await super().snapshot(db, definition, parameters) | {"result_fields": ["name"]}

        async def execute(self, db, record, mode, results, key):
            return await super().execute(db, record, mode, results, key) | {
                "name": record.data["name"].upper()
            }

    adapter = ReportingAdapter(tenant_a)
    with tenant_scope(tenant_a):
        job = await stage(factory, adapter, [row("product", data={"name": "Original product"})])
        ready = await invoke(
            factory, adapter, "validate", ImportAction(expected_version=1), job["id"]
        )
        adapter.failing = {"product"}
        failed = await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(
                expected_version=ready["row_version"], review_digest=ready["review_digest"]
            ),
            job["id"],
        )
        async with factory() as db:
            failed_attempt = await db.scalar(
                select(ImportJobAttempt.id).where(ImportJobAttempt.phase == "IMPORT")
            )
        adapter.failing = set()
        corrected = await invoke(
            factory,
            adapter,
            "revise",
            ReviseImport(
                expected_version=failed["row_version"],
                files=[file([row("product", data={"name": "Corrected product"})])],
            ),
            job["id"],
        )
        ready = await invoke(
            factory,
            adapter,
            "validate",
            ImportAction(expected_version=corrected["row_version"]),
            job["id"],
        )
        await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(
                expected_version=ready["row_version"], review_digest=ready["review_digest"]
            ),
            job["id"],
        )
        async with factory() as db:
            raw, _ = await download(
                db, adapter, uuid.UUID(job["id"]), DownloadOptions(attempt_id=failed_attempt)
            )
        report = list(csv.DictReader(io.StringIO(raw.decode()).readlines()[1:]))
        assert report[0]["status"] == "FAILED"
        assert report[0]["name"] == "Original product"
        async with factory() as db:
            raw, _ = await download(db, adapter, uuid.UUID(job["id"]), DownloadOptions())
        current = list(csv.DictReader(io.StringIO(raw.decode()).readlines()[1:]))
        assert current[0]["status"] == "APPLIED"
        assert current[0]["name"] == "CORRECTED PRODUCT"
