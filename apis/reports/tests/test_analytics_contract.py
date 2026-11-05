from financial_fixture import financial_manifest
from invoice_fixture import invoice_dataset
from reporting_contract.contract import Fact, Manifest, digest
from reporting_contract.invoice import InvoiceSupplyFact


def test_legacy_source_schema_and_optional_item_link_remain_readable_without_digest_changes():
    facts, _ = invoice_dataset()
    manifest = financial_manifest(facts).model_dump(mode="json")
    manifest["schema_hash"] = "d02efe7ab19f594ceaa92412f936adcde1a875ceee26d878266d9bd5c96b9710"
    assert Manifest.model_validate(manifest).schema_hash == manifest["schema_hash"]
    supply = next(fact for fact in facts if fact.entity == "invoice_supply_fact")
    legacy = supply.data.copy()
    legacy.pop("item_line_key", None)
    assert InvoiceSupplyFact.model_validate(legacy).item_line_key is None
    raw = supply.model_dump(mode="json") | {"data": legacy}
    raw["content_hash"] = digest({key: raw[key] for key in ("entity", "source_id", "data")})
    assert Fact.model_validate(raw).data == legacy
    assert "item_line_key" not in Fact.model_validate(raw).data
