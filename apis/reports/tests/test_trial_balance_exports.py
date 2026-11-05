"""Actual artifacts must preserve complete totals and the chosen frozen hierarchy."""

import csv
import io
import uuid
import zipfile
from decimal import Decimal

import pytest
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_dataset
from fixtures import source
from test_framework_execution import proof
from test_trial_balance_api import completed

from reports.tasks.framework_worker import process


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
@pytest.mark.parametrize("view", ["default", "detailed"])
async def test_both_trial_balance_layouts_produce_real_complete_artifacts(
    app, client, tmp_path, format_name, view
):
    dataset = None
    if format_name == "HTML":
        facts, identities = financial_dataset()
        amounts = {
            "amount",
            "base_amount",
            "total_debit",
            "total_credit",
            "debt_base_amount",
            "credit_base_amount",
        }
        dataset = (
            [
                source(
                    row.entity,
                    row.source_id,
                    {
                        key: format(Decimal(value) * Decimal("0.00002"), ".4f")
                        if key in amounts
                        else value
                        for key, value in row.data.items()
                    },
                )
                for row in facts
            ],
            identities,
        )
    target, _ = await completed(app, client, dataset=dataset)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    body = {
        "format": format_name,
        "view": view,
        "trial_balance": {"hierarchy": "ALL", "show_zero": True},
    }
    key = headers()
    response = await client.post(target + "/exports", headers=key, json=body)
    assert response.status_code == 202, response.text
    assert (await client.post(target + "/exports", headers=key, json=body)).json()[
        "id"
    ] == response.json()["id"]

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    export = f"/v2/companies/{COMPANY}/report-exports/{response.json()['id']}"
    status = await client.get(export, headers=headers())
    assert status.json()["status"] == "COMPLETE", status.text
    token = await client.get(export + "/download-token", headers=headers())
    assert token.status_code == 200, token.text
    output = await client.get(
        export + "/download", headers=headers(), params={"token": token.json()["token"]}
    )
    assert output.status_code == 200, output.text
    total = (await client.get(target + "/hierarchy", headers=headers())).json()["summary"]
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        control = rows[-1]
        accounts = [row for row in rows if row["Row type"] == "ACCOUNT"]
        assert len(accounts) == total["account_count"]
        debit = "Debit" if view == "default" else "Closing Dr"
        credit = "Credit" if view == "default" else "Closing Cr"
        assert Decimal(control[debit]) == Decimal(total["closing_debit"])
        assert Decimal(control[credit]) == Decimal(total["closing_credit"])
        assert sum(Decimal(row[debit]) for row in accounts) == Decimal(control[debit])
        assert sum(Decimal(row[credit]) for row in accounts) == Decimal(control[credit])
        assert any(row["Row type"] == "HEAD" for row in rows)
    else:
        if format_name == "XLSX":
            with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
                text = archive.read("xl/worksheets/sheet1.xml").decode()
            assert 'outlineLevel="' in text
        elif format_name == "HTML":
            text = output.text
            assert "default-src" in text and "<script" not in text
            assert "Display rounding" in text
            assert total["closing_debit"] == total["closing_credit"] == "0.0060"
            assert total["display_residual"]["closing_debit"] == "0.0100"
        else:
            from pypdf import PdfReader

            document = PdfReader(io.BytesIO(output.content))
            text = "".join(page.extract_text() for page in document.pages)
            if view == "detailed":
                assert document.pages[0].mediabox.width > document.pages[0].mediabox.height
        assert "grand total" in text.lower() and "cash" in text.lower()
        if view == "detailed":
            assert "Opening" in text and "Period" in text and "Closing" in text


async def test_trial_export_rejects_foreign_expansion_and_current_depth_does_not_change_totals(
    app, client, tmp_path
):
    target, _ = await completed(app, client)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    for changes in (
        {"expanded": ["group:" + str(uuid.uuid4())]},
        {"period": "COMPARATIVE"},
        {"level": "OTHER"},
        {"expanded": ["group:" + str(uuid.uuid4())], "collapsed": ["bad"]},
    ):
        rejected = await client.post(
            target + "/exports", headers=headers(), json={"format": "CSV", "trial_balance": changes}
        )
        assert rejected.status_code == 422, rejected.text
    response = await client.post(
        target + "/exports",
        headers=headers(),
        json={"format": "CSV", "trial_balance": {"level": "HEADS"}},
    )
    assert response.status_code == 202, response.text

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    export = f"/v2/companies/{COMPANY}/report-exports/{response.json()['id']}"
    token = (await client.get(export + "/download-token", headers=headers())).json()["token"]
    output = await client.get(export + "/download", headers=headers(), params={"token": token})
    rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
    assert {row["Row type"] for row in rows} == {"HEAD", "TRIAL_BALANCE_CONTROL"}
    total = (await client.get(target + "/hierarchy", headers=headers())).json()["summary"]
    assert Decimal(rows[-1]["Debit"]) == Decimal(total["closing_debit"])


def test_trial_presentation_rejects_oversized_raw_expansion_before_deduplication():
    from reports.schemas.trial_balance_options import TrialPresentation

    with pytest.raises(ValueError):
        TrialPresentation(expanded=["group:" + str(uuid.uuid4())] * 2001)


@pytest.mark.parametrize("level", ["HEADS", "GROUPS", "ALL_GROUPS", "LEDGERS"])
@pytest.mark.parametrize("hierarchy", ["CURRENT", "ALL"])
def test_streamed_export_presets_and_filters_preserve_full_period_controls(level, hierarchy):
    import datetime as dt

    from test_trial_balance_domain import query
    from trial_balance_filter_fixture import filtering_dataset

    from reports.domain.statements import Facts
    from reports.domain.trial_balance import AMOUNTS, calculate
    from reports.rendering.trial_balance import Selection
    from reports.schemas.trial_balance_options import TrialPresentation

    facts, ids = filtering_dataset()
    frozen, _ = calculate(
        Facts(facts),
        query(
            date_from="2026-04-02",
            comparative_from="2027-04-01",
            comparative_to="2027-04-30",
        ),
        dt.date(2026, 4, 1),
    )
    for period in ("CURRENT", "COMPARATIVE"):
        for show_zero in (False, True):
            options = TrialPresentation(
                period=period, hierarchy=hierarchy, level=level, show_zero=show_zero
            )
            selection = Selection(options)
            selected = []
            for start in range(0, len(frozen), 2):
                selected.extend(selection.rows(frozen[start : start + 2]))
            assert all(row["period"] == period for row in selected)
            controls = [row for row in selected if row["row_kind"] == "TRIAL_BALANCE_CONTROL"]
            assert len(controls) == 1
            original = next(
                row
                for row in frozen
                if row["period"] == period and row["row_kind"] == "TRIAL_BALANCE_CONTROL"
            )
            assert {key: controls[0][key] for key in AMOUNTS} == {
                key: original[key] for key in AMOUNTS
            }
            if not show_zero:
                assert all(
                    not row["is_zero"]
                    for row in selected
                    if row["row_kind"] != "TRIAL_BALANCE_CONTROL"
                )
            accounts = {row["account_id"] for row in selected if row["row_kind"] == "ACCOUNT"}
            if hierarchy == "ALL" or level == "LEDGERS":
                expected = {
                    row["account_id"]
                    for row in frozen
                    if row["period"] == period
                    and row["row_kind"] == "ACCOUNT"
                    and (show_zero or not row["is_zero"])
                }
                assert accounts == expected
            elif level in {"HEADS", "GROUPS"}:
                assert accounts == set()
            else:
                assert accounts == {ids["cash"]} | (
                    {ids["clearing"]} if show_zero or period == "CURRENT" else set()
                )
            if period == "CURRENT" and (hierarchy == "ALL" or level in {"ALL_GROUPS", "LEDGERS"}):
                assert ids["clearing"] in accounts
