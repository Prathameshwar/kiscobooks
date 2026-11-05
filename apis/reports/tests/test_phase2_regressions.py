import uuid

from conftest import PERMISSIONS, headers
from fixtures import dataset, manifest, source

from reports.domain.reconcile import reconcile


def test_finalized_zero_opening_has_no_synthetic_journal():
    items = [
        *dataset(),
        source(
            "opening_batch",
            uuid.uuid4(),
            {
                "status": "FINALIZED",
                "posting_date": "2026-04-01",
                "journal_id": None,
                "replacement_of_id": None,
                "finalized_at": "2026-04-01T00:00:00Z",
            },
        ),
    ]
    _, _, evidence = reconcile(items, manifest(items).control)
    assert evidence["differences"] == []


async def test_complete_financial_source_controls_require_ledger_read(client, prefix):
    result = await client.get(
        prefix + "/report-definitions", headers=headers(permissions=PERMISSIONS - {"ledger.read"})
    )
    assert result.status_code == 403
