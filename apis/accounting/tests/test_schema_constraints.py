"""Keep explicit native constraint names stable across metadata-created databases."""

from sqlalchemy import CheckConstraint

from accounting.metadata import service_metadata


def test_explicit_check_names_match_native_migrations() -> None:
    expected = {
        "exchange_rate_quote": [
            "ck_exchange_rate_quote_pair",
            "ck_exchange_rate_quote_positive",
            "ck_exchange_rate_quote_purpose",
            "ck_exchange_rate_quote_source",
            "ck_exchange_rate_quote_status",
            "ck_exchange_rate_quote_version",
        ],
        "exchange_rate_usage": ["ck_exchange_rate_usage_positive"],
        "invoice_record": ["source_kind"],
        "party_drug_licence": [
            "ck_party_drug_licence_dates",
            "ck_party_drug_licence_form",
            "ck_party_drug_licence_version",
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
