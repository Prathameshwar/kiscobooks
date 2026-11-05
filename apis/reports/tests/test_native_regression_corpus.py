"""Replay established financial regression scenarios through the native component plans.

Capture the inputs of existing domain scenarios so tax, credit and reversal fixtures cannot
drift into a second financial model. Their original assertions still run before native replay.
"""

import uuid

import pytest
from billing_platform.db import tenant_scope
from conftest import TENANT
from test_native_ledger import prepared

from reports.domain.reporting.contracts import fingerprint
from reports.domain.statements import calculate
from reports.queries.native_bank import execute as bank
from reports.queries.native_context import NativeContext
from reports.queries.native_invoices import execute as invoice


@pytest.mark.parametrize(
    "module_name,scenario",
    [
        (
            "test_invoice_reports",
            "test_tax_register_and_tax_gl_bridge_follow_tax_point_and_posting_dates",
        ),
        (
            "test_invoice_reports",
            "test_purchase_credit_register_distinguishes_pending_and_verified_tax",
        ),
        (
            "test_invoice_reports",
            "test_invoice_component_register_and_gl_bridge_preserve_distinct_grains",
        ),
        (
            "test_money_reports",
            "test_reversed_bank_instrument_covers_original_and_reversal_without_replaying_cash",
        ),
        (
            "test_money_reports",
            "test_receipt_register_splits_modes_without_multiplying_receipt_and_filters_party",
        ),
    ],
)
async def test_native_replays_nonempty_tax_credit_split_and_reversal_scenarios(
    app,
    monkeypatch,
    module_name,
    scenario,
):
    import importlib

    module = importlib.import_module(module_name)
    captured = {}

    def record(facts, query, coverage):
        # Existing domain tests build sources in varied insertion orders; publication uses
        # the owner's canonical entity/identity order, also used for the parity oracle.
        source = sorted(
            (row.model_copy(deep=True) for row in facts),
            key=lambda row: (row.entity, str(row.source_id)),
        )
        key = fingerprint([row.model_dump(mode="json") for row in source])
        captured.setdefault(key, (source, []))[1].append((query, coverage))
        return calculate(facts, query, coverage)

    monkeypatch.setattr(module, "calculate", record)
    getattr(module, scenario)()
    assert captured
    for source, requests in captured.values():
        # Each scenario state is an independent snapshot, including the synthetic lineage
        # appended by prepared(). Rebuilding it in the same company would correctly reject
        # removal of the prior helper's immutable execution record.
        company = uuid.uuid4()
        instruments = {str(row.source_id) for row in source if row.entity == "bank_instrument"}
        # The legacy tender scenario removes instrument capture. Its old irrelevant event
        # must also be absent for a valid complete owner snapshot.
        source = [
            row
            for row in source
            if row.entity != "bank_instrument_event" or row.data["instrument_id"] in instruments
        ]
        identities, published, _ = await prepared(app, company=company, dataset=(source, {}))
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                context = await NativeContext.load(db, company, identities[2])
                for query, coverage in requests:
                    current = query.model_copy(update={"generation_id": identities[2]})
                    engine = invoice if module_name == "test_invoice_reports" else bank
                    assert await engine(db, context, current, 100000) == calculate(
                        published, current, coverage
                    )
