"""Keep explicit native constraint names stable across metadata-created databases."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import CheckConstraint

from vouchers.metadata import service_metadata


def test_explicit_check_names_match_native_migrations() -> None:
    expected = {
        "counter_operator": ["ck_counter_operator_status"],
        "voucher_item_regulatory_projection": [
            "ck_voucher_item_reg_class_shape",
            "ck_voucher_item_reg_dates",
            "ck_voucher_item_reg_kind",
            "ck_voucher_item_reg_source_version",
            "ck_voucher_item_reg_version",
        ],
        "voucher_number_series": [
            "ck_voucher_number_series_mode",
            "ck_voucher_number_series_reset",
            "ck_voucher_number_series_start_value",
        ],
        "voucher_party_drug_licence_projection": [
            "ck_voucher_party_drug_dates",
            "ck_voucher_party_drug_form",
            "ck_voucher_party_drug_source_version",
            "ck_voucher_party_drug_version",
        ],
    }
    metadata = service_metadata()
    for table, names in expected.items():
        actual = {
            str(c.name)
            for c in metadata.tables[table].constraints
            if isinstance(c, CheckConstraint)
        }
        assert set(names) <= actual, table


def test_invoice_payable_migration_uses_model_check_name(monkeypatch) -> None:
    path = Path(__file__).parents[3] / "dbs/vouchers/versions/0116_invoice_payable_total.py"
    spec = spec_from_file_location("voucher_invoice_payable_revision", path)
    assert spec is not None and spec.loader is not None
    revision = module_from_spec(spec)
    spec.loader.exec_module(revision)
    check_name = next(
        str(constraint.name)
        for constraint in service_metadata().tables["voucher_invoice_detail"].constraints
        if isinstance(constraint, CheckConstraint)
        and "payable_total" in str(constraint.name)
    )
    statements: list[str] = []
    monkeypatch.setattr(revision.op, "execute", statements.append)

    revision.upgrade()
    assert len(statements) == 1
    assert f"ADD CONSTRAINT {check_name} " in statements[0]
    statements.clear()

    revision.downgrade()
    assert len(statements) == 1
    assert f"DROP CHECK {check_name}" in statements[0]
